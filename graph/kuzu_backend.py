"""Persistent LPG graph store backed by Kuzu (optional; ``.[graph]`` extra).

Kuzu is the durable store of record: every page, entity, mention and relation is
written through to an embedded Kuzu database, and reloaded into memory on startup so
the graph survives restarts. GraphRAG traversal (``expand``) reuses the validated
``InMemoryGraphStore`` logic over that loaded view — the hierarchy (path-derived) and
shared-topic edges are computed in Python, matching the default backend exactly, while
Kuzu owns durability and the raw node/relationship representation.

Schema (created if absent):
    Page(path PK, title, summary, topics_json, section)
    Entity(name PK, etype)
    (Page)-[:MENTIONS]->(Entity)
    (Entity)-[:REL {predicate}]->(Entity)

Selected by ``GRAPH_STORE=lpg`` with ``GRAPH_DB_PATH`` (defaults to ./graph-kuzu).
"""

from __future__ import annotations

import json

from .store import InMemoryGraphStore, _norm_topics


class KuzuGraphStore(InMemoryGraphStore):
    def __init__(self, db_path: str = "./graph-kuzu") -> None:
        super().__init__()
        import kuzu  # type: ignore

        self._db = kuzu.Database(db_path)
        self._conn = kuzu.Connection(self._db)
        self._init_schema()
        self._load()

    # -- schema / load --------------------------------------------------------
    def _init_schema(self) -> None:
        for stmt in (
            "CREATE NODE TABLE IF NOT EXISTS Page("
            "path STRING, title STRING, summary STRING, topics_json STRING, "
            "section STRING, PRIMARY KEY(path))",
            "CREATE NODE TABLE IF NOT EXISTS Entity(name STRING, etype STRING, PRIMARY KEY(name))",
            "CREATE REL TABLE IF NOT EXISTS MENTIONS(FROM Page TO Entity)",
            "CREATE REL TABLE IF NOT EXISTS REL(FROM Entity TO Entity, predicate STRING)",
        ):
            self._conn.execute(stmt)

    @staticmethod
    def _rows(result) -> list[list]:
        out = []
        while result.has_next():
            out.append(result.get_next())
        return out

    def _load(self) -> None:
        for path, title, summary, topics_json, section in self._rows(
            self._conn.execute(
                "MATCH (p:Page) RETURN p.path, p.title, p.summary, p.topics_json, p.section"
            )
        ):
            super().add_page(
                path=path, title=title or path, summary=summary or "",
                topics=json.loads(topics_json or "[]"), section=section or "",
            )
        for name, etype in self._rows(
            self._conn.execute("MATCH (e:Entity) RETURN e.name, e.etype")
        ):
            self._entity_types.setdefault(name, etype or "Unknown")
        for path, name in self._rows(
            self._conn.execute("MATCH (p:Page)-[:MENTIONS]->(e:Entity) RETURN p.path, e.name")
        ):
            self._page_entities.setdefault(path, set()).add(name)
            self._entity_pages.setdefault(name, set()).add(path)
        for s, pred, o in self._rows(
            self._conn.execute(
                "MATCH (a:Entity)-[r:REL]->(b:Entity) RETURN a.name, r.predicate, b.name"
            )
        ):
            self._relations.add((s, pred or "related_to", o))

    # -- write-through mutations ---------------------------------------------
    def add_page(
        self, path: str, title: str, summary: str, topics: list[str], section: str
    ) -> None:
        super().add_page(path=path, title=title, summary=summary, topics=topics, section=section)
        self._conn.execute(
            "MERGE (p:Page {path: $path}) "
            "SET p.title = $title, p.summary = $summary, p.topics_json = $topics, "
            "p.section = $section",
            {
                "path": path, "title": title, "summary": summary,
                "topics": json.dumps(sorted(_norm_topics(topics))), "section": section,
            },
        )

    def add_entity(self, name: str, etype: str, page_path: str | None = None) -> None:
        name = name.strip()
        if not name:
            return
        super().add_entity(name, etype, page_path=page_path)
        self._conn.execute(
            "MERGE (e:Entity {name: $name}) SET e.etype = coalesce(e.etype, $etype)",
            {"name": name, "etype": etype or "Unknown"},
        )
        if page_path:
            self._conn.execute(
                "MATCH (p:Page {path: $path}), (e:Entity {name: $name}) "
                "MERGE (p)-[:MENTIONS]->(e)",
                {"path": page_path, "name": name},
            )

    def add_relation(self, subject: str, predicate: str, obj: str) -> None:
        subject, obj = subject.strip(), obj.strip()
        if not subject or not obj:
            return
        predicate = predicate.strip() or "related_to"
        super().add_relation(subject, predicate, obj)
        for n in (subject, obj):
            self._conn.execute("MERGE (e:Entity {name: $name})", {"name": n})
        self._conn.execute(
            "MATCH (a:Entity {name: $s}), (b:Entity {name: $o}) "
            "MERGE (a)-[r:REL {predicate: $p}]->(b)",
            {"s": subject, "o": obj, "p": predicate},
        )
