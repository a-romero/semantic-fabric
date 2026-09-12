"""Markdown ingestion (Phase 1): push authored pages into the retrieval index.

Accepts an IngestRequest whose payload carries pages:

    {"kind": "markdown_tree", "namespace": "authored",
     "payload": {"pages": [{"path": ..., "frontmatter": {...}, "body": "..."}]}}

Later phases add the dense-PDF flow (layout parse, figure/VLM branch, tables->facts)
and emit the generated/ namespace; see ingest/__init__ for the roadmap.
"""

from __future__ import annotations

from fabric_client.models import IngestRequest

from retrieval.index import RetrievalIndex


def ingest_markdown_tree(index: RetrievalIndex, req: IngestRequest) -> int:
    """Ingest the pages in a markdown_tree request. Returns chunks added."""
    pages = req.payload.get("pages") or []
    if not isinstance(pages, list):
        raise ValueError("payload.pages must be a list of {path, frontmatter, body}")
    return index.add_pages(pages, namespace=req.namespace)
