"""The MCP server: registers query tools that proxy to a running semantic-fabric.

Run (stdio transport, what Claude Code/Cursor expect):

    FABRIC_URL=http://localhost:8080 python -m fabric_mcp

Register with Claude Code:

    claude mcp add semantic-fabric -e FABRIC_URL=http://localhost:8080 -- python -m fabric_mcp

Requires the ``mcp`` package (``pip install -e ".[mcp]"``) and a fabric already running
with data ingested. Tools are query-only; ingestion stays a separate, deliberate step.
"""

from __future__ import annotations

from . import client

_ERR_HINT = ("Ensure the fabric is running and FABRIC_URL points at it "
             "(default http://localhost:8080), and that data has been ingested.")


def _safe(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as e:  # surface a useful message to the agent, don't crash the server
        return {"error": str(e), "hint": _ERR_HINT}


def build_server():  # noqa: ANN201 - FastMCP type is optional at import time
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("semantic-fabric-query")

    @mcp.tool()
    def fabric_answer(question: str, top_k: int = 5, section: str = "",
                      expand: bool = True, record: bool = True) -> dict:
        """Run the FULL query cycle against semantic-fabric for a knowledge question.

        Use this first for any question about the ingested corpus. It retrieves ranked
        evidence, pulls graph-connected context, records an auditable decision, and returns
        its provenance lineage — everything needed to answer with citations.

        Returns {question, evidence[], related[], decision, lineage, guidance}. Each
        evidence item carries `content` and `provenance.locator` (page/section, or PDF page
        + bounding box) — cite those. Set record=false for a pure lookup with no audit
        trail; narrow with section (a top-level KB folder). Assumes data is already
        ingested and the fabric is running (FABRIC_URL).
        """
        return _safe(client.answer, question, top_k=top_k, section=section or None,
                     expand=expand, record=record)

    @mcp.tool()
    def fabric_search(query: str, top_k: int = 5, section: str = "") -> object:
        """Hybrid retrieval (vector + BM25, RRF-fused). Returns ranked EvidenceUnits, each
        with content, type, score and provenance (source + exact locator). Use for a plain
        search; prefer fabric_answer for a full, audited answer."""
        return _safe(client.search, query, top_k=top_k, section=section or None)

    @mcp.tool()
    def fabric_graph_expand(seed: str, hops: int = 2) -> object:
        """GraphRAG: from a seed (a page path or an entity name) walk the knowledge graph
        (hierarchy, shared topics, shared entities, relations) to related pages that plain
        search would miss."""
        return _safe(client.graph_expand, seed, hops=hops)

    @mcp.tool()
    def fabric_reason(query: str, facts: list[str] | None = None,
                      rules: list[dict] | None = None, over_graph: bool = False) -> dict:
        """Deterministic, explainable reasoning with a proof trace. rules:
        [{name, body:[atoms], head}]. over_graph=true also seeds the reasoner with the
        knowledge graph's own facts, so the query is answered by inference over the KG."""
        return _safe(client.reason, query, facts=facts, rules=rules, over_graph=over_graph)

    @mcp.tool()
    def fabric_validate(entities: list[dict], constraints: list[dict]) -> dict:
        """SHACL policy gate: check entity data against declared constraints
        (required properties, min values, allowed values). Returns {conforms, violations}.
        Use to gate an answer against business rules before presenting it."""
        return _safe(client.validate, entities, constraints)

    @mcp.tool()
    def fabric_record_decision(scenario: str, outcome: str,
                               evidence: list[str] | None = None, reasoning: str = "") -> dict:
        """Record a decision derived from the evidence it cited (provenance). evidence is a
        list of EvidenceUnit paths. Returns the decision_id for later lineage lookup."""
        return _safe(client.record_decision, scenario, outcome=outcome,
                     evidence=evidence, reasoning=reasoning)

    @mcp.tool()
    def fabric_decision_chain(decision_id: str) -> dict:
        """Trace a recorded decision's transitive lineage (W3C PROV-O + tamper-evident
        chain) — 'why did we conclude this, and from what?'."""
        return _safe(client.decision_chain, decision_id)

    @mcp.tool()
    def fabric_read_page(namespace: str, path: str) -> dict:
        """Read a full KB page (namespace 'authored' or 'generated') by path."""
        return _safe(client.read_page, namespace, path)

    @mcp.tool()
    def fabric_graph_snapshot() -> dict:
        """The whole knowledge graph: {pages, entities, relations, counts}. Large on real
        corpora — prefer fabric_graph_expand for a focused view."""
        return _safe(client.graph_snapshot)

    @mcp.tool()
    def fabric_health() -> dict:
        """Check the fabric is reachable; returns status + contract version."""
        return _safe(client.health)

    return mcp


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
