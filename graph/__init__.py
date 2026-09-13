"""Context Graph for GraphRAG expansion (Phase 1: page graph).

The page graph is built at ingest from the path hierarchy and frontmatter topics and
enriched with extracted entities/relations; ``expand(seed, hops)`` traverses it. The
in-memory store is the dependency-free default; a persistent, SPARQL-native RDF backend
(Oxigraph, ``GRAPH_STORE=rdf``) lives in ``oxigraph_backend`` behind the ``.[graph]``
extra and shares semantica's RDF/SPARQL model. Public surface:

    build_graph_store(kind) -> GraphStore
    GraphStore.add_page(...) / .expand(seed, hops, rel_types, limit)
"""

from .store import GraphStore, InMemoryGraphStore, build_graph_store

__all__ = ["GraphStore", "InMemoryGraphStore", "build_graph_store"]
