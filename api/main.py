"""semantic-fabric REST API — the network boundary.

Phase 0: every route validates against the real wire contract (fabric_client.models)
and returns stub data. Later phases replace the stub calls with retrieval/, graph/,
ingest/, reasoning/, and provenance/ implementations without changing these signatures.

Run: uvicorn api.main:app --reload --port 8080
"""

from __future__ import annotations

from fastapi import FastAPI

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

from . import stubs

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
    units = stubs.stub_search_units(req.query, req.section, req.top_k)
    return SearchResponse(units=units)


@app.post("/graph/expand", response_model=SearchResponse)
def graph_expand(req: GraphExpandRequest) -> SearchResponse:
    # Phase 0: reuse the search stub as placeholder graph neighbours.
    units = stubs.stub_search_units(req.seed, None, top_k=req.hops + 1)
    return SearchResponse(units=units)


@app.get("/chunk/{ref}")
def get_chunk(ref: str) -> dict:
    return {"ref": ref, "content": f"Stub chunk content for {ref} (Phase 0)."}


# -- knowledge base (authored + generated namespaces) ------------------------
@app.get("/kb/{namespace}/tree")
def list_kb(namespace: str) -> dict:
    return {
        "namespace": namespace,
        "tree": {"name": namespace, "type": "directory", "path": "", "children": []},
    }


@app.get("/kb/{namespace}/{path:path}", response_model=KBPage)
def read_page(namespace: str, path: str) -> KBPage:
    return stubs.stub_kb_page(namespace, path)


# -- ingestion ---------------------------------------------------------------
@app.post("/ingest", response_model=IngestJob)
def ingest(req: IngestRequest) -> IngestJob:
    # Push entry point: anyone can POST a source here. Phase 0 queues a stub job.
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
