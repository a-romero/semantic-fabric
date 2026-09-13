"""Persistent RDF graph store backed by Oxigraph (optional; ``.[graph]`` extra).

Oxigraph is the durable RDF store of record: pages, entities and relations are written
as triples (a small ``ex:`` vocabulary) into an on-disk Oxigraph store and reloaded on
startup, so the graph survives restarts. GraphRAG traversal (``expand``) reuses the
validated ``InMemoryGraphStore`` logic over the loaded view — matching the default
backend's edge semantics — while Oxigraph owns durability and the RDF representation
(so the same graph is SPARQL-queryable outside this service).

Vocabulary (all under ``http://semantic-fabric/ex#``):
    <page/{path}>   a ex:Page ; ex:path "…" ; rdfs:label "…" ; ex:summary "…" ;
                    ex:section "…" ; ex:topic "…" (repeatable)
    <entity/{name}> a ex:Entity ; ex:name "…" ; ex:etype "…"
    <page/…> ex:mentions <entity/…>
    <rel/{s}|{p}|{o}> a ex:Relation ; ex:subject <entity/s> ;
                      ex:predicate "p" ; ex:object <entity/o>

Selected by ``GRAPH_STORE=rdf`` with ``GRAPH_DB_PATH`` (defaults to ./graph-oxigraph).
"""

from __future__ import annotations

from urllib.parse import quote, unquote

from .store import InMemoryGraphStore, _norm_topics

EX = "http://semantic-fabric/ex#"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
RDFS_LABEL = "http://www.w3.org/2000/01/rdf-schema#label"


class OxigraphGraphStore(InMemoryGraphStore):
    def __init__(self, db_path: str = "./graph-oxigraph") -> None:
        super().__init__()
        import pyoxigraph as ox  # type: ignore

        self._ox = ox
        self._store = ox.Store(db_path)
        self._load()

    # -- term helpers ---------------------------------------------------------
    def _n(self, iri: str):
        return self._ox.NamedNode(iri)

    def _lit(self, value: str):
        return self._ox.Literal(value)

    def _page_iri(self, path: str) -> str:
        return f"{EX}page/{quote(path, safe='')}"

    def _entity_iri(self, name: str) -> str:
        return f"{EX}entity/{quote(name, safe='')}"

    def _add(self, s: str, p: str, o) -> None:
        obj = o if not isinstance(o, str) else self._n(o)
        self._store.add(self._ox.Quad(self._n(s), self._n(p), obj))

    def _objects(self, s: str, p: str) -> list:
        return [q.object for q in self._store.quads_for_pattern(self._n(s), self._n(p), None, None)]

    def _first_str(self, s: str, p: str, default: str = "") -> str:
        vals = self._objects(s, p)
        return vals[0].value if vals else default

    # -- load -----------------------------------------------------------------
    def _load(self) -> None:
        page_type = self._n(f"{EX}Page")
        for q in self._store.quads_for_pattern(None, self._n(RDF_TYPE), page_type, None):
            s = q.subject.value
            path = self._first_str(s, f"{EX}path") or unquote(s.rsplit("/", 1)[-1])
            topics = [o.value for o in self._objects(s, f"{EX}topic")]
            super().add_page(
                path=path,
                title=self._first_str(s, RDFS_LABEL, path),
                summary=self._first_str(s, f"{EX}summary"),
                topics=topics,
                section=self._first_str(s, f"{EX}section"),
            )
        ent_type = self._n(f"{EX}Entity")
        for q in self._store.quads_for_pattern(None, self._n(RDF_TYPE), ent_type, None):
            s = q.subject.value
            name = self._first_str(s, f"{EX}name") or unquote(s.rsplit("/", 1)[-1])
            self._entity_types.setdefault(name, self._first_str(s, f"{EX}etype", "Unknown"))
        for q in self._store.quads_for_pattern(None, self._n(f"{EX}mentions"), None, None):
            path = unquote(q.subject.value.rsplit("/", 1)[-1])
            name = unquote(q.object.value.rsplit("/", 1)[-1])
            self._page_entities.setdefault(path, set()).add(name)
            self._entity_pages.setdefault(name, set()).add(path)
        rel_type = self._n(f"{EX}Relation")
        for q in self._store.quads_for_pattern(None, self._n(RDF_TYPE), rel_type, None):
            s = q.subject.value
            subj = self._first_str(s, f"{EX}subject_name")
            obj = self._first_str(s, f"{EX}object_name")
            pred = self._first_str(s, f"{EX}predicate", "related_to")
            if subj and obj:
                self._relations.add((subj, pred, obj))

    # -- write-through mutations ---------------------------------------------
    def add_page(
        self, path: str, title: str, summary: str, topics: list[str], section: str
    ) -> None:
        super().add_page(path=path, title=title, summary=summary, topics=topics, section=section)
        s = self._page_iri(path)
        # Replace mutable props so a re-ingest updates rather than duplicates.
        for p in (RDFS_LABEL, f"{EX}summary", f"{EX}section", f"{EX}topic"):
            for q in list(self._store.quads_for_pattern(self._n(s), self._n(p), None, None)):
                self._store.remove(q)
        self._add(s, RDF_TYPE, f"{EX}Page")
        self._add(s, f"{EX}path", self._lit(path))
        self._add(s, RDFS_LABEL, self._lit(title))
        self._add(s, f"{EX}summary", self._lit(summary))
        self._add(s, f"{EX}section", self._lit(section))
        for t in sorted(_norm_topics(topics)):
            self._add(s, f"{EX}topic", self._lit(t))

    def add_entity(self, name: str, etype: str, page_path: str | None = None) -> None:
        name = name.strip()
        if not name:
            return
        super().add_entity(name, etype, page_path=page_path)
        s = self._entity_iri(name)
        self._add(s, RDF_TYPE, f"{EX}Entity")
        self._add(s, f"{EX}name", self._lit(name))
        if not self._first_str(s, f"{EX}etype"):
            self._add(s, f"{EX}etype", self._lit(etype or "Unknown"))
        if page_path:
            self._add(self._page_iri(page_path), f"{EX}mentions", self._entity_iri(name))

    def add_relation(self, subject: str, predicate: str, obj: str) -> None:
        subject, obj = subject.strip(), obj.strip()
        if not subject or not obj:
            return
        predicate = predicate.strip() or "related_to"
        super().add_relation(subject, predicate, obj)
        for n in (subject, obj):
            e = self._entity_iri(n)
            self._add(e, RDF_TYPE, f"{EX}Entity")
            self._add(e, f"{EX}name", self._lit(n))
        rel = f"{EX}rel/{quote(subject, safe='')}|{quote(predicate, safe='')}|{quote(obj, safe='')}"
        self._add(rel, RDF_TYPE, f"{EX}Relation")
        self._add(rel, f"{EX}subject", self._entity_iri(subject))
        self._add(rel, f"{EX}subject_name", self._lit(subject))
        self._add(rel, f"{EX}predicate", self._lit(predicate))
        self._add(rel, f"{EX}object", self._entity_iri(obj))
        self._add(rel, f"{EX}object_name", self._lit(obj))
