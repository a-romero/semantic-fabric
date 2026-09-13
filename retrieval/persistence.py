"""Optional SQLite persistence for the retrieval index and KB (stdlib only).

Enabled by ``FABRIC_DB=<path>``. The in-memory chunk store + BM25 index and the KB pages
are otherwise process-scoped, so ``/search`` and ``/kb`` return nothing after a service
restart until re-ingest. This write-through sidecar persists chunks (with their embedding
vectors) and KB pages so the index can be rebuilt on startup — vectors are re-upserted
into the in-memory vector store and BM25 is re-derived from the chunk text.

Same pattern as the other optional backends: the dependency-free in-memory stores stay
the default; persistence is opt-in and additive.
"""

from __future__ import annotations

import json
import sqlite3
import threading


class SqliteStore:
    def __init__(self, path: str) -> None:
        # check_same_thread=False: the API serves requests on a threadpool; a lock
        # serialises writes (SQLite handles concurrent readers).
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS chunks(id TEXT PRIMARY KEY, data TEXT, vector TEXT)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS kb_pages("
            "namespace TEXT, path TEXT, data TEXT, PRIMARY KEY(namespace, path))"
        )
        self._conn.commit()

    # -- chunks (with vectors) -----------------------------------------------
    def save_chunks(self, rows: list[tuple[str, dict, list[float]]]) -> None:
        if not rows:
            return
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO chunks(id, data, vector) VALUES(?, ?, ?)",
                [(cid, json.dumps(data), json.dumps(vec)) for cid, data, vec in rows],
            )
            self._conn.commit()

    def load_chunks(self) -> list[tuple[str, dict, list[float]]]:
        cur = self._conn.execute("SELECT id, data, vector FROM chunks")
        return [(cid, json.loads(data), json.loads(vec)) for cid, data, vec in cur.fetchall()]

    # -- KB pages ------------------------------------------------------------
    def save_page(self, namespace: str, path: str, data: dict) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO kb_pages(namespace, path, data) VALUES(?, ?, ?)",
                (namespace, path, json.dumps(data)),
            )
            self._conn.commit()

    def load_pages(self) -> list[tuple[str, str, dict]]:
        cur = self._conn.execute("SELECT namespace, path, data FROM kb_pages")
        return [(ns, path, json.loads(data)) for ns, path, data in cur.fetchall()]


_store: SqliteStore | None = None
_store_path: str | None = None


def get_store(path: str) -> SqliteStore:
    """Process-wide singleton so the index and KB share one DB connection/file."""
    global _store, _store_path
    if _store is None or _store_path != path:
        _store = SqliteStore(path)
        _store_path = path
    return _store
