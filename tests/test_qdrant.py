"""Opt-in Qdrant integration test.

Runs only when qdrant-client is installed (the .[prod] extra). Uses Qdrant's
in-memory mode, so no server is required — this validates the QdrantVectorStore
code path (create/upsert/query_points) end to end through the RetrievalIndex.
"""

import pytest

pytest.importorskip("qdrant_client")

from retrieval.embedder import HashingEmbedder  # noqa: E402
from retrieval.index import RetrievalIndex  # noqa: E402
from retrieval.vector_store import QdrantVectorStore  # noqa: E402


def test_qdrant_backed_hybrid_search():
    emb = HashingEmbedder()
    vs = QdrantVectorStore(":memory:", "authored_test", dim=emb.dim)
    ix = RetrievalIndex(emb, vs)
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
