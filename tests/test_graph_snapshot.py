"""The read-only whole-graph snapshot (GET /graph) used by the demo visualisation."""

from fastapi.testclient import TestClient

from api import state
from api.main import app
from graph.store import InMemoryGraphStore

client = TestClient(app)


def test_inmemory_snapshot_shape():
    g = InMemoryGraphStore()
    g.add_page("investments/index.md", "Investments", "s", ["tax"], "investments")
    g.add_page("investments/isas/index.md", "ISAs", "s", ["isa"], "investments")
    g.add_entity("Aviva", "Org", page_path="investments/isas/index.md")
    g.add_entity("ISA", "Product", page_path="investments/isas/index.md")
    g.add_relation("Aviva", "offers", "ISA")

    snap = g.snapshot()
    assert {p["path"] for p in snap["pages"]} == {
        "investments/index.md", "investments/isas/index.md"}
    # hierarchy is surfaced on the child page
    child = next(p for p in snap["pages"] if p["path"] == "investments/isas/index.md")
    assert child["parent"] == "investments/index.md"
    assert {e["name"] for e in snap["entities"]} == {"Aviva", "ISA"}
    assert {"subject": "Aviva", "predicate": "offers", "object": "ISA"} in snap["relations"]


def test_graph_endpoint_returns_snapshot_with_counts():
    idx = state.get_index()
    idx.graph.add_entity("Aviva", "Org", page_path="p/index.md")
    idx.graph.add_entity("ISA", "Product", page_path="p/index.md")
    idx.graph.add_relation("Aviva", "offers", "ISA")

    r = client.get("/graph")
    assert r.status_code == 200
    body = r.json()
    assert body["counts"]["entities"] == 2
    assert body["counts"]["relations"] == 1
    assert any(e["name"] == "Aviva" for e in body["entities"])
