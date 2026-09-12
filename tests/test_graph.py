"""Phase 1 graph-expansion tests (GraphRAG third leg)."""

from fastapi.testclient import TestClient

from api.main import app
from graph.store import InMemoryGraphStore
from retrieval.embedder import HashingEmbedder
from retrieval.index import RetrievalIndex
from retrieval.vector_store import InMemoryVectorStore

client = TestClient(app)


def _pages():
    return [
        {"path": "investments/index.md", "frontmatter": {"title": "Investments",
         "topics": ["investing"]}, "body": "Investment products."},
        {"path": "investments/isas/index.md", "frontmatter": {"title": "ISAs",
         "topics": ["tax-efficient", "savings"]}, "body": "An ISA is a savings account."},
        {"path": "investments/lisa/index.md", "frontmatter": {"title": "LISA",
         "topics": ["tax-efficient", "savings"]}, "body": "A Lifetime ISA."},
        {"path": "insurance/home/index.md", "frontmatter": {"title": "Home Insurance",
         "topics": ["property"]}, "body": "Covers your home."},
    ]


def test_hierarchy_expansion_finds_children():
    g = InMemoryGraphStore()
    for p in _pages():
        g.add_page(p["path"], p["frontmatter"]["title"], "", p["frontmatter"]["topics"],
                   p["path"].split("/")[0])
    hits = g.expand("investments/index.md", hops=1, rel_types=["hierarchy"])
    paths = {h["path"] for h in hits}
    assert "investments/isas/index.md" in paths
    assert "investments/lisa/index.md" in paths
    assert "insurance/home/index.md" not in paths


def test_shared_topic_expansion_links_siblings():
    g = InMemoryGraphStore()
    for p in _pages():
        g.add_page(p["path"], p["frontmatter"]["title"], "", p["frontmatter"]["topics"],
                   p["path"].split("/")[0])
    # ISAs and LISA share the 'tax-efficient'/'savings' topics.
    hits = g.expand("investments/isas/index.md", hops=1, rel_types=["topic"])
    paths = {h["path"] for h in hits}
    assert "investments/lisa/index.md" in paths
    assert any(h["relation"].startswith("shared-topic:") for h in hits)


def test_expand_by_topic_seed():
    g = InMemoryGraphStore()
    for p in _pages():
        g.add_page(p["path"], p["frontmatter"]["title"], "", p["frontmatter"]["topics"],
                   p["path"].split("/")[0])
    hits = g.expand("tax-efficient", hops=1)
    paths = {h["path"] for h in hits}
    assert {"investments/isas/index.md", "investments/lisa/index.md"} <= paths


def test_index_graph_expand_returns_fact_units():
    ix = RetrievalIndex(HashingEmbedder(), InMemoryVectorStore(), InMemoryGraphStore())
    ix.add_pages(_pages())
    units = ix.graph_expand("investments/isas/index.md", hops=1)
    assert units
    u = units[0]
    assert u.type.value == "fact"
    assert u.entities == ["investments/isas/index.md"]
    assert u.provenance and u.provenance.locator


def test_graph_expand_over_http(sample_kb):
    # sample_kb ingests two pages in different sections; expand from the ISAs page.
    r = client.post("/graph/expand", json={"seed": "investments/isas/index.md", "hops": 1})
    assert r.status_code == 200
    # No sibling in the same section in the sample KB, so this simply must not error
    # and must return a valid SearchResponse shape.
    assert "units" in r.json()
