# semantic-fabric

An enterprise **knowledge, context & semantic layer** — the machine-scale half of a
two-repo design. It ingests both curated Markdown and dense heterogeneous data
(PDFs with charts, tables, enterprise databases) into one auditable Context Graph,
and serves retrieval, reasoning, and provenance to agents over **REST + MCP**.

Its companion front-end, [`skilled-agent`](https://github.com/a-romero/skilled-agent),
stays lean and **semantica-free** — it talks to this service only through the
lightweight [`fabric-client`](client/) package. The full rationale lives in
skilled-agent's `docs/SEMANTICA_SEPARATION_DESIGN.md` and
`docs/SEMANTICA_INTEGRATION_VISION.md`.

> **Status: Phase 3 deterministic trio complete (provenance · reasoning · SHACL).**
> Real and wired: `/search` (hybrid vector + BM25, RRF-fused), `/graph/expand`
> (GraphRAG), `/ingest` for `markdown_tree` **and** `pdf_batch`, the `generated/` +
> `authored/` KB namespaces, **`/decisions`** (each agent answer recorded as a decision
> derived from its cited evidence, tamper-evident hash chain, `GET /decisions/{id}/chain`
> for transitive lineage), **`/reason`** (deterministic, explainable inference with a
> rule trace), and **`/validate`** — the SHACL policy gate: check entity data against
> declared constraints (required properties, min values, allowed values) before an
> answer leaves the plane. Runs on pure-Python defaults out of the box; `.[prod]` swaps
> in Qdrant + BGE-M3, `.[semantica]` swaps in real W3C PROV-O provenance, Datalog
> reasoning, and pyshacl SHACL (see ADR 0001). A real PDF layout parser, VLM captioner,
> and LLM-backed extraction remain pluggable layers.

## The boundary

```
skilled-agent  ──HTTP/MCP──►  semantic-fabric        depends on: semantica, vector store,
(RemoteFabricBackend)  ◄── evidence units ──         graph store, VLM, object storage
      │
      └── depends on ──►  fabric-client  ◄── published from this repo (client/)
```

- The wire payload is the **`EvidenceUnit`** — `{content, type, score, provenance}`
  plus a backward-compatible `{path, title, summary}` trio — single-sourced in
  [`client/fabric_client/models.py`](client/fabric_client/models.py).
- skilled-agent falls back to its own Kuzu/BM25 when the fabric is unreachable, so
  the layer is an upgrade, not a prerequisite.

## Two KB namespaces

- **`authored/`** — human-curated Markdown, **pushed to `POST /ingest`** from
  anywhere. Authoritative; the fabric ingests but never overwrites it.
- **`generated/`** — fabric-produced Markdown (dense-PDF summary trees, downward
  projections from graph slices), served over `GET /kb/generated/...`. A materialized
  read-view of the semantic plane — never re-ingested (no feedback loop).

Both are read through the same `GET /kb/{namespace}/{path}` path.

## Layout

```
contracts/     OpenAPI + EvidenceUnit JSON-Schema snapshot (the boundary)
client/        fabric-client: contract types + HTTP client (published; semantica-free)
api/           REST (main.py) + MCP (mcp_server.py) — Phase 0 returns stubs (stubs.py)
ingest/        pipeline: parse·split·extract·conflict·dedup·connectors   (Phase 2+)
retrieval/     hybrid vector + BM25 + graph expansion                    (Phase 1+)
graph/         Context Graph + ontology (OWL/SHACL/SKOS)                 (Phase 1+)
reasoning/     SPARQL / Datalog / SHACL / Rete                           (Phase 3+)
provenance/    PROV-O lineage + decisions                                (Phase 3+)
deploy/        Dockerfile (+ docker-compose.yml at root)
tests/         contract tests (seed of the consumer-driven suite)
```

## Quickstart

```bash
make install          # pip install -e ./client && pip install -e ".[dev]"
make run              # uvicorn api.main:app --reload --port 8080
curl -s localhost:8080/health
curl -s localhost:8080/search -H 'content-type: application/json' \
  -d '{"query":"what are ISAs?","section":"investments","top_k":2}'
make test             # contract tests
make mcp              # run the MCP server (needs the `mcp` extra)
```

### Production backends

```bash
pip install -e ".[prod]"      # qdrant-client + FlagEmbedding
docker compose up -d qdrant   # or point QDRANT_URL at any Qdrant; ':memory:' needs no server
export VECTOR_STORE=qdrant QDRANT_URL=http://localhost:6333 EMBEDDING_MODEL=BAAI/bge-m3
make run
```

- **Qdrant** is validated end to end (its in-memory mode is used by `tests/test_qdrant.py`).
- **BGE-M3** downloads ~2.3GB of weights from HuggingFace on first load, so it needs a
  host with HF egress (or a pre-provisioned model / `HF_ENDPOINT` mirror / a local model
  path as `EMBEDDING_MODEL`). `tests/test_bge_m3.py` skips gracefully where the model
  isn't reachable.

## API surface

| Concern | REST | MCP tool |
|---|---|---|
| Hybrid retrieval | `POST /search` | `search` |
| Graph expansion | `POST /graph/expand` | `graph_query` |
| Fetch detail | `GET /chunk/{ref}` | `get_chunk` |
| Read KB page | `GET /kb/{namespace}/{path}` | `read_page` |
| Browse namespace | `GET /kb/{namespace}/tree` | — |
| Push a source | `POST /ingest` | `ingest` |
| Job status | `GET /jobs/{id}` | — |
| Reasoning | `POST /reason` | `reason` |
| Decisions | `POST /decisions`, `GET /decisions/{id}/chain` | — |

## Roadmap

- **Phase 0** — contract + client + stub API; consumers integrate. ✅
- **Phase 1** — hybrid retrieval (vector + BM25) + GraphRAG expansion over the
  authored KB. ✅
- **Phase 2** — dense-PDF ingestion (prose/tables/figures, figure/VLM branch) + the
  `generated/` namespace. ✅ (pre-parsed `pdf_batch`; real layout parser + one
  enterprise connector are the remaining pluggable pieces.)
- **Phase 3** — reasoning guardrails + decision/provenance recording.
- **Phase 4** — serve additional consumers over MCP (org-wide context layer).
