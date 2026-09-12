"""RetrievalIndex — hybrid (vector + BM25) retrieval over ingested chunks.

Phase 1 covers the authored KB. ``search`` fuses vector + BM25 rankings with
Reciprocal Rank Fusion (RRF), robust without score calibration across the two very
different scales. ``graph_expand`` adds the third GraphRAG leg — traversal over the
page graph (hierarchy + shared-topic edges) built at ingest. Both return
fabric_client EvidenceUnits.
"""

from __future__ import annotations

import os

from fabric_client.models import EvidenceType, EvidenceUnit, Provenance

from graph.store import GraphStore, InMemoryGraphStore, build_graph_store

from .bm25 import BM25Index
from .chunking import Chunk, chunk_page
from .embedder import Embedder, build_embedder
from .vector_store import VectorStore, build_vector_store

RRF_K = 60  # standard RRF damping constant


def _page_summary(frontmatter: dict, body: str) -> str:
    fm = frontmatter.get("summary")
    if fm:
        return str(fm)
    text = " ".join(body.split())
    return text[:200] + ("…" if len(text) > 200 else "")


def _page_topics(frontmatter: dict) -> list[str]:
    topics = frontmatter.get("topics") or []
    keywords = frontmatter.get("keywords") or []
    out: list[str] = []
    for coll in (topics, keywords):
        if isinstance(coll, list):
            out.extend(str(x) for x in coll)
        elif coll:
            out.append(str(coll))
    return out


def _summary_for(chunk: Chunk) -> str:
    fm_summary = chunk.frontmatter.get("summary")
    if fm_summary:
        return str(fm_summary)
    text = " ".join(chunk.text.split())
    return text[:200] + ("…" if len(text) > 200 else "")


class RetrievalIndex:
    def __init__(
        self,
        embedder: Embedder,
        vector_store: VectorStore,
        graph_store: GraphStore | None = None,
    ) -> None:
        self._embedder = embedder
        self._vs = vector_store
        self._graph = graph_store if graph_store is not None else InMemoryGraphStore()
        self._bm25 = BM25Index()
        self._chunks: dict[str, Chunk] = {}

    # -- ingestion --------------------------------------------------------
    def add_pages(self, pages: list[dict], namespace: str = "authored") -> int:
        """Ingest Markdown pages: [{path, frontmatter, body}]. Returns chunk count."""
        new_chunks: list[Chunk] = []
        for page in pages:
            path = page["path"]
            frontmatter = page.get("frontmatter") or {}
            body = page.get("body") or ""
            new_chunks.extend(
                chunk_page(namespace=namespace, path=path, frontmatter=frontmatter, body=body)
            )
            # Register the page in the graph (hierarchy + topic edges derived on expand).
            self._graph.add_page(
                path=path,
                title=str(frontmatter.get("title") or path),
                summary=_page_summary(frontmatter, body),
                topics=_page_topics(frontmatter),
                section=path.split("/", 1)[0] if "/" in path else "",
            )
        if not new_chunks:
            return 0
        vectors = self._embedder.embed([c.text for c in new_chunks])
        self._vs.upsert([c.id for c in new_chunks], vectors)
        for c in new_chunks:
            self._bm25.add(c.id, f"{c.page_title} {c.section_title} {c.text}")
            self._chunks[c.id] = c
        return len(new_chunks)

    @property
    def size(self) -> int:
        return len(self._chunks)

    # -- retrieval --------------------------------------------------------
    def search(self, query: str, section: str | None = None, top_k: int = 5) -> list[EvidenceUnit]:
        if not self._chunks:
            return []
        pool = max(top_k * 4, 20)
        q_vec = self._embedder.embed([query])[0]
        vec_hits = self._vs.query(q_vec, pool)
        bm25_hits = self._bm25.search(query, pool)

        # Reciprocal Rank Fusion across the two rankings.
        fused: dict[str, float] = {}
        for ranking in (vec_hits, bm25_hits):
            for rank, (cid, _score) in enumerate(ranking):
                fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)

        ranked = sorted(fused.items(), key=lambda x: x[1], reverse=True)
        units: list[EvidenceUnit] = []
        for cid, score in ranked:
            chunk = self._chunks.get(cid)
            if chunk is None:
                continue
            if section and not chunk.path.startswith(f"{section}/"):
                continue
            units.append(
                EvidenceUnit(
                    id=chunk.id,
                    path=chunk.path,
                    title=chunk.page_title,
                    summary=_summary_for(chunk),
                    type=EvidenceType.markdown_chunk,
                    content=chunk.text,
                    score=round(score, 6),
                    provenance=Provenance(source_id=chunk.path, locator=chunk.locator),
                )
            )
            if len(units) >= top_k:
                break
        return units

    # -- graph expansion (GraphRAG third leg) -----------------------------
    def graph_expand(
        self, seed: str, hops: int = 1, rel_types: list[str] | None = None, limit: int = 10
    ) -> list[EvidenceUnit]:
        """Expand from a seed (page path or topic) to connected pages as evidence."""
        hits = self._graph.expand(seed, hops=hops, rel_types=rel_types, limit=limit)
        units: list[EvidenceUnit] = []
        for h in hits:
            units.append(
                EvidenceUnit(
                    id=f"graph:{h['path']}",
                    path=h["path"],
                    title=h["title"],
                    summary=h["summary"],
                    type=EvidenceType.fact,
                    content=f"Related to '{seed}' via {h['relation']} ({h['distance']} hop(s)).",
                    score=round(1.0 / (1 + h["distance"]), 6),
                    provenance=Provenance(source_id=h["path"], locator=h["path"]),
                    entities=[seed],
                )
            )
        return units


def build_index_from_env() -> RetrievalIndex:
    """Construct a RetrievalIndex from environment config."""
    embedder = build_embedder(os.getenv("EMBEDDING_MODEL"))
    vs = build_vector_store(
        os.getenv("VECTOR_STORE"),
        dim=embedder.dim,
        url=os.getenv("QDRANT_URL"),
        collection=os.getenv("QDRANT_COLLECTION", "authored"),
    )
    graph = build_graph_store(os.getenv("GRAPH_STORE"))
    return RetrievalIndex(embedder, vs, graph)
