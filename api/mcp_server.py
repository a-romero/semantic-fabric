"""MCP server exposing the same fabric capabilities as the REST API.

Any MCP client (skilled-agent's agent, Claude Code, Cursor, other agents) consumes
the fabric through these tools identically to the REST surface. Phase 0 delegates to
the same stub layer as api/main.py, so REST and MCP never drift.

Run: python -m api.mcp_server   (requires the `mcp` package)
"""

from __future__ import annotations

from fabric_client.models import IngestRequest, SearchRequest

from . import stubs

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # keep the scaffold importable without the mcp extra installed
    FastMCP = None  # type: ignore[assignment]


def build_server():  # noqa: ANN201 - FastMCP type optional at import time
    """Construct the MCP server, registering one tool per fabric capability."""
    if FastMCP is None:
        raise RuntimeError("Install the 'mcp' package to run the MCP server: pip install mcp")

    mcp = FastMCP("semantic-fabric")

    @mcp.tool()
    def search(query: str, section: str = "", top_k: int = 5) -> list[dict]:
        """Hybrid retrieval over the fabric. Returns evidence units."""
        req = SearchRequest(query=query, section=section or None, top_k=top_k)
        return [u.model_dump() for u in stubs.stub_search_units(req.query, req.section, req.top_k)]

    @mcp.tool()
    def graph_query(entity: str, hops: int = 1) -> list[dict]:
        """Expand from an entity to connected facts (GraphRAG)."""
        return [u.model_dump() for u in stubs.stub_search_units(entity, None, hops + 1)]

    @mcp.tool()
    def get_chunk(ref: str) -> str:
        """Fetch full chunk content by reference."""
        return f"Stub chunk content for {ref} (Phase 0)."

    @mcp.tool()
    def read_page(namespace: str, path: str) -> dict:
        """Read a KB page from the authored/ or generated/ namespace."""
        return stubs.stub_kb_page(namespace, path).model_dump()

    @mcp.tool()
    def ingest(kind: str, namespace: str = "authored", uri: str = "") -> dict:
        """Push a source to the fabric for ingestion."""
        IngestRequest(kind=kind, namespace=namespace, uri=uri or None)
        return stubs.stub_ingest_job().model_dump()

    @mcp.tool()
    def reason(query: str) -> dict:
        """Deterministic reasoning over the semantic layer."""
        return stubs.stub_reason(query).model_dump()

    return mcp


if __name__ == "__main__":
    build_server().run()
