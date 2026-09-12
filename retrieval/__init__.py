"""Hybrid retrieval (Phase 1+): vector + BM25 + graph expansion.

Wraps semantica.vector_store (pgvector/Qdrant/...) and the Context Graph, returning
fabric_client.models.EvidenceUnit lists. This is what api.main.search() calls once
the stubs are removed.

Public entry (future):
    def search_evidence(req: SearchRequest) -> list[EvidenceUnit]: ...
    def graph_expand(req: GraphExpandRequest) -> list[EvidenceUnit]: ...
"""
