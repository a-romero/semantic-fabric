"""Vector stores behind one protocol.

- ``InMemoryVectorStore`` — pure-Python cosine search over normalized vectors. Default
  for tests/CI and small local runs; no external service.
- ``QdrantVectorStore`` — the production store. Imported lazily so the base install
  and CI don't need qdrant-client.

Selected by ``VECTOR_STORE`` (``memory`` default, ``qdrant`` in deployment).
"""

from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class VectorStore(Protocol):
    def upsert(self, ids: list[str], vectors: list[list[float]]) -> None: ...

    def query(self, vector: list[float], top_k: int) -> list[tuple[str, float]]:
        """Return [(id, score)] sorted by descending similarity."""
        ...


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class InMemoryVectorStore:
    """Cosine similarity over vectors assumed L2-normalized at upsert time."""

    def __init__(self) -> None:
        self._vectors: dict[str, list[float]] = {}

    def upsert(self, ids: list[str], vectors: list[list[float]]) -> None:
        for i, v in zip(ids, vectors):
            self._vectors[i] = v

    def query(self, vector: list[float], top_k: int) -> list[tuple[str, float]]:
        scored = [(i, _dot(vector, v)) for i, v in self._vectors.items()]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def __len__(self) -> int:
        return len(self._vectors)


class QdrantVectorStore:
    """Production vector store (Qdrant). Optional dependency (qdrant-client).

    ``url`` may be ``:memory:`` (or ``memory``) for an in-process instance — handy for
    tests and local runs — or an ``http://host:port`` URL for a Qdrant server.
    """

    def __init__(self, url: str, collection: str, dim: int) -> None:
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams
        except ImportError as exc:  # pragma: no cover - prod installs only
            raise RuntimeError("Qdrant requires qdrant-client: pip install qdrant-client") from exc
        if url.strip().lower() in {":memory:", "memory"}:
            self._client = QdrantClient(location=":memory:")
        else:
            self._client = QdrantClient(url=url)
        self._collection = collection
        # Counter for stable integer point ids (Qdrant ids must be int/UUID).
        self._next_id = 0
        if not self._client.collection_exists(collection):
            self._client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )

    def upsert(self, ids: list[str], vectors: list[list[float]]) -> None:
        from qdrant_client.models import PointStruct

        # Keep the string chunk id in the payload; assign monotonic integer point ids.
        points = []
        for i, v in zip(ids, vectors):
            points.append(PointStruct(id=self._next_id, vector=v, payload={"chunk_id": i}))
            self._next_id += 1
        self._client.upsert(collection_name=self._collection, points=points)

    def query(self, vector: list[float], top_k: int) -> list[tuple[str, float]]:
        hits = self._client.query_points(
            collection_name=self._collection, query=vector, limit=top_k
        ).points
        return [(h.payload["chunk_id"], float(h.score)) for h in hits]


def build_vector_store(kind: str | None, *, dim: int, url: str | None, collection: str):
    """Factory from a VECTOR_STORE value.

    Falls back to the in-memory store if Qdrant can't be constructed or reached (missing
    dep, no server, or a proxy intercepting the connection), so a misconfigured vector
    store degrades gracefully instead of failing every request — the same fallback
    pattern the other optional backends use. Real embeddings still drive retrieval.
    """
    if not kind or kind.strip().lower() in {"memory", "inmemory", "in_memory"}:
        return InMemoryVectorStore()
    if kind.strip().lower() == "qdrant":
        target = url or "http://localhost:6333"
        try:
            return QdrantVectorStore(target, collection, dim)
        except Exception as exc:
            logger.warning(
                "VECTOR_STORE=qdrant unavailable at %s (%s); falling back to the "
                "in-memory vector store. If you run Qdrant on localhost behind a proxy, "
                "set NO_PROXY=localhost,127.0.0.1.", target, exc,
            )
            return InMemoryVectorStore()
    raise ValueError(f"Unknown VECTOR_STORE: {kind!r}")
