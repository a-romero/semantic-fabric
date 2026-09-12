"""Markdown ingestion (Phase 1): push authored pages into the retrieval index.

Accepts an IngestRequest whose payload carries pages:

    {"kind": "markdown_tree", "namespace": "authored",
     "payload": {"pages": [{"path": ..., "frontmatter": {...}, "body": "..."}]}}

Later phases add the dense-PDF flow (layout parse, figure/VLM branch, tables->facts)
and emit the generated/ namespace; see ingest/__init__ for the roadmap.
"""

from __future__ import annotations

from fabric_client.models import IngestRequest

from kb.store import KBStore
from retrieval.index import RetrievalIndex


def ingest_markdown_tree(index: RetrievalIndex, kb: KBStore, req: IngestRequest) -> int:
    """Ingest a markdown_tree request into the index and mirror pages into the KB.

    The pages become retrievable chunks (and graph nodes) via the index, and are also
    stored under the authored/ namespace so GET /kb/authored/<path> can read them.
    Returns chunks added.
    """
    pages = req.payload.get("pages") or []
    if not isinstance(pages, list):
        raise ValueError("payload.pages must be a list of {path, frontmatter, body}")
    added = index.add_pages(pages, namespace=req.namespace)
    for page in pages:
        kb.put(
            "authored",
            page["path"],
            body=page.get("body") or "",
            frontmatter=page.get("frontmatter") or {},
        )
    return added
