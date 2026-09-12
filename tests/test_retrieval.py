"""Phase 1 retrieval tests: chunking, hybrid ranking, and the ingest->search flow."""

from fastapi.testclient import TestClient

from api.main import app
from api.state import get_index
from retrieval.chunking import chunk_page
from retrieval.embedder import HashingEmbedder
from retrieval.index import RetrievalIndex
from retrieval.vector_store import InMemoryVectorStore

client = TestClient(app)


def test_chunk_page_splits_on_headings():
    body = "# Title\n\nIntro para.\n\n## Section A\n\nText A.\n\n## Section B\n\nText B.\n"
    chunks = chunk_page("authored", "x/index.md", {"title": "Title"}, body)
    titles = [c.section_title for c in chunks]
    assert "Section A" in titles and "Section B" in titles
    assert all(c.path == "x/index.md" for c in chunks)
    assert all(c.locator.startswith("x/index.md#") for c in chunks)


def test_empty_index_returns_no_results():
    ix = RetrievalIndex(HashingEmbedder(), InMemoryVectorStore())
    assert ix.search("anything") == []


def test_hybrid_ranks_relevant_page_first():
    ix = RetrievalIndex(HashingEmbedder(), InMemoryVectorStore())
    ix.add_pages(
        [
            {"path": "investments/isas/index.md", "frontmatter": {"title": "ISAs"},
             "body": "An ISA is a tax-efficient individual savings account."},
            {"path": "insurance/home/index.md", "frontmatter": {"title": "Home Insurance"},
             "body": "Covers your home and contents against damage and theft."},
        ]
    )
    units = ix.search("tax-efficient savings account", top_k=2)
    assert units
    assert units[0].path == "investments/isas/index.md"
    assert units[0].content  # evidence carries the chunk text
    assert units[0].provenance and units[0].provenance.locator.startswith("investments/")


def test_section_filter_scopes_results():
    ix = RetrievalIndex(HashingEmbedder(), InMemoryVectorStore())
    ix.add_pages([
        {"path": "investments/isas/index.md", "frontmatter": {"title": "ISAs"},
         "body": "individual savings account"},
        {"path": "insurance/home/index.md", "frontmatter": {"title": "Home"},
         "body": "home contents insurance"},
    ])
    units = ix.search("insurance", section="investments", top_k=5)
    assert all(u.path.startswith("investments/") for u in units)


def test_ingest_then_search_over_http(sample_kb):
    # sample_kb ingested via fixture; verify the live endpoints return real hits.
    r = client.post("/search", json={"query": "stocks and shares ISA", "top_k": 3})
    assert r.status_code == 200
    units = r.json()["units"]
    assert units
    assert any(u["path"] == "investments/isas/index.md" for u in units)


def test_ingest_endpoint_reports_chunk_count():
    pages = [
        {"path": "a/index.md", "frontmatter": {"title": "A"}, "body": "# A\n\none\n\n## B\n\ntwo"}
    ]
    r = client.post(
        "/ingest",
        json={"kind": "markdown_tree", "namespace": "authored", "payload": {"pages": pages}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "done"
    assert get_index().size >= 1
