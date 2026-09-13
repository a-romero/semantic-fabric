"""Phase 3 provenance + decision tests (in-memory default backend)."""

from fabric_client.models import Decision
from fastapi.testclient import TestClient

from api.main import app
from provenance.store import InMemoryProvenanceStore

client = TestClient(app)


def test_record_decision_returns_id_and_derivation():
    r = client.post("/decisions", json={
        "scenario": "Is an ISA suitable for tax-free growth?",
        "outcome": "Yes — an ISA shelters growth from tax.",
        "evidence": ["authored:investments/isas/index.md#0", "report-q3.pdf#p12-tab0"],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["recorded"] is True
    assert body["decision_id"].startswith("decision-")
    assert set(body["derived_from"]) == {
        "authored:investments/isas/index.md#0", "report-q3.pdf#p12-tab0"
    }


def test_trace_chain_returns_transitive_lineage():
    store = InMemoryProvenanceStore()
    # Register a source -> evidence chain, then a decision derived from the evidence.
    store.record_entity("report-q3.pdf", kind="source", attrs={"source_id": "report-q3.pdf"})
    store.record_entity(
        "report-q3.pdf#p12-tab0", kind="evidence",
        derived_from=["report-q3.pdf"], attrs={"source_id": "report-q3.pdf", "locator": "page=12"},
    )
    res = store.record_decision(
        Decision(scenario="Q3 revenue?", outcome="4.2", evidence=["report-q3.pdf#p12-tab0"])
    )
    chain = store.trace_chain(res["decision_id"])
    assert chain["found"] and chain["verified"] is True
    ids = {c["id"] for c in chain["chain"]}
    # decision -> evidence -> source, all reachable
    assert {res["decision_id"], "report-q3.pdf#p12-tab0", "report-q3.pdf"} <= ids
    # distances increase along the derivation: decision(0) -> evidence(1) -> source(2)
    dist = {c["id"]: c["distance"] for c in chain["chain"]}
    assert dist[res["decision_id"]] == 0
    assert dist["report-q3.pdf#p12-tab0"] == 1
    assert dist["report-q3.pdf"] == 2


def test_hash_chain_detects_tampering():
    store = InMemoryProvenanceStore()
    store.record_decision(Decision(scenario="s1", outcome="o1", evidence=["e1"]))
    store.record_decision(Decision(scenario="s2", outcome="o2", evidence=["e2"]))
    assert store.verify_chain() is True
    # Tamper with a stored record's attributes after the fact.
    rec = store._records["decision-1"]  # noqa: SLF001 - white-box tamper test
    rec.attrs["outcome"] = "TAMPERED"
    assert store.verify_chain() is False


def test_trace_missing_decision_is_not_found():
    r = client.get("/decisions/decision-999/chain")
    assert r.status_code == 200
    assert r.json()["found"] is False


def test_decision_chain_over_http():
    rec = client.post("/decisions", json={
        "scenario": "s", "outcome": "o", "evidence": ["ev-a", "ev-b"],
    }).json()
    chain = client.get(f"/decisions/{rec['decision_id']}/chain").json()
    assert chain["found"] is True
    assert chain["verified"] is True
    # evidence ids appear in the lineage even though only referenced (unregistered)
    ids = {c["id"] for c in chain["chain"]}
    assert {"ev-a", "ev-b"} <= ids
