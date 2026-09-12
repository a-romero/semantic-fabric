"""Hybrid retrieval (Phase 1): vector + BM25 over ingested chunks, fused with RRF.

Wraps a vector store (in-memory default; Qdrant in deployment) and a BM25 index,
returning fabric_client.models.EvidenceUnit lists. Graph expansion (the third leg)
arrives with the graph store. Public surface:

    build_index_from_env() -> RetrievalIndex
    RetrievalIndex.add_pages(pages, namespace) / .search(query, section, top_k)
"""

from .index import RetrievalIndex, build_index_from_env

__all__ = ["RetrievalIndex", "build_index_from_env"]
