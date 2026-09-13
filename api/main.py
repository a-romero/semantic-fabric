"""semantic-fabric REST API — the network boundary.

Every route validates against the real wire contract (fabric_client.models). Real and
wired: /search + /graph/expand (retrieval + GraphRAG), /ingest (markdown_tree,
pdf_batch), the authored/ + generated/ KB namespaces, /reason, /validate (SHACL gate),
/extract (LLM-backed), and /decisions (+ lineage). Each has a dependency-free default
and an optional backend behind an extra. Route signatures never change.

Run: uvicorn api.main:app --reload --port 8080
"""

from __future__ import annotations

import os

from fabric_client.models import (
    CONTRACT_VERSION,
    Decision,
    ExtractRequest,
    ExtractResponse,
    GraphExpandRequest,
    IngestJob,
    IngestRequest,
    KBPage,
    ReasonRequest,
    ReasonResponse,
    SearchRequest,
    SearchResponse,
    ValidateRequest,
    ValidateResponse,
)
from fastapi import FastAPI

from ingest.markdown import ingest_markdown_tree
from ingest.pdf import ingest_pdf_batch
from ontology.validator import Constraint, ValidationRequest
from reasoning.engine import ReasoningRequest, Rule

from . import stubs
from .state import (
    get_captioner,
    get_extractor,
    get_index,
    get_kb,
    get_object_store,
    get_pdf_parser,
    get_provenance,
    get_reasoning,
    get_validator,
)

app = FastAPI(
    title="semantic-fabric",
    version="0.1.0",
    summary="Enterprise semantic layer: retrieval, graph, ingestion, reasoning, provenance.",
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "contract_version": CONTRACT_VERSION}


# -- retrieval ---------------------------------------------------------------
@app.post("/search", response_model=SearchResponse)
def search(req: SearchRequest) -> SearchResponse:
    # Phase 1: real hybrid (vector + BM25) retrieval over the ingested authored KB.
    units = get_index().search(req.query, section=req.section, top_k=req.top_k)
    return SearchResponse(units=units)


@app.post("/graph/expand", response_model=SearchResponse)
def graph_expand(req: GraphExpandRequest) -> SearchResponse:
    # Phase 1: real GraphRAG expansion from a seed (page path or topic) to connected pages.
    units = get_index().graph_expand(req.seed, hops=req.hops, rel_types=req.rel_types)
    return SearchResponse(units=units)


@app.get("/chunk/{ref}")
def get_chunk(ref: str) -> dict:
    return {"ref": ref, "content": f"Stub chunk content for {ref} (Phase 0)."}


@app.get("/graph")
def graph_snapshot() -> dict:
    # Read-only whole-graph view (pages/entities/relations) for visualization/inspection.
    snap = get_index().graph_snapshot()
    snap["counts"] = {
        "pages": len(snap["pages"]),
        "entities": len(snap["entities"]),
        "relations": len(snap["relations"]),
    }
    return snap


# -- knowledge base (authored + generated namespaces) ------------------------
@app.get("/kb/{namespace}/tree")
def list_kb(namespace: str) -> dict:
    return get_kb().tree(namespace)


@app.get("/kb/{namespace}/{path:path}", response_model=KBPage)
def read_page(namespace: str, path: str) -> KBPage:
    page = get_kb().get(namespace, path)
    return page if page is not None else stubs.stub_kb_page(namespace, path)


# -- ingestion ---------------------------------------------------------------
def _ingest_extractor():
    """The extractor to enrich the graph at ingest, or None unless EXTRACTION_ON_INGEST."""
    if os.getenv("EXTRACTION_ON_INGEST", "false").strip().lower() in {"1", "true", "yes"}:
        return get_extractor()
    return None


@app.post("/ingest", response_model=IngestJob)
def ingest(req: IngestRequest) -> IngestJob:
    # Push entry point: anyone can POST a source here from anywhere.
    if req.kind == "markdown_tree":
        try:
            added = ingest_markdown_tree(get_index(), get_kb(), req, extractor=_ingest_extractor())
        except ValueError as exc:
            return IngestJob(job_id="ingest-error", status="failed", detail=str(exc))
        return IngestJob(job_id=f"md-{added}", status="done", detail=f"ingested {added} chunks")
    if req.kind == "pdf_batch":
        try:
            stats = ingest_pdf_batch(
                get_index(), get_kb(), get_object_store(), req,
                captioner=get_captioner(), extractor=_ingest_extractor(),
                parser=get_pdf_parser(),
            )
        except (ValueError, KeyError) as exc:
            return IngestJob(job_id="ingest-error", status="failed", detail=str(exc))
        return IngestJob(
            job_id=f"pdf-{stats['docs']}",
            status="done",
            detail=(
                f"{stats['docs']} docs -> {stats['chunks']} chunks "
                f"({stats['tables']} tables, {stats['figures']} figures), "
                f"{stats['generated_pages']} generated pages"
            ),
        )
    # Other kinds (connector, …) are added in later phases.
    return stubs.stub_ingest_job()


@app.get("/jobs/{job_id}", response_model=IngestJob)
def job(job_id: str) -> IngestJob:
    return IngestJob(job_id=job_id, status="done", detail="Phase 0 stub job.")


# -- reasoning / decisions ---------------------------------------------------
@app.post("/reason", response_model=ReasonResponse)
def reason(req: ReasonRequest) -> ReasonResponse:
    # Gated so the deterministic layer can be rolled out without destabilizing callers.
    if os.getenv("ENABLE_REASONING", "true").strip().lower() in {"0", "false", "no"}:
        return ReasonResponse(answer="Reasoning is disabled (ENABLE_REASONING=false).")
    facts = list(req.facts)
    if req.over_graph:
        # Reason over the knowledge graph itself: seed the KG as Datalog facts.
        facts += get_index().graph_facts()
    rreq = ReasoningRequest(
        query=req.query,
        facts=facts,
        rules=[Rule(name=r.name, body=list(r.body), head=r.head) for r in req.rules],
    )
    return get_reasoning().reason(rreq)


@app.post("/extract", response_model=ExtractResponse)
def extract(req: ExtractRequest) -> ExtractResponse:
    # LLM-backed typed entity/relation extraction (structured outputs on the Claude
    # backend; no-op on the default). Feeds the graph when wired into ingestion.
    extractor = get_extractor()
    result = extractor.extract(req.text, hint=req.hint)
    return ExtractResponse(
        entities=result.entities,
        relations=result.relations,
        backend=extractor.name,
        model=extractor.model,
    )


@app.post("/validate", response_model=ValidateResponse)
def validate(req: ValidateRequest) -> ValidateResponse:
    # SHACL policy gate: check entity data against declared constraints. This is the
    # deterministic gate an answer passes before leaving the semantic plane.
    vreq = ValidationRequest(
        entities=list(req.entities),
        constraints=[
            Constraint(
                target_class=c.target_class,
                required=list(c.required),
                min_values=dict(c.min_values),
                allowed_values=dict(c.allowed_values),
                message=c.message,
            )
            for c in req.constraints
        ],
    )
    result = get_validator().validate(vreq)
    return ValidateResponse(
        conforms=result.conforms,
        violations=[
            {"entity_id": v.entity_id, "target_class": v.target_class,
             "path": v.path, "message": v.message}
            for v in result.violations
        ],
    )


@app.post("/decisions")
def record_decision(decision: Decision) -> dict:
    # Phase 3: persist the decision as a provenance node derived from its evidence.
    return get_provenance().record_decision(decision)


@app.get("/decisions/{decision_id}/chain")
def decision_chain(decision_id: str) -> dict:
    # Phase 3: transitive lineage ("why did the agent conclude this, from what?").
    return get_provenance().trace_chain(decision_id)
