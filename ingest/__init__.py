"""Ingestion pipeline (Phase 2+).

Turns pushed sources into retrieval artifacts and the generated/ KB namespace.

Dense-PDF flow:  parse (layout-aware) -> split (entity-aware) + tables->facts
                 + figures->VLM caption/data table/image blob -> normalize
                 -> conflict-detect -> dedup -> upsert{graph, vectors, provenance}
                 -> emit doc/section/chunk summary tree into generated/.
Markdown flow:   frontmatter + extract(NER/relations/triplets) -> split -> embed
                 -> upsert (provenance from source registry).

Public entry (future):
    def ingest(request: IngestRequest) -> IngestJob: ...
"""
