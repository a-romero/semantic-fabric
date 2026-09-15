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


def _norm(snap: dict) -> dict:
    """Order-independent view of a snapshot for cross-backend comparison."""
    return {
        "pages": sorted(
            ({**p, "topics": sorted(p["topics"])} for p in snap["pages"]),
            key=lambda p: p["path"],
        ),
        "entities": sorted(
            ({**e, "pages": sorted(e["pages"])} for e in snap["entities"]),
            key=lambda e: e["name"],
        ),
        "relations": sorted(
            snap["relations"], key=lambda r: (r["subject"], r["predicate"], r["object"])
        ),
    }


def test_oxigraph_snapshot_matches_inmemory(tmp_path):
    """The aggregate-query Oxigraph snapshot must match the in-memory backend exactly."""
    import pytest

    pytest.importorskip("pyoxigraph")
    from graph.oxigraph_backend import OxigraphGraphStore

    def populate(g):
        g.add_page("investments/index.md", "Investments", "Overview.", ["tax"], "investments")
        g.add_page("investments/isas/index.md", "ISAs", "Tax-efficient.",
                   ["isa", "savings"], "investments")
        g.add_page("investments/isas/cash.md", "Cash ISA", "A cash ISA.",
                   ["savings"], "investments")
        g.add_entity("Aviva", "Org", page_path="investments/isas/index.md")
        g.add_entity("Aviva", "Org", page_path="investments/isas/cash.md")
        g.add_entity("ISA", "Product", page_path="investments/isas/index.md")
        g.add_relation("Aviva", "offers", "ISA")

    mem = InMemoryGraphStore()
    oxi = OxigraphGraphStore(str(tmp_path / "oxi"))
    populate(mem)
    populate(oxi)
    assert _norm(oxi.snapshot()) == _norm(mem.snapshot())


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
