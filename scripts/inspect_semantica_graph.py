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

    # --- SPARQLReasoner: full signatures + graph-ingestion probes ---------------
    print("\n########## SPARQLReasoner deep-dive ##########")
    show("SPARQLReasoner.__init__", SPARQLReasoner.__init__)
    for meth in ("execute_query", "infer_results", "expand_query",
                 "add_inference_rule", "clear_cache"):
        fn = getattr(SPARQLReasoner, meth, None)
        if fn:
            show(f"SPARQLReasoner.{meth}", fn)

    Q = "PREFIX ex: <http://semantic-fabric/ex#> SELECT ?o WHERE { ex:Aviva ex:offers ?o }"

    # (1) graph via constructor, then execute_query(query)
    def _ctor_graph():
        r = SPARQLReasoner(g)
        print("execute_query(Q) ->", r.execute_query(Q))
    probe("SPARQLReasoner(rdflib.Graph).execute_query(Q)", _ctor_graph)

    # (2) graph via constructor config dict
    def _ctor_config():
        r = SPARQLReasoner(config={"graph": g})
        print("execute_query(Q) ->", r.execute_query(Q))
    probe("SPARQLReasoner(config={'graph': g}).execute_query(Q)", _ctor_config)

    # (3) no-arg ctor, graph passed to execute_query (kwarg + positional)
    def _query_graph_kwarg():
        r = SPARQLReasoner()
        print("execute_query(Q, graph=g) ->", r.execute_query(Q, graph=g))
    probe("SPARQLReasoner().execute_query(Q, graph=g)", _query_graph_kwarg)

    def _query_graph_pos():
        r = SPARQLReasoner()
        print("execute_query(Q, g) ->", r.execute_query(Q, g))
    probe("SPARQLReasoner().execute_query(Q, g) [positional]", _query_graph_pos)

    # (4) does it accept a pyoxigraph Store or a SPARQL-endpoint URL instead of rdflib?
    def _oxi_store():
        import pyoxigraph as ox
        s = ox.Store()
        s.add(ox.Quad(ox.NamedNode("http://semantic-fabric/ex#Aviva"),
                      ox.NamedNode("http://semantic-fabric/ex#offers"),
                      ox.NamedNode("http://semantic-fabric/ex#ISA")))
        r = SPARQLReasoner(s)
        print("execute_query(Q) over pyoxigraph.Store ->", r.execute_query(Q))
    probe("SPARQLReasoner(pyoxigraph.Store).execute_query(Q)", _oxi_store)

    # (5) infer_results — forward inference then materialised triples/results?
    def _infer():
        r = SPARQLReasoner(g)
        print("infer_results() ->", r.infer_results())
    probe("SPARQLReasoner(g).infer_results()", _infer)

    # (6) add_inference_rule shape (SPARQL CONSTRUCT? rule object? then infer)
    def _add_rule_then_infer():
        r = SPARQLReasoner(g)
        rule = ("PREFIX ex: <http://semantic-fabric/ex#> "
                "CONSTRUCT { ?x ex:insurable true } WHERE { ex:Aviva ex:offers ?x }")
        r.add_inference_rule(rule)
        print("infer_results() after CONSTRUCT rule ->", r.infer_results())
    probe("SPARQLReasoner(g).add_inference_rule(CONSTRUCT); infer_results()",
          _add_rule_then_infer)

    # Can pyoxigraph's own SPARQL feed semantica instead (skip the rdflib copy)?
    probe("pyoxigraph availability for direct SPARQL", lambda: print(
        "pyoxigraph", __import__("pyoxigraph").__version__))


if __name__ == "__main__":
    main()
