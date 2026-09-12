"""fabric-client — the thin, semantica-free client + contract types for semantic-fabric.

skilled-agent (and any other consumer) depends on THIS package only, never on
`semantica`. It ships the wire contract (pydantic models) and an HTTP client.
"""

from .http import FabricClient
from .models import (
    CONTRACT_VERSION,
    Decision,
    EvidenceType,
    EvidenceUnit,
    GraphExpandRequest,
    IngestJob,
    IngestRequest,
    KBPage,
    Provenance,
    ReasonRequest,
    ReasonResponse,
    SearchRequest,
    SearchResponse,
)

__version__ = "0.1.0"

__all__ = [
    "FabricClient",
    "CONTRACT_VERSION",
    "Decision",
    "EvidenceType",
    "EvidenceUnit",
    "GraphExpandRequest",
    "IngestJob",
    "IngestRequest",
    "KBPage",
    "Provenance",
    "ReasonRequest",
    "ReasonResponse",
    "SearchRequest",
    "SearchResponse",
]
