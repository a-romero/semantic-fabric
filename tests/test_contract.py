"""Phase 0 contract tests.

These are the seed of the consumer-driven contract suite: they assert that the wire
shapes are stable and that the API returns valid evidence units. skilled-agent's own
expectations will be added here so a breaking change fails in semantic-fabric's CI,
not in production.
"""

from fastapi.testclient import TestClient

from api.main import app
from fabric_client.models import EvidenceUnit, SearchResponse

client = TestClient(app)


def test_evidence_unit_roundtrip_and_legacy():
    u = EvidenceUnit(path="authored/x/index.md", title="X", summary="s")
    dumped = u.model_dump()
    again = EvidenceUnit.model_validate(dumped)
    assert again == u
    assert u.to_legacy() == {"path": "authored/x/index.md", "title": "X", "summary": "s"}


def test_health_reports_contract_version():
    r = client.get("/health")
    assert r.status_code == 200
    assert "contract_version" in r.json()


def test_search_returns_valid_units():
    r = client.post("/search", json={"query": "what are ISAs?", "section": "investments", "top_k": 2})
    assert r.status_code == 200
    resp = SearchResponse.model_validate(r.json())
    assert len(resp.units) == 2
    # legacy projection still works for existing skilled-agent consumers
    legacy = [u.to_legacy() for u in resp.units]
    assert all(set(item) == {"path", "title", "summary"} for item in legacy)


def test_ingest_returns_job():
    r = client.post("/ingest", json={"kind": "markdown_tree", "namespace": "authored"})
    assert r.status_code == 200
    assert r.json()["status"] in {"queued", "running", "done"}


def test_read_generated_namespace_page():
    r = client.get("/kb/generated/report-q3/summary.md")
    assert r.status_code == 200
    assert r.json()["namespace"] == "generated"
