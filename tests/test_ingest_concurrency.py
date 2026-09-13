"""Concurrent extraction-on-ingest preserves per-page correctness and ordering."""

from fabric_client.models import ExtractedEntity, Extraction

from retrieval.embedder import HashingEmbedder
from retrieval.index import RetrievalIndex
from retrieval.vector_store import InMemoryVectorStore


class _BodyExtractor:
    """Deterministic stub: extracts one entity named after a token in the body."""

    name = "stub"
    model = None

    def extract(self, text, hint=None):
        token = text.strip().split()[0] if text.strip() else "empty"
        return Extraction(entities=[ExtractedEntity(name=token, type="Token")])


def _index():
    return RetrievalIndex(HashingEmbedder(), InMemoryVectorStore())


def test_concurrent_extraction_maps_each_page_to_its_own_entities(monkeypatch):
    monkeypatch.setenv("EXTRACTION_CONCURRENCY", "4")
    idx = _index()
    pages = [{"path": f"s/p{i}.md", "frontmatter": {"title": f"P{i}"},
              "body": f"tok{i} some body text about topic {i}."} for i in range(10)]
    idx.add_pages(pages, extractor=_BodyExtractor())

    snap = idx.graph_snapshot()
    names = {e["name"] for e in snap["entities"]}
    assert {f"tok{i}" for i in range(10)} <= names
    # each entity is linked to exactly its own page (no cross-page bleed under threading)
    by_name = {e["name"]: e["pages"] for e in snap["entities"]}
    for i in range(10):
        assert by_name[f"tok{i}"] == [f"s/p{i}.md"]


def test_serial_and_concurrent_agree(monkeypatch):
    pages = [{"path": f"s/p{i}.md", "frontmatter": {}, "body": f"tok{i} text {i}."}
             for i in range(6)]

    monkeypatch.setenv("EXTRACTION_CONCURRENCY", "1")
    serial = _index()
    serial.add_pages(pages, extractor=_BodyExtractor())

    monkeypatch.setenv("EXTRACTION_CONCURRENCY", "5")
    conc = _index()
    conc.add_pages(pages, extractor=_BodyExtractor())

    assert serial.graph_snapshot()["entities"] == conc.graph_snapshot()["entities"]
