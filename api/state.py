"""Process-shared retrieval index for the API.

Phase 1 keeps a single in-process RetrievalIndex, built from environment config on
first use. Tests reset it via ``set_index`` for isolation. Persistence across
restarts comes with the Qdrant/graph backends (the index is a thin front over them).
"""

from __future__ import annotations

from retrieval.index import RetrievalIndex, build_index_from_env

_index: RetrievalIndex | None = None


def get_index() -> RetrievalIndex:
    global _index
    if _index is None:
        _index = build_index_from_env()
    return _index


def set_index(index: RetrievalIndex) -> None:
    global _index
    _index = index
