"""Context Graph for GraphRAG expansion (Phase 1: page graph).

Phase 1 builds a page graph at ingest from the path hierarchy and frontmatter topics
and exposes ``expand(seed, hops)``. Entity/relation extraction, the ontology
(OWL/SHACL/SKOS), and a persistent LPG (Kuzu) / RDF (Oxigraph) backend arrive with
later phases. Public surface:

    build_graph_store(kind) -> GraphStore
    GraphStore.add_page(...) / .expand(seed, hops, rel_types, limit)
"""

from .store import GraphStore, InMemoryGraphStore, build_graph_store

__all__ = ["GraphStore", "InMemoryGraphStore", "build_graph_store"]
