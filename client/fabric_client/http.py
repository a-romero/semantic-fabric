"""Thin HTTP client for the semantic-fabric REST API.

This is the only thing skilled-agent imports to talk to the fabric. Dependency
surface is deliberately tiny (httpx + pydantic) — no `semantica`, no graph/vector
libraries. The client mirrors the API surface in contracts/openapi.yaml.
"""

from __future__ import annotations

import httpx

from .models import (
    CONTRACT_VERSION,
    Decision,
    EvidenceUnit,
    GraphExpandRequest,
    IngestJob,
    IngestRequest,
    KBPage,
    ReasonRequest,
    ReasonResponse,
    SearchRequest,
    SearchResponse,
)

DEFAULT_TIMEOUT = 30.0


class FabricClient:
    """Synchronous client. Construct once and reuse.

    Example
    -------
    >>> fc = FabricClient("http://semantic-fabric:8080", token="...")
    >>> units = fc.search("what are ISAs?", section="investments")
    >>> [u.to_legacy() for u in units]
    """

    def __init__(self, base_url: str, token: str | None = None, timeout: float = DEFAULT_TIMEOUT):
        headers = {"authorization": f"Bearer {token}"} if token else {}
        self._c = httpx.Client(base_url=base_url.rstrip("/"), headers=headers, timeout=timeout)

    # -- retrieval --------------------------------------------------------
    def search(
        self, query: str, section: str | None = None, top_k: int = 5,
        modes: list[str] | None = None,
    ) -> list[EvidenceUnit]:
        req = SearchRequest(query=query, section=section, top_k=top_k,
                            modes=modes or ["vector", "bm25", "graph"])
        r = self._c.post("/search", json=req.model_dump())
        r.raise_for_status()
        return SearchResponse.model_validate(r.json()).units

    def graph_expand(self, seed: str, hops: int = 1, rel_types: list[str] | None = None) -> list[EvidenceUnit]:
        req = GraphExpandRequest(seed=seed, hops=hops, rel_types=rel_types)
        r = self._c.post("/graph/expand", json=req.model_dump())
        r.raise_for_status()
        return SearchResponse.model_validate(r.json()).units

    def get_chunk(self, ref: str) -> str:
        r = self._c.get(f"/chunk/{ref}")
        r.raise_for_status()
        return r.json().get("content", "")

    # -- knowledge base (authored + generated namespaces) -----------------
    def read_page(self, namespace: str, path: str) -> KBPage:
        r = self._c.get(f"/kb/{namespace}/{path}")
        r.raise_for_status()
        return KBPage.model_validate(r.json())

    def list_kb(self, namespace: str) -> dict:
        r = self._c.get(f"/kb/{namespace}/tree")
        r.raise_for_status()
        return r.json()

    # -- ingestion --------------------------------------------------------
    def ingest(self, req: IngestRequest) -> IngestJob:
        r = self._c.post("/ingest", json=req.model_dump())
        r.raise_for_status()
        return IngestJob.model_validate(r.json())

    def job(self, job_id: str) -> IngestJob:
        r = self._c.get(f"/jobs/{job_id}")
        r.raise_for_status()
        return IngestJob.model_validate(r.json())

    # -- reasoning / decisions -------------------------------------------
    def reason(self, query: str, ruleset: str | None = None) -> ReasonResponse:
        r = self._c.post("/reason", json=ReasonRequest(query=query, ruleset=ruleset).model_dump())
        r.raise_for_status()
        return ReasonResponse.model_validate(r.json())

    def record_decision(self, decision: Decision) -> dict:
        r = self._c.post("/decisions", json=decision.model_dump())
        r.raise_for_status()
        return r.json()

    # -- meta -------------------------------------------------------------
    def health(self) -> dict:
        r = self._c.get("/health")
        r.raise_for_status()
        return r.json()

    @property
    def contract_version(self) -> str:
        return CONTRACT_VERSION

    def close(self) -> None:
        self._c.close()

    def __enter__(self) -> "FabricClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
