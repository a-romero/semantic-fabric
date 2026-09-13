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

import re
from collections import deque
from pathlib import PurePosixPath
from typing import Protocol


def datalog_const(s: str) -> str:
    """Normalize an arbitrary label (entity name, page path) to a Datalog constant.

    Datalog constants are lowercase alnum/underscore tokens starting with a letter, so
    ``"Enhanced Pension Annuity"`` -> ``enhanced_pension_annuity`` and
    ``"investments/isas/index.md"`` -> ``investments_isas_index_md``. Predicates are
    normalized the same way (extraction already emits snake_case predicates).
    """
    c = re.sub(r"[^a-z0-9]+", "_", str(s).strip().lower()).strip("_")
    if not c:
        return "x"
    return c if c[0].isalpha() else f"e_{c}"


class GraphStore(Protocol):
    def add_page(
        self, path: str, title: str, summary: str, topics: list[str], section: str
    ) -> None: ...

    def add_entity(self, name: str, etype: str, page_path: str | None = None) -> None: ...

    def add_relation(self, subject: str, predicate: str, obj: str) -> None: ...

    def expand(
        self, seed: str, hops: int = 1, rel_types: list[str] | None = None, limit: int = 10
    ) -> list[dict]:
        """Return connected pages as dicts: {path, title, summary, relation, distance}."""
        ...

    def facts(self) -> list[str]:
        """The knowledge graph as Datalog atoms for reasoning over the KG itself."""
        ...


def _norm_topics(topics: list[str]) -> set[str]:
    return {t.strip().lower() for t in topics if t and t.strip()}


def nearest_parent(path: str, page_paths) -> str | None:
    """Nearest ancestor page (…/index.md) above ``path`` within ``page_paths``.

    Shared by the in-memory and RDF backends so path-derived hierarchy is identical.
    """
    parent_dir = PurePosixPath(path).parent.parent  # skip the page's own dir
    while str(parent_dir) not in (".", "/", ""):
        candidate = str(parent_dir / "index.md")
        if candidate in page_paths and candidate != path:
            return candidate
        parent_dir = parent_dir.parent
    return None


class InMemoryGraphStore:
    """Pure-Python page graph. Default backend; no external service."""

    HIERARCHY = "hierarchy"
    TOPIC = "topic"
    ENTITY = "entity"      # pages sharing an extracted entity
    RELATION = "relation"  # pages connected through an extracted relation

    def __init__(self) -> None:
        # path -> {title, summary, topics: set[str], section}
        self._pages: dict[str, dict] = {}
        # extracted-KG state (populated when extraction is wired into ingestion)
        self._page_entities: dict[str, set[str]] = {}   # path -> entity names
        self._entity_pages: dict[str, set[str]] = {}    # entity name -> paths
        self._entity_types: dict[str, str] = {}         # entity name -> type
        self._relations: set[tuple[str, str, str]] = set()  # (subject, predicate, object)

    def add_page(
        self, path: str, title: str, summary: str, topics: list[str], section: str
    ) -> None:
        self._pages[path] = {
            "title": title,
            "summary": summary,
            "topics": _norm_topics(topics),
            "section": section,
        }

    # -- extracted knowledge graph (from LLM extraction at ingest) --------
    def add_entity(self, name: str, etype: str, page_path: str | None = None) -> None:
        name = name.strip()
        if not name:
            return
        self._entity_types.setdefault(name, etype or "Unknown")
        if page_path:
            self._page_entities.setdefault(page_path, set()).add(name)
            self._entity_pages.setdefault(name, set()).add(page_path)

    def add_relation(self, subject: str, predicate: str, obj: str) -> None:
        subject, obj = subject.strip(), obj.strip()
        if not subject or not obj:
            return
        self._entity_types.setdefault(subject, "Unknown")
        self._entity_types.setdefault(obj, "Unknown")
        self._relations.add((subject, predicate.strip() or "related_to", obj))

    def _related_entities(self, entity: str) -> list[tuple[str, str]]:
        """Entities directly related to `entity`, with the predicate."""
        out: list[tuple[str, str]] = []
        for s, p, o in self._relations:
            if s == entity:
                out.append((o, p))
            elif o == entity:
                out.append((s, p))
        return out

    # -- edge derivation --------------------------------------------------
    def _parent(self, path: str) -> str | None:
        """Nearest ancestor page (…/index.md) above this path, if any."""
        return nearest_parent(path, self._pages)

    def _edges(self, path: str, rel_types: list[str] | None) -> list[tuple[str, str]]:
        want = set(rel_types) if rel_types else {
            self.HIERARCHY, self.TOPIC, self.ENTITY, self.RELATION
        }
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
        my_entities = self._page_entities.get(path, set())
        if self.ENTITY in want and my_entities:
            # pages that share an extracted entity with this page
            for ent in my_entities:
                for other in self._entity_pages.get(ent, set()):
                    if other != path:
                        edges.append((other, f"shared-entity:{ent}"))
        if self.RELATION in want and my_entities:
            # pages reached through an extracted relation on one of this page's entities
            for ent in my_entities:
                for related, predicate in self._related_entities(ent):
                    for other in self._entity_pages.get(related, set()):
                        if other != path:
                            edges.append((other, f"relation:{predicate}"))
        return edges

    # -- traversal --------------------------------------------------------
    def _resolve_seed(self, seed: str) -> dict[str, tuple[int, str]]:
        """Map a seed to an initial frontier: {path: (distance, relation)}."""
        seed = seed.strip()
        if seed in self._pages:
            return {seed: (0, "seed")}
        # seed as an extracted entity name -> pages mentioning it (distance 1)
        if seed in self._entity_pages:
            return {p: (1, f"entity:{seed}") for p in self._entity_pages[seed]}
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

    def facts(self) -> list[str]:
        out: list[str] = []
        for s, p, o in self._relations:
            out.append(f"{datalog_const(p)}({datalog_const(s)}, {datalog_const(o)})")
        for page, ents in self._page_entities.items():
            for e in ents:
                out.append(f"mentions({datalog_const(page)}, {datalog_const(e)})")
        for path in self._pages:
            parent = self._parent(path)
            if parent:
                out.append(f"parent({datalog_const(path)}, {datalog_const(parent)})")
        return sorted(set(out))

    def __len__(self) -> int:
        return len(self._pages)


def build_graph_store(kind: str | None) -> GraphStore:
    """Factory from a GRAPH_STORE value. 'memory' (default) is dependency-free.

    'rdf' selects the persistent, SPARQL-native Oxigraph backend (``.[graph]`` extra),
    durable at ``GRAPH_DB_PATH`` — the store that shares semantica's RDF/SPARQL model.
    It falls back to in-memory if pyoxigraph is not installed, so the default install
    and CI stay dependency-free.
    """
    import os

    choice = (kind or "memory").strip().lower()
    if choice in {"rdf", "oxigraph"}:
        try:
            from .oxigraph_backend import OxigraphGraphStore

            return OxigraphGraphStore(os.getenv("GRAPH_DB_PATH") or "./graph-oxigraph")
        except Exception:
            return InMemoryGraphStore()
    return InMemoryGraphStore()
