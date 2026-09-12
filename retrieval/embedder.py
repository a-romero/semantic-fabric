"""Embedders behind one protocol.

- ``HashingEmbedder`` — deterministic, dependency-free bag-of-words hashing into a
  fixed-dimension unit vector. Not high quality, but it exercises the full vector
  path in tests and CI without downloading a model.
- ``BGEM3Embedder`` — the production embedder (BAAI/bge-m3), self-hosted. Imported
  lazily so the base install and CI don't need torch / FlagEmbedding.

Selected by ``EMBEDDING_MODEL``: a value of ``hashing`` (or unset in tests) uses the
hashing embedder; anything else is treated as a model id for BGE-M3.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class Embedder(Protocol):
    @property
    def dim(self) -> int: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashingEmbedder:
    """Feature-hashing embedder. Deterministic and dependency-free."""

    def __init__(self, dim: int = 256) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self._dim
        for tok in _tokenize(text):
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            v[h % self._dim] += 1.0
        norm = math.sqrt(sum(x * x for x in v))
        if norm > 0:
            v = [x / norm for x in v]
        return v

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]


class BGEM3Embedder:
    """Production embedder (BAAI/bge-m3). Optional heavy dependency."""

    def __init__(self, model_id: str = "BAAI/bge-m3") -> None:
        try:
            from FlagEmbedding import BGEM3FlagModel
        except ImportError as exc:  # pragma: no cover - exercised only in prod installs
            raise RuntimeError(
                "BGE-M3 requires FlagEmbedding: pip install FlagEmbedding"
            ) from exc
        self._model = BGEM3FlagModel(model_id, use_fp16=True)
        self._dim = 1024  # bge-m3 dense dim

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = self._model.encode(texts, return_dense=True)["dense_vecs"]
        return [list(map(float, row)) for row in out]


def build_embedder(model: str | None) -> Embedder:
    """Factory from an EMBEDDING_MODEL value."""
    if not model or model.strip().lower() == "hashing":
        return HashingEmbedder()
    return BGEM3Embedder(model)
