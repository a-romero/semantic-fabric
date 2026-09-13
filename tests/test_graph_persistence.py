"""On-env: the persistent, SPARQL-native RDF graph backend (Oxigraph).

SKIPPED unless pyoxigraph is installed (the ``.[graph]`` extra). The tests build a store
at a tmp path, ingest pages/entities/relations, check GraphRAG expansion (which runs as
SPARQL over the RDF graph), reopen a FRESH store at the SAME path to prove it persisted,
and confirm the RDF surface semantica consumes (raw SPARQL + an rdflib.Graph snapshot).

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


def test_oxigraph_persists_and_reloads(tmp_path):
    import pytest

    pytest.importorskip("pyoxigraph")
    from graph.oxigraph_backend import OxigraphGraphStore

    db = str(tmp_path / "oxi")
    _populate(OxigraphGraphStore(db))
    _assert_graph(OxigraphGraphStore(db))  # fresh instance, same path -> reloaded


def test_oxigraph_is_sparql_native(tmp_path):
    """Traversal is SPARQL over RDF, and the graph is exposed for semantica."""
    import pytest

    pytest.importorskip("pyoxigraph")
    rdflib = pytest.importorskip("rdflib")
    from graph.oxigraph_backend import OxigraphGraphStore

    store = OxigraphGraphStore(str(tmp_path / "oxi"))
    _populate(store)

    # shared-topic edge (both carry "savings"); isolate it via rel_types (SPARQL filter)
    topic = store.expand("investments/isas/index.md", hops=1, rel_types=["topic"])
    assert any(r["relation"].startswith("shared-topic:") for r in topic)

    # relation edge: cash.md mentions Aviva, Aviva offers ISA, index.md mentions ISA
    rel = store.expand("investments/isas/cash.md", hops=1, rel_types=["relation"])
    assert any(r["relation"] == "relation:offers"
               and r["path"] == "investments/isas/index.md" for r in rel)

    # entity seed resolves through SPARQL to the mentioning pages
    hits = store.expand("Aviva", hops=1)
    assert {h["path"] for h in hits} == {
        "investments/isas/index.md", "investments/isas/cash.md"}

    # raw SPARQL passthrough over the persistent RDF store
    n_entities = list(store.sparql(
        "PREFIX ex: <http://semantic-fabric/ex#> "
        "SELECT ?e WHERE { ?e a ex:Entity }"
    ))
    assert len(n_entities) >= 2  # ISA, Aviva

    # rdflib.Graph snapshot for semantica's reasoners (mentions triples present)
    g = store.rdf_graph()
    assert isinstance(g, rdflib.Graph) and len(g) > 0
    mentions = list(g.triples(
        (None, rdflib.URIRef("http://semantic-fabric/ex#mentions"), None)
    ))
    assert mentions

    # KG as Datalog atoms (gathered by SPARQL) for reasoning over the graph
    facts = store.facts()
    assert "offers(aviva, isa)" in facts
    assert any(f.startswith("mentions(") for f in facts)
