"""Vector stores behind one protocol.

- ``InMemoryVectorStore`` — pure-Python cosine search over normalized vectors. Default
  for tests/CI and small local runs; no external service.
- ``QdrantVectorStore`` — the production store. Imported lazily so the base install
  and CI don't need qdrant-client.

Selected by ``VECTOR_STORE`` (``memory`` default, ``qdrant`` in deployment).
"""

from __future__ import annotations

from typing import Protocol


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
    """Production vector store (Qdrant). Optional heavy dependency."""

    def __init__(self, url: str, collection: str, dim: int) -> None:
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams
        except ImportError as exc:  # pragma: no cover - prod installs only
            raise RuntimeError("Qdrant requires qdrant-client: pip install qdrant-client") from exc
        self._client = QdrantClient(url=url)
        self._collection = collection
        if not self._client.collection_exists(collection):
            self._client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )

    def upsert(self, ids: list[str], vectors: list[list[float]]) -> None:
        from qdrant_client.models import PointStruct

        # Qdrant point ids must be ints or UUIDs; keep the string id in the payload.
        points = [
            PointStruct(id=abs(hash(i)) % (10**18), vector=v, payload={"chunk_id": i})
            for i, v in zip(ids, vectors)
        ]
        self._client.upsert(collection_name=self._collection, points=points)

    def query(self, vector: list[float], top_k: int) -> list[tuple[str, float]]:
        hits = self._client.search(
            collection_name=self._collection, query_vector=vector, limit=top_k
        )
        return [(h.payload["chunk_id"], float(h.score)) for h in hits]


def build_vector_store(kind: str | None, *, dim: int, url: str | None, collection: str):
    """Factory from a VECTOR_STORE value."""
    if not kind or kind.strip().lower() in {"memory", "inmemory", "in_memory"}:
        return InMemoryVectorStore()
    if kind.strip().lower() == "qdrant":
        return QdrantVectorStore(url or "http://localhost:6333", collection, dim)
    raise ValueError(f"Unknown VECTOR_STORE: {kind!r}")
