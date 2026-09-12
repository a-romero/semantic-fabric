"""KB stores: the authored/ and generated/ Markdown namespaces served over /kb.

- authored/  — human-curated pages, pushed via /ingest and mirrored here for reading.
- generated/ — fabric-produced pages (dense-source summary trees, downward
  projections). A materialized read-view, never re-ingested.
"""

from .store import KBStore

__all__ = ["KBStore"]
