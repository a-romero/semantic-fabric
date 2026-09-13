"""Extraction wired into ingestion: extracted entities/relations enrich the graph.

Uses a deterministic fake extractor (no LLM) so the wiring is fully tested offline.
"""

from fabric_client.models import ExtractedEntity, ExtractedRelation, Extraction
from fastapi.testclient import TestClient

from api import state
from api.main import app
from retrieval.embedder import HashingEmbedder
from retrieval.index import RetrievalIndex
from retrieval.vector_store import InMemoryVectorStore

client = TestClient(app)


class FakeExtractor:
    """Returns a fixed extraction regardless of input; name/model for the endpoint."""

    name = "fake"
    model = "fake-model"

    def extract(self, text, hint=None):
        return Extraction(
            entities=[
                ExtractedEntity(name="ISA", type="Product"),
                ExtractedEntity(name="Aviva", type="Organization"),
            ],
            relations=[ExtractedRelation(subject="ISA", predicate="offered_by", object="Aviva")],
        )


def _pages():
    return [
        {"path": "investments/isas/index.md", "frontmatter": {"title": "ISAs"},
         "body": "An ISA is a tax-efficient savings account offered by Aviva."},
        {"path": "providers/aviva/index.md", "frontmatter": {"title": "Aviva"},
         "body": "Aviva is a UK insurer and pension provider."},
    ]


def test_add_pages_with_extractor_attaches_entities_and_graph_edges():
    ix = RetrievalIndex(HashingEmbedder(), InMemoryVectorStore())
    ix.add_pages(_pages(), extractor=FakeExtractor())

    # entities surface on retrieved evidence units
    units = ix.search("tax-efficient savings", top_k=5)
    assert units and any("ISA" in u.entities for u in units)

    # both pages share the "Aviva" entity -> graph connects them
    hits = ix.graph_expand("investments/isas/index.md", hops=1)
    paths = {h.path for h in hits}
    assert "providers/aviva/index.md" in paths
    # the connecting relation is surfaced as a shared-entity/relation edge
    assert any("Aviva" in (h.content or "") or "relation" in (h.content or "").lower()
               or "shared-entity" in (h.content or "") for h in hits)


def test_graph_expand_from_entity_seed():
    ix = RetrievalIndex(HashingEmbedder(), InMemoryVectorStore())
    ix.add_pages(_pages(), extractor=FakeExtractor())
    # seed by an extracted entity name -> pages mentioning it
    hits = ix.graph_expand("Aviva", hops=1)
    assert {h.path for h in hits} & {"investments/isas/index.md", "providers/aviva/index.md"}


def test_no_extractor_leaves_entities_empty():
    ix = RetrievalIndex(HashingEmbedder(), InMemoryVectorStore())
    ix.add_pages(_pages())  # no extractor
    units = ix.search("savings", top_k=5)
    assert units and all(u.entities == [] for u in units)


def test_ingest_endpoint_enriches_when_flag_on(monkeypatch):
    monkeypatch.setenv("EXTRACTION_ON_INGEST", "true")
    state.set_extractor(FakeExtractor())
    client.post("/ingest", json={"kind": "markdown_tree", "namespace": "authored",
                                 "payload": {"pages": _pages()}})
    r = client.post("/search", json={"query": "tax-efficient savings", "top_k": 5})
    units = r.json()["units"]
    assert any("Aviva" in u["entities"] or "ISA" in u["entities"] for u in units)
