"""FABRIC_DB persistence: the chunk store + KB survive a fresh index/KB (restart)."""

from pathlib import Path

from kb.store import KBStore
from retrieval.embedder import HashingEmbedder
from retrieval.index import RetrievalIndex
from retrieval.persistence import SqliteStore
from retrieval.vector_store import InMemoryVectorStore

PAGES = [
    {"path": "investments/isas/index.md",
     "frontmatter": {"title": "ISAs", "summary": "Tax-efficient savings."},
     "body": "# ISAs\n\nAn ISA is a tax-efficient savings account offered by Aviva."},
]


def _index(store):
    return RetrievalIndex(HashingEmbedder(), InMemoryVectorStore(), persist=store)


def test_search_survives_a_restart(tmp_path: Path):
    db = str(tmp_path / "fabric.db")

    # First "process": ingest, confirm search works.
    idx = _index(SqliteStore(db))
    idx.add_pages(PAGES, namespace="authored")
    assert idx.search("tax efficient savings", top_k=3)

    # Second "process": a brand-new index over the SAME db, no re-ingest.
    idx2 = _index(SqliteStore(db))
    assert idx2.size == 0  # nothing ingested yet in this instance
    loaded = idx2.load_persisted()
    assert loaded >= 1
    hits = idx2.search("tax efficient savings", top_k=3)
    assert hits, "search must return hits after reload without re-ingest"
    assert any(h.path == "investments/isas/index.md" for h in hits)


def test_kb_pages_survive_a_restart(tmp_path: Path):
    db = str(tmp_path / "fabric.db")
    kb = KBStore(persist=SqliteStore(db))
    kb.put("authored", "a/index.md", body="# A\n\nbody", frontmatter={"title": "A"})

    kb2 = KBStore(persist=SqliteStore(db))
    assert kb2.count("authored") == 0
    kb2.load_persisted()
    page = kb2.get("authored", "a/index.md")
    assert page is not None and page.frontmatter["title"] == "A"


def test_no_persist_is_unchanged(tmp_path: Path):
    # Without a store, nothing persists and load is a no-op.
    idx = RetrievalIndex(HashingEmbedder(), InMemoryVectorStore())
    idx.add_pages(PAGES)
    assert idx.load_persisted() == 0
