#!/usr/bin/env python
"""Phase 2 & 4 spike — semantica knowledge-graph build, Oxigraph persistence, analytics.

This spike answers the pivotal Phase 2 question in
docs/plans/semantica-adoption-plan.md: **does semantica's KG store persist LIVE into an
embedded Oxigraph (RocksDB) store, or only via an RDF exporter?** The answer decides the
Phase 2 design (a live `SemanticaGraphStore` behind our GraphStore protocol, vs an
end-of-ingest export into our existing pyoxigraph.Store at GRAPH_DB_PATH).

It also confirms Phase 4 inputs: what `semantica.kg` analytics classes exist and what graph
representation they accept (a semantica graph, an rdflib.Graph, or a networkx graph).

READ-ONLY except that it writes a THROWAWAY graph under a temp dir. Paste output into
docs/plans/semantica-spike-findings.md.

    pip install -e ".[semantica,graph]"
    python scripts/inspect_semantica_kg.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _spike_common import dump_module, header, probe, require_semantica, sig  # noqa: E402


def main() -> None:
    require_semantica()
    tmp = Path(tempfile.mkdtemp(prefix="semantica-kg-spike-"))
    oxi_path = str(tmp / "oxi")
    print("temp graph dir:", tmp)

    header("1. semantica.kg — full public surface")
    kg = dump_module("semantica.kg")

    header("2. storage backends — how is a graph persisted? (RDF/Oxigraph config)")
    # Look for a storage/backends module and any Oxigraph adapter.
    for modname in ("semantica.kg.storage", "semantica.storage", "semantica.kg.backends",
                    "semantica.graph_store", "semantica.stores"):
        dump_module(modname)
    print("\nGrep hint: search the installed package for 'oxigraph' / 'RocksDB' / 'Store(':")
    try:
        import semantica
        pkg = Path(semantica.__file__).parent
        hits = []
        for p in pkg.rglob("*.py"):
            try:
                txt = p.read_text(errors="ignore").lower()
            except Exception:  # noqa: BLE001
                continue
            if "oxigraph" in txt or "rocksdb" in txt:
                hits.append(str(p.relative_to(pkg)))
        print("files mentioning oxigraph/rocksdb:", hits[:40])
    except Exception:  # noqa: BLE001
        pass

    header("3. GraphBuilder / ContextGraph — construct with an Oxigraph backend and add data")

    def find(mod, *names):
        return next((getattr(mod, n) for n in names if mod and hasattr(mod, n)), None)

    Builder = find(kg, "GraphBuilder", "KnowledgeGraphBuilder", "KGBuilder", "GraphStore")
    if Builder:
        print(f"GraphBuilder = {Builder.__name__}{sig(getattr(Builder, '__init__', Builder))}")

    # Try the plausible ways to point a builder/store at an embedded Oxigraph path.
    ctor_variants = [
        ("backend='oxigraph', path=…", dict(backend="oxigraph", path=oxi_path)),
        ("store='oxigraph', path=…", dict(store="oxigraph", path=oxi_path)),
        ("storage='oxigraph', db_path=…", dict(storage="oxigraph", db_path=oxi_path)),
        ("config={'backend':'oxigraph','path':…}",
         dict(config={"backend": "oxigraph", "path": oxi_path})),
        ("rdf_backend='oxigraph', location=…", dict(rdf_backend="oxigraph", location=oxi_path)),
        ("path=…", dict(path=oxi_path)),
        ("no-args", {}),
    ]

    built = {"inst": None, "how": None}

    def try_build():
        if Builder is None:
            print("no GraphBuilder-like class found; inspect section 1 output")
            return
        for desc, kwargs in ctor_variants:
            try:
                inst = Builder(**kwargs)
                built["inst"], built["how"] = inst, desc
                print(f"OK constructed: {Builder.__name__}({desc})")
                return
            except Exception as e:  # noqa: BLE001
                print(f"  x {Builder.__name__}({desc}) -> {type(e).__name__}: {e}")
        print("could not construct a builder with an oxigraph backend from the guesses above")
    probe("construct GraphBuilder with oxigraph backend", try_build)

    def add_and_persist():
        inst = built["inst"]
        if inst is None:
            return
        # Try common mutation method names to add an entity + relation.
        for add in ("add_entity", "add_node", "add_fact", "add_triple", "upsert_entity"):
            fn = getattr(inst, add, None)
            if fn:
                print(f"mutation method available: {add}{sig(fn)}")
        # Try to persist/flush.
        for save in ("save", "flush", "commit", "persist", "close", "save_to_file"):
            fn = getattr(inst, save, None)
            if fn:
                print(f"persist method available: {save}{sig(fn)}")
    probe("inspect mutation/persist methods on the built graph", add_and_persist)

    header("4. PERSISTENCE TEST — reopen the SAME oxigraph path in a fresh instance")
    print("Manual step for the implementer: using the methods printed above, add one entity,")
    print("persist, then construct a NEW builder at the SAME path and confirm the entity is")
    print("present. If yes -> LIVE Oxigraph backend (Phase 2 'live' path). If the data only")
    print("appears after an explicit export step -> EXPORT path.")

    header("5. RDF export bridge (the fallback path)")
    exp = dump_module("semantica.export")
    RDFExp = find(exp, "RDFExporter", "TurtleExporter", "RDFExport")
    if RDFExp:
        print(f"RDFExporter = {RDFExp.__name__}{sig(getattr(RDFExp, '__init__', RDFExp))}")
        for meth in ("export", "to_turtle", "to_ntriples", "dump", "write"):
            fn = getattr(RDFExp, meth, None)
            if fn:
                print(f"  - {meth}{sig(fn)}")

    header("6. analytics — what graph representation do the analyzers accept? (Phase 4)")
    for cname in ("GraphAnalyzer", "CentralityCalculator", "CommunityDetector",
                  "LinkPredictor", "PathFinder"):
        cls = find(kg, cname)
        if cls:
            print(f"\n{cname}{sig(getattr(cls, '__init__', cls))}")
            for meth in ("analyze", "compute", "run", "centrality", "detect",
                         "detect_communities", "predict", "predict_links"):
                fn = getattr(cls, meth, None)
                if fn:
                    print(f"  - {meth}{sig(fn)}")

    def feed_representations():
        Cent = find(kg, "CentralityCalculator", "GraphAnalyzer")
        if Cent is None:
            print("no centrality/analyzer class found")
            return
        # (a) an rdflib.Graph like OxigraphGraphStore.rdf_graph() returns
        import rdflib
        g = rdflib.Graph()
        g.parse(data="""@prefix ex: <http://semantic-fabric/ex#> .
                        ex:Aviva ex:offers ex:ISA . ex:ISA a ex:Product .""",
                format="turtle")
        probe("CentralityCalculator(rdflib.Graph)", lambda: print(Cent(g)))
        # (b) a networkx graph
        try:
            import networkx as nx
            ng = nx.DiGraph()
            ng.add_edge("Aviva", "ISA", type="offers")
            probe("CentralityCalculator(networkx.DiGraph)", lambda: print(Cent(ng)))
        except Exception as e:  # noqa: BLE001
            print("networkx not available:", e)
    probe("feed rdflib/networkx to an analyzer", feed_representations)

    header("7. QUESTIONS FOR THE PLAN")
    print("- Does a builder/store persist LIVE to embedded Oxigraph at a path (section 4)?")
    print("- If not, is RDFExporter -> load into pyoxigraph the intended bridge (section 5)?")
    print("- What input do kg analyzers accept: semantica graph / rdflib / networkx?")
    print("- Which mutation methods carry confidence + provenance onto an edge?")
    print(f"\n(You can delete the temp dir: {tmp})")


if __name__ == "__main__":
    main()
