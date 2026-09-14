"""The standalone query MCP server's client — the full cycle, in-process.

fabric_mcp.client talks HTTP; here we replace its single ``_call`` seam with the FastAPI
TestClient so the whole retrieve → expand → decision → lineage cycle is exercised in CI
without a network or the ``mcp`` package.
"""

from fastapi.testclient import TestClient

from api import state
from api.main import app
from fabric_mcp import client as fclient

_HTTP = TestClient(app)
SAMPLE = [
    {"path": "investments/isas/index.md",
     "frontmatter": {"title": "ISAs", "summary": "Tax-efficient savings from Aviva."},
     "body": "# ISAs\n\nAn ISA is a tax-efficient savings account offered by Aviva."},
    {"path": "investments/isas/cash-isa.md",
     "frontmatter": {"title": "Cash ISA"},
     "body": "# Cash ISA\n\nA Cash ISA pays tax-free interest and is lower risk."},
]


def _dispatch(method, path, body=None):
    r = _HTTP.get(path) if method == "GET" else _HTTP.post(path, json=body)
    r.raise_for_status()
    return r.json()


def _ingest():
    _HTTP.post("/ingest", json={"kind": "markdown_tree", "namespace": "authored",
                                "payload": {"pages": SAMPLE}})


def test_full_query_cycle(monkeypatch):
    monkeypatch.setattr(fclient, "_call", _dispatch)
    _ingest()

    res = fclient.answer("Is a Cash ISA tax-free, and who offers it?", top_k=3)

    # evidence with provenance
    assert res["evidence"], "expected ranked evidence"
    assert all("provenance" in u for u in res["evidence"])
    # a decision was recorded and its lineage traced (the audit trail)
    assert res["decision"] and res["decision"].get("decision_id")
    assert res["lineage"] and res["lineage"].get("found") is True
    # evidence the agent will cite includes the ISA page
    assert any("investments/isas" in u["path"] for u in res["evidence"])


def test_search_and_reason_over_graph(monkeypatch):
    monkeypatch.setattr(fclient, "_call", _dispatch)
    _ingest()
    # direct search
    hits = fclient.search("tax free interest", top_k=3)
    assert hits and hits[0]["type"] == "markdown_chunk"
    # reasoning endpoint reachable (empty graph on defaults -> derives nothing, no error)
    r = fclient.reason("q", over_graph=True)
    assert "answer" in r


def test_empty_index_diagnostic_when_graph_has_data(monkeypatch):
    monkeypatch.setattr(fclient, "_call", _dispatch)
    # Graph has entities/relations but the retrieval index is empty (the restart-without-
    # FABRIC_DB symptom). Simulate by seeding only the graph, not the index.
    idx = state.get_index()
    idx.graph.add_entity("Aviva", "Org", page_path="p/index.md")
    idx.graph.add_relation("Aviva", "offers", "ISA")

    res = fclient.answer("anything at all")
    assert res["evidence"] == []
    diag = res["diagnostic"]
    assert diag["graph_counts"]["relations"] >= 1
    assert "FABRIC_DB" in diag["likely_cause"]
    assert "Do NOT scan" in diag["do_not"]


def test_errors_are_actionable(monkeypatch):
    # point at a dead port; the client raises a clear, hint-bearing error
    monkeypatch.setenv("FABRIC_URL", "http://127.0.0.1:1")
    monkeypatch.setattr(state, "_index", None, raising=False)
    try:
        fclient.health()
        raise AssertionError("expected a RuntimeError")
    except RuntimeError as e:
        assert "cannot reach fabric" in str(e)
