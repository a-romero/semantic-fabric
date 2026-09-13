"""VECTOR_STORE=qdrant degrades to in-memory instead of failing every request."""

from retrieval.vector_store import InMemoryVectorStore, build_vector_store


def test_qdrant_unavailable_falls_back_to_in_memory():
    # No qdrant-client here (and/or nothing listening / a proxy) -> graceful fallback,
    # never an exception that would 500 the ingest/search path.
    vs = build_vector_store("qdrant", dim=8, url="http://127.0.0.1:1", collection="x")
    assert isinstance(vs, InMemoryVectorStore)


def test_memory_default():
    assert isinstance(build_vector_store(None, dim=8, url=None, collection="x"),
                      InMemoryVectorStore)
