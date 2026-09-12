"""Phase 0 stub responses.

These let a consumer (skilled-agent's RemoteFabricBackend) integrate against the
real wire contract before any retrieval/graph machinery exists. Every function here
is replaced in later phases by calls into retrieval/, graph/, ingest/, etc.
"""

from __future__ import annotations

import uuid

from fabric_client.models import (
    EvidenceType,
    EvidenceUnit,
    IngestJob,
    KBPage,
    Provenance,
    ReasonResponse,
)


def stub_search_units(query: str, section: str | None, top_k: int) -> list[EvidenceUnit]:
    """Return deterministic placeholder evidence units that satisfy the contract."""
    base = section or "authored"
    units = [
        EvidenceUnit(
            id="stub-1",
            path=f"{base}/example/index.md",
            title="Example authored page",
            summary=f"Stub result for query: {query!r}",
            type=EvidenceType.markdown_chunk,
            content="This is stub content from the semantic-fabric Phase 0 skeleton.",
            score=0.99,
            provenance=Provenance(
                source_id=f"{base}/example/index.md",
                source_url="https://example.invalid/example",
                locator=f"{base}/example/index.md#intro",
                credibility=1.0,
            ),
        ),
        EvidenceUnit(
            id="stub-2",
            path="generated/report-q3/summary.md",
            title="Q3 report — generated summary",
            summary="Stub fact extracted from a dense PDF chart.",
            type=EvidenceType.fact,
            content="Q3 revenue = 4.2 (units: £m)",
            score=0.71,
            provenance=Provenance(
                source_id="report-q3.pdf",
                locator="page=12;bbox=88,204,512,470",
                valid_time="2026-09-30",
                credibility=0.8,
            ),
            entities=["entity:revenue", "entity:q3-2026"],
        ),
    ]
    return units[:top_k]


def stub_kb_page(namespace: str, path: str) -> KBPage:
    return KBPage(
        namespace=namespace,
        path=path,
        frontmatter={"title": "Stub page", "namespace": namespace},
        body=f"# Stub page\n\nServed from the `{namespace}` namespace at `{path}` (Phase 0).\n",
    )


def stub_ingest_job() -> IngestJob:
    return IngestJob(job_id=f"job-{uuid.uuid4().hex[:8]}", status="queued",
                     detail="Phase 0 stub: no pipeline wired yet.")


def stub_reason(query: str) -> ReasonResponse:
    return ReasonResponse(
        answer="Phase 0 stub: deterministic reasoning is not wired yet.",
        rule_trace=[f"received: {query}"],
    )
