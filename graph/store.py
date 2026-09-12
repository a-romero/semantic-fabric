"""Graph store for GraphRAG expansion — the third retrieval leg.

Phase 1 builds a lightweight page graph at ingest time from what the authored KB
already gives us for free, no NER required:

- **hierarchy** edges (parent/child) from the path structure — the same promotion of
  skilled-agent's CHILD_OF taxonomy described in the design;
- **shared-topic** edges between pages that share a frontmatter topic/keyword.

``expand(seed, hops)`` walks from a seed (a page path, or a topic/keyword) to
connected pages, so an answer pulls in related material that pure vector/BM25 search
would miss. Entity/relation extraction and a persistent LPG (Kuzu) / RDF (Oxigraph)
backend arrive with later phases; the InMemoryGraphStore keeps the default install
dependency-free and CI-testable.
"""

from __future__ import annotations

from collections import deque
from pathlib import PurePosixPath
from typing import Protocol


class GraphStore(Protocol):
    def add_page(
        self, path: str, title: str, summary: str, topics: list[str], section: str
    ) -> None: ...

    def expand(
        self, seed: str, hops: int = 1, rel_types: list[str] | None = None, limit: int = 10
    ) -> list[dict]:
        """Return connected pages as dicts: {path, title, summary, relation, distance}."""
        ...


def _norm_topics(topics: list[str]) -> set[str]:
    return {t.strip().lower() for t in topics if t and t.strip()}


class InMemoryGraphStore:
    """Pure-Python page graph. Default backend; no external service."""

    HIERARCHY = "hierarchy"
    TOPIC = "topic"

    def __init__(self) -> None:
        # path -> {title, summary, topics: set[str], section}
        self._pages: dict[str, dict] = {}

    def add_page(
        self, path: str, title: str, summary: str, topics: list[str], section: str
    ) -> None:
        self._pages[path] = {
            "title": title,
            "summary": summary,
            "topics": _norm_topics(topics),
            "section": section,
        }

    # -- edge derivation --------------------------------------------------
    def _parent(self, path: str) -> str | None:
        """Nearest ancestor page (…/index.md) above this path, if any."""
        parent_dir = PurePosixPath(path).parent.parent  # skip the page's own dir
        while str(parent_dir) not in (".", "/", ""):
            candidate = str(parent_dir / "index.md")
            if candidate in self._pages and candidate != path:
                return candidate
            parent_dir = parent_dir.parent
        return None

    def _edges(self, path: str, rel_types: list[str] | None) -> list[tuple[str, str]]:
        want = set(rel_types) if rel_types else {self.HIERARCHY, self.TOPIC}
        edges: list[tuple[str, str]] = []
        if self.HIERARCHY in want:
            parent = self._parent(path)
            if parent:
                edges.append((parent, "parent"))
            for other in self._pages:
                if other != path and self._parent(other) == path:
                    edges.append((other, "child"))
        if self.TOPIC in want:
            mine = self._pages[path]["topics"]
            if mine:
                for other, meta in self._pages.items():
                    if other == path:
                        continue
                    shared = mine & meta["topics"]
                    if shared:
                        edges.append((other, f"shared-topic:{sorted(shared)[0]}"))
        return edges

    # -- traversal --------------------------------------------------------
    def _resolve_seed(self, seed: str) -> dict[str, tuple[int, str]]:
        """Map a seed to an initial frontier: {path: (distance, relation)}."""
        seed = seed.strip()
        if seed in self._pages:
            return {seed: (0, "seed")}
        token = seed.lower().removeprefix("topic:")
        frontier: dict[str, tuple[int, str]] = {}
        for path, meta in self._pages.items():
            if any(token in t for t in meta["topics"]):
                frontier[path] = (1, f"topic:{token}")
        return frontier

    def expand(
        self, seed: str, hops: int = 1, rel_types: list[str] | None = None, limit: int = 10
    ) -> list[dict]:
        if not self._pages:
            return []
        visited = self._resolve_seed(seed)
        if not visited:
            return []
        queue: deque[str] = deque(visited.keys())
        seed_is_page = seed.strip() in self._pages
        while queue:
            path = queue.popleft()
            dist, _rel = visited[path]
            if dist >= hops:
                continue
            for neighbour, relation in self._edges(path, rel_types):
                if neighbour not in visited:
                    visited[neighbour] = (dist + 1, relation)
                    queue.append(neighbour)

        results: list[dict] = []
        for path, (dist, relation) in visited.items():
            if seed_is_page and dist == 0:
                continue  # exclude the seed page itself
            meta = self._pages[path]
            results.append(
                {
                    "path": path,
                    "title": meta["title"],
                    "summary": meta["summary"],
                    "relation": relation,
                    "distance": dist,
                }
            )
        results.sort(key=lambda r: (r["distance"], r["title"]))
        return results[:limit]

    def __len__(self) -> int:
        return len(self._pages)


def build_graph_store(kind: str | None) -> GraphStore:
    """Factory from a GRAPH_STORE value. 'memory' (default) is dependency-free.

    'lpg' (Kuzu) and 'rdf' (Oxigraph) backends are wired with the real-backend and
    reasoning phases respectively; until then they fall back to in-memory.
    """
    choice = (kind or "memory").strip().lower()
    if choice in {"memory", "inmemory", "in_memory"}:
        return InMemoryGraphStore()
    # lpg/rdf backends not yet wired; in-memory keeps behaviour correct meanwhile.
    return InMemoryGraphStore()
