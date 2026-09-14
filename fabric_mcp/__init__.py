"""fabric_mcp — a standalone MCP server that lets an agent query semantic-fabric.

Query-focused (assumes ingestion has already happened): it proxies the fabric's REST
query surface over HTTP and adds a composite ``fabric_answer`` tool that runs the full
cycle — retrieve → graph-expand → record a decision → fetch its provenance lineage — and
returns everything an agent needs to answer with citations and an audit trail.

Point it at a running fabric with ``FABRIC_URL`` (default http://localhost:8080). The
client functions live in ``fabric_mcp.client`` (no ``mcp`` dependency, so they're easy to
test); the MCP server wiring is in ``fabric_mcp.server``.
"""

from . import client

__all__ = ["client"]
