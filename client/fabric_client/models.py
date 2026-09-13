"""Wire contract types shared across the semantic-fabric boundary.

These pydantic models ARE the contract. Both the fabric service (`api/`) and every
consumer (skilled-agent's RemoteFabricBackend) import them from here, so there is a
single source of truth for what crosses the network. `contracts/evidence_unit.schema.json`
is a committed JSON-Schema snapshot generated from `EvidenceUnit` — see the Makefile
target `contracts`.

Compatibility rule: evolve by BACKWARD-COMPATIBLE ADDITION only. New optional fields
are fine; renaming or removing a field is a breaking change and requires a major
version bump of fabric-client.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

CONTRACT_VERSION = "0.1.0"


class EvidenceType(str, Enum):
    """What kind of thing an evidence unit carries. Origin-agnostic to the agent."""

    markdown_chunk = "markdown_chunk"   # chunk of a curated (authored) Markdown page
    pdf_chunk = "pdf_chunk"             # chunk of prose from a dense document
    chart_caption = "chart_caption"     # VLM-generated description of a figure/chart
    fact = "fact"                       # a triplet/fact from the Context Graph
    table_row = "table_row"             # an extracted structured row
    db_value = "db_value"               # a live value fetched from a connector
    decision = "decision"               # a recorded prior decision


class Provenance(BaseModel):
    """Where an evidence unit came from. Powers citations and audit."""

    source_id: str = Field(..., description="Doc/page id or connector URI")
    source_url: str | None = Field(None, description="Upstream URL, when known")
    locator: str | None = Field(
        None, description="e.g. 'page=12;bbox=...' or 'authored/investments/isas.md#overview'"
    )
    valid_time: str | None = Field(
        None, description="Bi-temporal: when true in the world (ISO 8601)"
    )
    recorded_time: str | None = Field(None, description="Bi-temporal: when learned (ISO 8601)")
    prov_o: dict[str, Any] = Field(default_factory=dict, description="W3C PROV-O payload")
    credibility: float | None = Field(None, description="Source credibility score, 0..1")


class EvidenceUnit(BaseModel):
    """The single normalized shape every retrieval mode returns.

    The (path, title, summary) trio is kept for backward compatibility with
    skilled-agent's existing KnowledgeGraph.search() consumers; `to_legacy()`
    projects down to exactly that dict.
    """

    # backward-compatible trio
    path: str = Field(..., description="Canonical locator; a KB path for Markdown units")
    title: str = ""
    summary: str = ""

    # richer fields (ignored by legacy consumers)
    id: str = ""
    type: EvidenceType = EvidenceType.markdown_chunk
    content: str = Field("", description="Retrievable payload: chunk / caption / fact text")
    score: float = 0.0
    provenance: Provenance | None = None
    entities: list[str] = Field(default_factory=list, description="Linked graph node ids")
    embedding_ref: str | None = None

    def to_legacy(self) -> dict[str, str]:
        """Project to the {path, title, summary} dict older callers expect."""
        return {"path": self.path, "title": self.title, "summary": self.summary}


# --- requests / responses ---------------------------------------------------


class SearchRequest(BaseModel):
    query: str
    section: str | None = Field(None, description="Ontology/section scope, e.g. 'investments'")
    top_k: int = 5
    modes: list[str] = Field(
        default_factory=lambda: ["vector", "bm25", "graph"],
        description="Which retrieval legs to run",
    )


class SearchResponse(BaseModel):
    contract_version: str = CONTRACT_VERSION
    units: list[EvidenceUnit] = Field(default_factory=list)


class GraphExpandRequest(BaseModel):
    seed: str = Field(..., description="Entity id or pattern to expand from")
    hops: int = 1
    rel_types: list[str] | None = None


class IngestRequest(BaseModel):
    """Push a source to the fabric. `kind` selects the pipeline."""

    kind: str = Field(..., description="'markdown_tree' | 'pdf_batch' | 'connector'")
    namespace: str = Field("authored", description="KB namespace this source belongs to")
    uri: str | None = Field(None, description="Location of the source payload")
    payload: dict[str, Any] = Field(default_factory=dict, description="Inline descriptor/content")


class IngestJob(BaseModel):
    job_id: str
    status: str = Field("queued", description="queued | running | done | failed")
    detail: str | None = None


class ReasonRule(BaseModel):
    """A Horn rule: all `body` atoms present -> derive `head`."""

    name: str = "rule"
    body: list[str] = Field(default_factory=list)
    head: str


class ReasonRequest(BaseModel):
    query: str = Field("", description="Atom to prove/derive, e.g. 'Insurable(motor_policy)'")
    facts: list[str] = Field(default_factory=list, description="Known ground atoms")
    rules: list[ReasonRule] = Field(default_factory=list)
    ruleset: str | None = Field(None, description="Named server-side ruleset (optional)")


class ReasonResponse(BaseModel):
    answer: str
    rule_trace: list[str] = Field(default_factory=list)


class Decision(BaseModel):
    scenario: str
    reasoning: str = ""
    outcome: str = ""
    evidence: list[str] = Field(default_factory=list, description="Evidence unit ids used")
    valid_time: str | None = None
    recorded_time: str | None = None


class ExtractedEntity(BaseModel):
    name: str = Field(..., description="Canonical surface form of the entity")
    type: str = Field(..., description="Entity type, e.g. Product, Organization, Policy, Term")


class ExtractedRelation(BaseModel):
    subject: str = Field(..., description="Entity name (subject)")
    predicate: str = Field(..., description="Typed relation, snake_case, e.g. covers, offered_by")
    object: str = Field(..., description="Entity name or literal (object)")
    confidence: float = Field(1.0, description="Extractor confidence 0..1")


class Extraction(BaseModel):
    """Typed entities + relations extracted from a piece of text.

    Doubles as the LLM structured-output schema (client.messages.parse output_format),
    so the wire contract and the extraction schema are one definition.
    """

    entities: list[ExtractedEntity] = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)


class ExtractRequest(BaseModel):
    text: str
    hint: str | None = Field(
        None, description="Optional domain hint, e.g. 'UK insurance & pensions'"
    )


class ExtractResponse(BaseModel):
    entities: list[ExtractedEntity] = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)
    backend: str = "null"
    model: str | None = None


class OntologyConstraint(BaseModel):
    """A declarative constraint over entities of a class (compiled to SHACL server-side)."""

    target_class: str
    required: list[str] = Field(default_factory=list)
    min_values: dict[str, float] = Field(default_factory=dict)
    allowed_values: dict[str, list[Any]] = Field(default_factory=dict)
    message: str | None = None


class ValidateRequest(BaseModel):
    # entities: [{"id":..., "class":"Policy", "props": {...}}]
    entities: list[dict[str, Any]] = Field(default_factory=list)
    constraints: list[OntologyConstraint] = Field(default_factory=list)


class Violation(BaseModel):
    entity_id: str
    target_class: str
    path: str
    message: str


class ValidateResponse(BaseModel):
    conforms: bool
    violations: list[Violation] = Field(default_factory=list)


class KBPage(BaseModel):
    namespace: str
    path: str
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    body: str = ""
