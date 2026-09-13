"""Context Graph for GraphRAG expansion (Phase 1: page graph).

The page graph is built at ingest from the path hierarchy and frontmatter topics and
enriched with extracted entities/relations; ``expand(seed, hops)`` traverses it. The
in-memory store is the dependency-free default; persistent LPG (Kuzu, ``GRAPH_STORE=lpg``)
and RDF (Oxigraph, ``GRAPH_STORE=rdf``) backends live in ``kuzu_backend`` /
``oxigraph_backend`` behind the ``.[graph]`` extra. Public surface:

    build_graph_store(kind) -> GraphStore
    GraphStore.add_page(...) / .expand(seed, hops, rel_types, limit)
"""

from .store import GraphStore, InMemoryGraphStore, build_graph_store

__all__ = ["GraphStore", "InMemoryGraphStore", "build_graph_store"]
