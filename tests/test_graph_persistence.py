"""On-env: persistent graph backends (Kuzu LPG + Oxigraph RDF).

SKIPPED unless the native lib is installed (the ``.[graph]`` extra). Each test builds a
store at a tmp path, ingests pages/entities/relations, checks GraphRAG expansion, then
reopens a FRESH store at the SAME path and asserts the graph was reloaded from disk —
i.e. it actually persisted.

Run: pip install -e ".[graph]" && pytest -q tests/test_graph_persistence.py
"""

from __future__ import annotations


def _populate(store):
    store.add_page("investments/isas/index.md", "ISAs", "Tax-efficient savings.",
                   ["savings", "tax"], "investments")
    store.add_page("investments/isas/cash.md", "Cash ISA", "A cash ISA.",
                   ["savings"], "investments")
    store.add_entity("ISA", "Product", page_path="investments/isas/index.md")
    store.add_entity("Aviva", "Org", page_path="investments/isas/index.md")
    store.add_entity("Aviva", "Org", page_path="investments/isas/cash.md")
    store.add_relation("Aviva", "offers", "ISA")


def _assert_graph(store):
    # hierarchy: parent -> child
    kids = {r["path"] for r in store.expand("investments/isas/index.md", hops=1)}
    assert "investments/isas/cash.md" in kids
    # shared entity "Aviva" links the two pages
    ent = {r["path"] for r in store.expand("Aviva", hops=1)}
    assert {"investments/isas/index.md", "investments/isas/cash.md"} <= ent


def test_kuzu_persists_and_reloads(tmp_path):
    import pytest

    pytest.importorskip("kuzu")
    from graph.kuzu_backend import KuzuGraphStore

    db = str(tmp_path / "kuzu")
    _populate(KuzuGraphStore(db))
    _assert_graph(KuzuGraphStore(db))  # fresh instance, same path -> reloaded


def test_oxigraph_persists_and_reloads(tmp_path):
    import pytest

    pytest.importorskip("pyoxigraph")
    from graph.oxigraph_backend import OxigraphGraphStore

    db = str(tmp_path / "oxi")
    _populate(OxigraphGraphStore(db))
    _assert_graph(OxigraphGraphStore(db))  # fresh instance, same path -> reloaded
