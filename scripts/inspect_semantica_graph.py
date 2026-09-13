#!/usr/bin/env python
"""Probe how semantica's reasoners consume a graph — run on an env with semantica.

We want the KG (our persistent Oxigraph RDF store, surfaced as an ``rdflib.Graph`` via
``OxigraphGraphStore.rdf_graph()``) to feed semantica's reasoners directly, so the
knowledge graph, reasoning, provenance and SHACL all share one RDF substrate.

This script does NOT change anything — it prints the exact signatures and runs tiny
probes so the graph<->reasoner wiring can be written against the real 0.6.8 API instead
of guessed. Paste its output back.

    pip install -e ".[semantica,graph]"
    python scripts/inspect_semantica_graph.py
"""

from __future__ import annotations

import inspect
import traceback


def show(label, obj):
    print(f"\n=== {label} ===")
    try:
        print("signature:", inspect.signature(obj))
    except (TypeError, ValueError):
        pass
    doc = (inspect.getdoc(obj) or "").strip()
    if doc:
        print("doc:", doc.splitlines()[0][:200])


def members(label, obj):
    print(f"\n=== {label} public members ===")
    print([m for m in dir(obj) if not m.startswith("_")])


def probe(label, fn):
    print(f"\n--- probe: {label} ---")
    try:
        fn()
    except Exception:
        print("EXC:")
        traceback.print_exc()


def main() -> None:
    import semantica  # noqa: F401
    from semantica import reasoning

    print("semantica version:", getattr(__import__("semantica"), "__version__", "?"))
    members("semantica.reasoning", reasoning)

    from semantica.reasoning import DatalogReasoner, GraphReasoner, SPARQLReasoner

    for cls in (DatalogReasoner, SPARQLReasoner, GraphReasoner):
        show(cls.__name__, cls)
        members(f"{cls.__name__} instance", cls.__new__(cls))
        for meth in ("load_from_graph", "add_graph", "query", "reason", "derive_all",
                     "execute", "ask", "run"):
            fn = getattr(cls, meth, None)
            if fn:
                show(f"{cls.__name__}.{meth}", fn)

    # Build a tiny rdflib graph exactly like OxigraphGraphStore.rdf_graph() returns.
    import rdflib

    g = rdflib.Graph()
    g.parse(data="""
        @prefix ex: <http://semantic-fabric/ex#> .
        ex:Aviva ex:offers ex:ISA .
        ex:ISA a ex:Product .
    """, format="turtle")
    print("\nrdflib graph triples:", len(g))

    # Does DatalogReasoner ingest an rdflib.Graph?
    probe("DatalogReasoner().load_from_graph(rdflib.Graph)", lambda: (
        _r := DatalogReasoner(), _r.load_from_graph(g),
        print("derive_all ->", _r.derive_all()[:10])
    ))

    # Does SPARQLReasoner take a graph (rdflib or store) and answer SPARQL?
    def _sparql():
        try:
            r = SPARQLReasoner(g)
        except Exception:
            r = SPARQLReasoner()
            for m in ("load_from_graph", "add_graph", "load"):
                if hasattr(r, m):
                    getattr(r, m)(g)
                    print("loaded via", m)
                    break
        q = "PREFIX ex: <http://semantic-fabric/ex#> SELECT ?o WHERE { ex:Aviva ex:offers ?o }"
        for m in ("query", "reason", "execute", "ask", "run"):
            if hasattr(r, m):
                print(f"{m} ->", getattr(r, m)(q))
                break
    probe("SPARQLReasoner over rdflib.Graph", _sparql)

    # Can pyoxigraph's own SPARQL feed semantica instead (skip the rdflib copy)?
    probe("pyoxigraph availability for direct SPARQL", lambda: print(
        "pyoxigraph", __import__("pyoxigraph").__version__))


if __name__ == "__main__":
    main()
