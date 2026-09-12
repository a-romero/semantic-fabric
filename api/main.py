"""semantic-fabric REST API — the network boundary.

Every route validates against the real wire contract (fabric_client.models).
Phase 1 wires /ingest (markdown_tree) and /search to real hybrid retrieval over the
ingested authored KB; graph expansion, reasoning, decisions, and the generated/ KB
namespace remain stubs until their phases land. Route signatures never change.

Run: uvicorn api.main:app --reload --port 8080
"""

from __future__ import annotations

from fabric_client.models import (
    CONTRACT_VERSION,
    Decision,
    GraphExpandRequest,
    IngestJob,
    IngestRequest,
    KBPage,
    ReasonRequest,
    ReasonResponse,
    SearchRequest,
    SearchResponse,
)
from fastapi import FastAPI

from ingest.markdown import ingest_markdown_tree
from ingest.pdf import ingest_pdf_batch

from . import stubs
from .state import get_index, get_kb, get_object_store

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


# -- knowledge base (authored + generated namespaces) ------------------------
@app.get("/kb/{namespace}/tree")
def list_kb(namespace: str) -> dict:
    return get_kb().tree(namespace)


@app.get("/kb/{namespace}/{path:path}", response_model=KBPage)
def read_page(namespace: str, path: str) -> KBPage:
    page = get_kb().get(namespace, path)
    return page if page is not None else stubs.stub_kb_page(namespace, path)


# -- ingestion ---------------------------------------------------------------
@app.post("/ingest", response_model=IngestJob)
def ingest(req: IngestRequest) -> IngestJob:
    # Push entry point: anyone can POST a source here from anywhere.
    if req.kind == "markdown_tree":
        try:
            added = ingest_markdown_tree(get_index(), get_kb(), req)
        except ValueError as exc:
            return IngestJob(job_id="ingest-error", status="failed", detail=str(exc))
        return IngestJob(job_id=f"md-{added}", status="done", detail=f"ingested {added} chunks")
    if req.kind == "pdf_batch":
        try:
            stats = ingest_pdf_batch(get_index(), get_kb(), get_object_store(), req)
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
    return stubs.stub_reason(req.query)


@app.post("/decisions")
def record_decision(decision: Decision) -> dict:
    return {"decision_id": "dec-stub", "recorded": True, "scenario": decision.scenario}


@app.get("/decisions/{decision_id}/chain")
def decision_chain(decision_id: str) -> dict:
    return {"decision_id": decision_id, "chain": [], "note": "Phase 0 stub."}
