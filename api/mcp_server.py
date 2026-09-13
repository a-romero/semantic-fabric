"""MCP server exposing the same fabric capabilities as the REST API.

Any MCP client (skilled-agent's agent, Claude Code, Cursor, other agents) consumes
the fabric through these tools identically to the REST surface. Phase 0 delegates to
the same stub layer as api/main.py, so REST and MCP never drift.

Run: python -m api.mcp_server   (requires the `mcp` package)
"""

from __future__ import annotations

from fabric_client.models import IngestRequest, SearchRequest

from ingest.markdown import ingest_markdown_tree
from ingest.pdf import ingest_pdf_batch

from . import stubs
from .state import get_index, get_kb, get_object_store, get_provenance

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
        units = get_index().search(req.query, section=req.section, top_k=req.top_k)
        return [u.model_dump() for u in units]

    @mcp.tool()
    def graph_query(entity: str, hops: int = 1) -> list[dict]:
        """Expand from an entity/page to connected facts (GraphRAG)."""
        return [u.model_dump() for u in get_index().graph_expand(entity, hops=hops)]

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
        req = IngestRequest(kind=kind, namespace=namespace, uri=uri or None)
        if req.kind == "markdown_tree":
            added = ingest_markdown_tree(get_index(), get_kb(), req)
            return {"job_id": f"md-{added}", "status": "done", "detail": f"ingested {added} chunks"}
        if req.kind == "pdf_batch":
            stats = ingest_pdf_batch(get_index(), get_kb(), get_object_store(), req)
            return {"job_id": f"pdf-{stats['docs']}", "status": "done", "detail": str(stats)}
        return stubs.stub_ingest_job().model_dump()

    @mcp.tool()
    def reason(query: str, facts: list[str] | None = None,
               rules: list[dict] | None = None) -> dict:
        """Deterministic, explainable reasoning. rules: [{name, body:[...], head}]."""
        from reasoning.engine import ReasoningRequest, Rule

        from .state import get_reasoning

        rreq = ReasoningRequest(
            query=query,
            facts=facts or [],
            rules=[Rule(name=r.get("name", "rule"), body=r.get("body", []), head=r["head"])
                   for r in (rules or [])],
        )
        return get_reasoning().reason(rreq).model_dump()

    @mcp.tool()
    def record_decision(scenario: str, outcome: str, evidence: list[str] | None = None) -> dict:
        """Record an agent decision derived from the evidence it cited (provenance)."""
        from fabric_client.models import Decision

        return get_provenance().record_decision(
            Decision(scenario=scenario, outcome=outcome, evidence=evidence or [])
        )

    return mcp


if __name__ == "__main__":
    build_server().run()
