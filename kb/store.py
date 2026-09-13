"""In-memory KB store backing GET /kb/{namespace}/{path}.

Holds Markdown pages per namespace. The markdown ingest path mirrors authored pages
here for reading; the dense-source pipeline writes generated summary pages under
'generated'. A persistent store (object store / DB) replaces this without changing
the API.
"""

from __future__ import annotations

from typing import Any

from fabric_client.models import KBPage


class KBStore:
    def __init__(self, persist=None) -> None:
        # namespace -> path -> KBPage
        self._pages: dict[str, dict[str, KBPage]] = {}
        self._persist = persist  # optional SqliteStore for restart durability

    def load_persisted(self) -> int:
        """Repopulate pages from the SQLite sidecar (called on startup)."""
        if self._persist is None:
            return 0
        pages = self._persist.load_pages()
        for namespace, path, data in pages:
            self._pages.setdefault(namespace, {})[path] = KBPage(**data)
        return len(pages)

    def put(
        self, namespace: str, path: str, body: str, frontmatter: dict[str, Any] | None = None
    ) -> None:
        page = KBPage(namespace=namespace, path=path, frontmatter=frontmatter or {}, body=body)
        self._pages.setdefault(namespace, {})[path] = page
        if self._persist is not None:
            self._persist.save_page(namespace, path, page.model_dump())

    def get(self, namespace: str, path: str) -> KBPage | None:
        return self._pages.get(namespace, {}).get(path)

    def tree(self, namespace: str) -> dict:
        paths = sorted(self._pages.get(namespace, {}))
        return {
            "namespace": namespace,
            "count": len(paths),
            "pages": paths,
        }

    def count(self, namespace: str) -> int:
        return len(self._pages.get(namespace, {}))
