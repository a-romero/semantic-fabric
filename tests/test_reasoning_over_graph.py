"""Reasoning over the knowledge graph itself (over_graph).

The KG is surfaced as Datalog atoms (entities/relations/hierarchy) and seeded into the
reasoner, so a query can be answered by inference over the actual graph. CI runs this
against the default SimpleForwardChainer; on-env it also flows through semantica's
DatalogReasoner (same ReasoningRequest.facts path, confirmed API).
"""

from fastapi.testclient import TestClient

from api import state
from api.main import app
from graph.store import InMemoryGraphStore

client = TestClient(app)


def test_inmemory_graph_facts_are_datalog_atoms():
    g = InMemoryGraphStore()
    # Section-index hierarchy: isas/index.md is a child of investments/index.md.
    g.add_page("investments/index.md", "Investments", "s", ["savings"], "investments")
    g.add_page("investments/isas/index.md", "ISAs", "s", ["savings"], "investments")
    g.add_entity("Aviva", "Org", page_path="investments/isas/index.md")
    g.add_entity("Enhanced Pension Annuity", "Product",
                 page_path="investments/isas/index.md")
    g.add_relation("Aviva", "offers", "Enhanced Pension Annuity")

    facts = g.facts()
    # relation -> predicate(subject, object), all normalized to Datalog constants
    assert "offers(aviva, enhanced_pension_annuity)" in facts
    # mentions + hierarchy edges are emitted too
    assert "mentions(investments_isas_index_md, aviva)" in facts
    assert "parent(investments_isas_index_md, investments_index_md)" in facts


def test_reason_over_graph_derives_from_kg():
    # Seed the API's KG directly, then reason over it (default engine).
    g = state.get_index().graph
    g.add_entity("Aviva", "Org", page_path="p/index.md")
    g.add_entity("ISA", "Product", page_path="p/index.md")
    g.add_relation("Aviva", "offers", "ISA")

    # A ground KG fact holds when reasoning over the graph...
    r = client.post("/reason", json={"query": "offers(aviva, isa)", "over_graph": True})
    assert r.status_code == 200 and r.json()["answer"].startswith("Yes")

    # ...and a rule fires over KG facts to derive something new.
    r2 = client.post("/reason", json={
        "query": "insurable(isa)",
        "over_graph": True,
        "rules": [{"name": "R", "body": ["offers(aviva, isa)"], "head": "insurable(isa)"}],
    })
    assert r2.json()["answer"].startswith("Yes")
    assert r2.json()["rule_trace"]


def test_reason_without_over_graph_ignores_kg():
    g = state.get_index().graph
    g.add_entity("Aviva", "Org", page_path="p/index.md")
    g.add_relation("Aviva", "offers", "ISA")
    # Same query, but not over the graph -> the KG fact is not in scope.
    r = client.post("/reason", json={"query": "offers(aviva, isa)"})
    assert r.status_code == 200 and r.json()["answer"].startswith("No")
