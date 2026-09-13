"""Persistent, SPARQL-native RDF graph store backed by Oxigraph (``.[graph]`` extra).

This is the graph backend that *adheres to semantica's own model*: RDF triples queried
with SPARQL. The knowledge graph, semantica's provenance (PROV-O), reasoning (Datalog /
SPARQL) and SHACL all speak the same substrate, so the graph is one coherent semantic
plane rather than a second, disconnected store.

- Storage: an on-disk Oxigraph store (``pyoxigraph.Store(path)``) — durable, survives
  restarts, and independently SPARQL-queryable.
- Traversal (``expand``): every edge lookup is a **SPARQL query** over the RDF graph
  (a UNION of the hierarchy / shared-topic / shared-entity / relation patterns). The
  multi-hop frontier (distance + first-relation labelling) is composed in Python around
  those SPARQL neighbour queries, matching the in-memory backend's semantics exactly.
- Hierarchy is materialised as ``ex:parentPage`` triples (derived from the path
  structure via the shared ``nearest_parent`` helper) so it is queryable like any edge.
- ``rdf_graph()`` returns an ``rdflib.Graph`` snapshot for semantica's reasoners, and
  ``sparql(query)`` exposes arbitrary SPARQL — capabilities an LPG/Cypher store can't
  offer the rest of the semantic stack.

Vocabulary (all under ``http://semantic-fabric/ex#``):
    <page/{path}>   a ex:Page ; ex:path "…" ; rdfs:label "…" ; ex:summary "…" ;
                    ex:section "…" ; ex:topic "…" (repeatable) ; ex:parentPage <page/…>
    <entity/{name}> a ex:Entity ; ex:name "…" ; ex:etype "…"
    <page/…> ex:mentions <entity/…>
    <rel/{s}/{p}/{o}> a ex:Relation ; ex:relSubject <entity/s> ;
                      ex:relPredicate "p" ; ex:relObject <entity/o>

Selected by ``GRAPH_STORE=rdf`` with ``GRAPH_DB_PATH`` (defaults to ./graph-oxigraph).
"""

from __future__ import annotations

from urllib.parse import quote

from .store import GraphStore, datalog_const, nearest_parent

EX = "http://semantic-fabric/ex#"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
RDFS_LABEL = "http://www.w3.org/2000/01/rdf-schema#label"


class OxigraphGraphStore(GraphStore):
    def __init__(self, db_path: str = "./graph-oxigraph") -> None:
        import pyoxigraph as ox  # type: ignore

        self._ox = ox
        self._store = ox.Store(db_path)

    # -- term / IRI helpers ---------------------------------------------------
    @staticmethod
    def _page_iri(path: str) -> str:
        return f"{EX}page/{quote(path, safe='')}"

    @staticmethod
    def _entity_iri(name: str) -> str:
        return f"{EX}entity/{quote(name, safe='')}"

    def _n(self, iri: str):
        return self._ox.NamedNode(iri)

    def _lit(self, value: str):
        return self._ox.Literal(value)

    def _add(self, s: str, p: str, o) -> None:
        obj = o if not isinstance(o, str) else self._n(o)
        self._store.add(self._ox.Quad(self._n(s), self._n(p), obj))

    def _remove_props(self, s: str, *props: str) -> None:
        for p in props:
            for q in list(self._store.quads_for_pattern(self._n(s), self._n(p), None, None)):
                self._store.remove(q)

    def _ask(self, where: str) -> bool:
        return bool(self._store.query(f"PREFIX ex: <{EX}> ASK {{ {where} }}"))

    def _select(self, query: str) -> list[dict]:
        res = self._store.query(f"PREFIX ex: <{EX}> PREFIX rdfs: <{RDFS_LABEL[:-5]}> {query}")
        names = [v.value for v in res.variables]
        out = []
        for sol in res:
            row = {}
            for name in names:
                term = sol[name]
                row[name] = term.value if term is not None else None
            out.append(row)
        return out

    # -- mutations (write-through to the RDF store) ---------------------------
    def add_page(
        self, path: str, title: str, summary: str, topics: list[str], section: str
    ) -> None:
        from .store import _norm_topics

        s = self._page_iri(path)
        self._remove_props(s, RDFS_LABEL, f"{EX}summary", f"{EX}section", f"{EX}topic")
        self._add(s, RDF_TYPE, f"{EX}Page")
        self._add(s, f"{EX}path", self._lit(path))
        self._add(s, RDFS_LABEL, self._lit(title))
        self._add(s, f"{EX}summary", self._lit(summary))
        self._add(s, f"{EX}section", self._lit(section))
        for t in sorted(_norm_topics(topics)):
            self._add(s, f"{EX}topic", self._lit(t))
        self._materialise_hierarchy(path)
        self._store.flush()

    def _all_page_paths(self) -> set[str]:
        return {r["p"] for r in self._select("SELECT ?p WHERE { ?pg ex:path ?p }")}

    def _materialise_hierarchy(self, new_path: str) -> None:
        """(Re)derive ex:parentPage edges affected by adding ``new_path``."""
        paths = self._all_page_paths()
        # This page's parent.
        self._remove_props(self._page_iri(new_path), f"{EX}parentPage")
        parent = nearest_parent(new_path, paths)
        if parent:
            self._add(self._page_iri(new_path), f"{EX}parentPage", self._page_iri(parent))
        # Existing pages whose nearest parent is now this page.
        for other in paths:
            if other == new_path:
                continue
            if nearest_parent(other, paths) == new_path:
                self._remove_props(self._page_iri(other), f"{EX}parentPage")
                self._add(self._page_iri(other), f"{EX}parentPage", self._page_iri(new_path))

    def add_entity(self, name: str, etype: str, page_path: str | None = None) -> None:
        name = name.strip()
        if not name:
            return
        s = self._entity_iri(name)
        self._add(s, RDF_TYPE, f"{EX}Entity")
        self._add(s, f"{EX}name", self._lit(name))
        if not self._ask(f"<{s}> ex:etype ?t"):
            self._add(s, f"{EX}etype", self._lit(etype or "Unknown"))
        if page_path:
            self._add(self._page_iri(page_path), f"{EX}mentions", s)
        self._store.flush()

    def add_relation(self, subject: str, predicate: str, obj: str) -> None:
        subject, obj = subject.strip(), obj.strip()
        if not subject or not obj:
            return
        predicate = predicate.strip() or "related_to"
        for n in (subject, obj):
            e = self._entity_iri(n)
            self._add(e, RDF_TYPE, f"{EX}Entity")
            if not self._ask(f"<{e}> ex:name ?nm"):
                self._add(e, f"{EX}name", self._lit(n))
        rel = f"{EX}rel/{quote(subject, safe='')}/{quote(predicate, safe='')}/{quote(obj, safe='')}"
        self._add(rel, RDF_TYPE, f"{EX}Relation")
        self._add(rel, f"{EX}relSubject", self._entity_iri(subject))
        self._add(rel, f"{EX}relPredicate", self._lit(predicate))
        self._add(rel, f"{EX}relObject", self._entity_iri(obj))
        self._store.flush()

    # -- SPARQL-native traversal ---------------------------------------------
    _EDGE_TEMPLATES = {
        "hierarchy": (
            "{{ <{p}> ex:parentPage ?n . BIND('parent' AS ?rel) }}"
            " UNION {{ ?n ex:parentPage <{p}> . BIND('child' AS ?rel) }}"
        ),
        "topic": (
            "{{ <{p}> ex:topic ?t . ?n ex:topic ?t . ?n ex:path ?np . FILTER(?n != <{p}>)"
            " BIND(CONCAT('shared-topic:', ?t) AS ?rel) }}"
        ),
        "entity": (
            "{{ <{p}> ex:mentions ?e . ?e ex:name ?en . ?n ex:mentions ?e . ?n ex:path ?np ."
            " FILTER(?n != <{p}>) BIND(CONCAT('shared-entity:', ?en) AS ?rel) }}"
        ),
        "relation": (
            "{{ <{p}> ex:mentions ?e1 ."
            " {{ ?r ex:relSubject ?e1 ; ex:relPredicate ?pr ; ex:relObject ?e2 }}"
            " UNION {{ ?r ex:relObject ?e1 ; ex:relPredicate ?pr ; ex:relSubject ?e2 }}"
            " ?n ex:mentions ?e2 . ?n ex:path ?np . FILTER(?n != <{p}>)"
            " BIND(CONCAT('relation:', ?pr) AS ?rel) }}"
        ),
    }

    def _neighbours(self, path: str, rel_types: list[str] | None) -> list[tuple[str, str]]:
        want = rel_types or list(self._EDGE_TEMPLATES)
        blocks = [self._EDGE_TEMPLATES[k].format(p=self._page_iri(path))
                  for k in want if k in self._EDGE_TEMPLATES]
        if not blocks:
            return []
        query = "SELECT DISTINCT ?n ?rel WHERE { " + " UNION ".join(blocks) + " }"
        seen: dict[str, str] = {}
        for row in self._select(query):
            npath = self._path_of(row["n"])
            if npath and npath not in seen:
                seen[npath] = row["rel"]
        return list(seen.items())

    def _path_of(self, page_iri: str | None) -> str | None:
        if not page_iri:
            return None
        rows = self._select(f"SELECT ?p WHERE {{ <{page_iri}> ex:path ?p }}")
        return rows[0]["p"] if rows else None

    def _page_meta(self, path: str) -> dict:
        rows = self._select(
            f"SELECT ?title ?summary WHERE {{ <{self._page_iri(path)}> "
            f"rdfs:label ?title ; ex:summary ?summary }}"
        )
        r = rows[0] if rows else {}
        return {"title": r.get("title") or path, "summary": r.get("summary") or ""}

    def _resolve_seed(self, seed: str) -> dict[str, tuple[int, str]]:
        seed = seed.strip()
        if self._ask(f"?pg ex:path '{_esc(seed)}'"):
            return {seed: (0, "seed")}
        # seed as an entity name -> pages mentioning it (distance 1)
        ent_pages = self._select(
            f"SELECT ?p WHERE {{ ?e ex:name '{_esc(seed)}' . ?pg ex:mentions ?e . ?pg ex:path ?p }}"
        )
        if ent_pages:
            return {r["p"]: (1, f"entity:{seed}") for r in ent_pages}
        token = seed.lower().removeprefix("topic:")
        rows = self._select(
            f"SELECT ?p WHERE {{ ?pg ex:topic ?t . ?pg ex:path ?p ."
            f" FILTER(CONTAINS(?t, '{_esc(token)}')) }}"
        )
        return {r["p"]: (1, f"topic:{token}") for r in rows}

    def expand(
        self, seed: str, hops: int = 1, rel_types: list[str] | None = None, limit: int = 10
    ) -> list[dict]:
        if not self._ask("?pg ex:path ?p"):  # empty graph
            return []
        visited = self._resolve_seed(seed)
        if not visited:
            return []
        from collections import deque

        queue: deque[str] = deque(visited.keys())
        seed_is_page = seed.strip() in visited and visited[seed.strip()][0] == 0
        while queue:
            path = queue.popleft()
            dist, _rel = visited[path]
            if dist >= hops:
                continue
            for neighbour, relation in self._neighbours(path, rel_types):
                if neighbour not in visited:
                    visited[neighbour] = (dist + 1, relation)
                    queue.append(neighbour)

        results: list[dict] = []
        for path, (dist, relation) in visited.items():
            if seed_is_page and dist == 0:
                continue
            meta = self._page_meta(path)
            results.append({
                "path": path, "title": meta["title"], "summary": meta["summary"],
                "relation": relation, "distance": dist,
            })
        results.sort(key=lambda r: (r["distance"], r["title"]))
        return results[:limit]

    def facts(self) -> list[str]:
        """The RDF KG as Datalog atoms, gathered by SPARQL over the graph."""
        out: list[str] = []
        for r in self._select(
            "SELECT ?sn ?p ?on WHERE { ?rel a ex:Relation ; ex:relSubject ?s ;"
            " ex:relPredicate ?p ; ex:relObject ?o . ?s ex:name ?sn . ?o ex:name ?on }"
        ):
            out.append(
                f"{datalog_const(r['p'])}({datalog_const(r['sn'])}, {datalog_const(r['on'])})"
            )
        for r in self._select(
            "SELECT ?path ?en WHERE { ?pg ex:path ?path ; ex:mentions ?e . ?e ex:name ?en }"
        ):
            out.append(f"mentions({datalog_const(r['path'])}, {datalog_const(r['en'])})")
        for r in self._select(
            "SELECT ?cp ?pp WHERE { ?c ex:parentPage ?p . ?c ex:path ?cp . ?p ex:path ?pp }"
        ):
            out.append(f"parent({datalog_const(r['cp'])}, {datalog_const(r['pp'])})")
        return sorted(set(out))

    # -- semantica interop / raw SPARQL --------------------------------------
    def sparql(self, query: str):
        """Run an arbitrary SPARQL query against the RDF graph."""
        return self._store.query(query)

    def rdf_graph(self):
        """Materialise the graph as an ``rdflib.Graph`` for semantica's reasoners."""
        import rdflib  # type: ignore

        nt = self._store.dump(
            format=self._ox.RdfFormat.N_TRIPLES, from_graph=self._ox.DefaultGraph()
        )
        if isinstance(nt, (bytes, bytearray)):
            nt = nt.decode()
        g = rdflib.Graph()
        g.parse(data=nt, format="nt")
        return g


def _esc(value: str) -> str:
    """Escape a string literal for inlining into a SPARQL query."""
    return value.replace("\\", "\\\\").replace("'", "\\'")
