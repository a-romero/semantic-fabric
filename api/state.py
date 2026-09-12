"""Process-shared stores for the API.

Phase 1 kept a single RetrievalIndex; Phase 2 adds the KB store (authored/ +
generated/ namespaces served over /kb) and an object store (figure images). All are
built lazily and reset by tests for isolation. Persistence across restarts comes with
the Qdrant / object-store backends; these singletons are thin fronts over them.
"""

from __future__ import annotations

from ingest.object_store import InMemoryObjectStore, ObjectStore
from kb.store import KBStore
from retrieval.index import RetrievalIndex, build_index_from_env

_index: RetrievalIndex | None = None
_kb: KBStore | None = None
_object_store: ObjectStore | None = None


def get_index() -> RetrievalIndex:
    global _index
    if _index is None:
        _index = build_index_from_env()
    return _index


def set_index(index: RetrievalIndex) -> None:
    global _index
    _index = index


def get_kb() -> KBStore:
    global _kb
    if _kb is None:
        _kb = KBStore()
    return _kb


def set_kb(kb: KBStore) -> None:
    global _kb
    _kb = kb


def get_object_store() -> ObjectStore:
    global _object_store
    if _object_store is None:
        _object_store = InMemoryObjectStore()
    return _object_store


def set_object_store(store: ObjectStore) -> None:
    global _object_store
    _object_store = store
