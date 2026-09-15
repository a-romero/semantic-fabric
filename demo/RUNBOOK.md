# semantic-fabric — end-to-end runbook

A guided, copy-paste walkthrough that takes a **folder of documents** (Markdown and/or
PDF, nested however you like), ingests it into the platform, exercises **every**
capability against a question you ask, and produces a **single self-contained HTML
report** visualising the corpus, the knowledge graph, and everything the platform did.

Aimed at showing the platform to people across the organisation — no prior knowledge of
the internals required. Runs in ~2 minutes on the built-in sample; point it at your own
folder when you're ready.

---

## 1. What you'll see

The demo drives the platform the way a real application would, one capability per step:

| Step | Capability | What it demonstrates |
|------|-----------|----------------------|
| Ingest | **Multi-format ingestion** | Markdown *and* PDF, from a nested directory, into one knowledge base. PDFs are parsed for text, tables and figures. |
| Extract | **LLM knowledge extraction** | Typed entities and relations pulled from the text (provider-agnostic — your gateway model), building a knowledge graph. |
| Retrieve | **Hybrid retrieval** | Vector + keyword (BM25) search fused together, returning ranked evidence with exact provenance (which page/section/PDF-page). |
| Graph | **GraphRAG expansion** | Following the knowledge graph (hierarchy, shared topics, shared entities, relations) to pull in related material pure search would miss. |
| Reason | **Reason over the KG** | Deterministic Datalog inference over the graph's own facts, with an explanation trace. |
| Prove | **Provenance & lineage** | Every answer/decision recorded as W3C PROV-O with a tamper-evident chain — "why did we conclude this, from what?". |
| Gate | **SHACL policy gate** | A deterministic constraint check an answer must pass before it leaves the platform. |

The report shows all of this as: corpus stat tiles, the KB hierarchy, an interactive
**knowledge-graph diagram**, and a **Question → Answer** panel with the evidence,
reasoning trace, provenance chain and policy result.

---

## 2. Prerequisites

```bash
cd semantic-fabric
python -m venv .venv && source .venv/bin/activate
pip install -e ./client                 # the wire-contract package
pip install -e ".[dev]"                 # runs on pure-Python defaults
```

That's enough for a **quick run** (defaults: in-memory vector store, keyword+hashing
retrieval, no LLM). For the **full experience** (real embeddings, the knowledge graph,
reasoning over it, real PROV-O), also install and configure the real backends — see §5.

---

## 3. Quick run (defaults, ~2 min, no credentials)

Two terminals.

**Terminal A — start the service:**
```bash
cd semantic-fabric
PYTHONPATH=client:. uvicorn api.main:app --port 8080
```

**Terminal B — run the demo against the built-in sample corpus:**
```bash
cd semantic-fabric
PYTHONPATH=client:. python demo/run_demo.py \
  --source demo/sample_corpus \
  --question "Is a Cash ISA tax-free, and who offers it?"
```

Then open **`demo/out/report.html`** in a browser.

On defaults you'll see retrieval, GraphRAG, provenance and the SHACL gate all working.
**Extraction and reason-over-KG will show `n/a`** — they need an LLM, so the knowledge
graph is empty in this mode. That's expected; §5 lights them up.

---

## 4. Point it at your own data

```bash
PYTHONPATH=client:. python demo/run_demo.py \
  --source /path/to/your/folder \
  --question "your question here"
```

- The folder can be **nested**; every `.md` and `.pdf` under it is ingested.
- **Markdown**: optional YAML front-matter is used for the title and topics —
  ```markdown
  ---
  title: Cash ISA
  topics: [savings, tax, isa]
  ---
  # Cash ISA
  ...
  ```
  With no front-matter, the title comes from the first `# heading` or the filename.
- **PDF**: parsed server-side into per-page text, tables and figures (needs the
  `.[pdf]` extra — see §5; without it, PDFs are skipped and reported as such).
- Optional flags: `--seed <page-path>` to fix the GraphRAG starting point,
  `--url http://host:8080` for a remote service, `--out <dir>` for the report location,
  `--batch-size N` (markdown pages per request, default 25) and `--timeout S`
  (per-request seconds, default 600) — see §9 for large corpora.

> The report is a **local file** — your data never leaves your machine. Nothing is
> published anywhere.

### Ask again without re-ingesting

Ingesting and asking are **separate** — once documents are in the service you can ask as
many questions as you like without re-ingesting. Pass `--no-ingest`:

```bash
PYTHONPATH=client:. python demo/run_demo.py --no-ingest \
  --question "which products are tax-advantaged?"
```

Or hit the API directly (the demo is just a driver over it):
`curl -s localhost:8080/search -d '{"query":"...","top_k":5}' -H 'content-type: application/json'`.

**Persisting across restarts:** set `FABRIC_DB=<path>` (and `GRAPH_STORE=rdf` for the
graph) and everything survives a service restart — no re-ingest needed:

```bash
FABRIC_DB=./fabric.db GRAPH_STORE=rdf GRAPH_DB_PATH=./graph-oxigraph \
  PYTHONPATH=client:. uvicorn api.main:app --port 8080
```

`FABRIC_DB` is a SQLite sidecar that persists the retrieval chunks (with their vectors)
and the KB pages; on startup the index rebuilds and `/search`, `/kb` and `--no-ingest`
work immediately against the previously ingested corpus. With
`PROVENANCE_BACKEND=semantica` the **decision lineage** (PROV-O + hash chain) also
persists (to `<FABRIC_DB>.prov.db`, or `PROVENANCE_DB`), so `/decisions/{id}/chain`
survives a restart too. Without `FABRIC_DB` the retrieval index + KB are in-memory (the
default) and a restart needs a re-ingest — the fast structural pass in §9 makes that
quick.

So the full durable set is: `GRAPH_STORE=rdf` (graph) + `FABRIC_DB` (retrieval + KB +,
with the semantica provenance backend, decision lineage).

---

## 5. Full experience (real backends)

The platform selects backends by environment variable; each has a dependency-free
default and an optional real implementation. Install the extras and export the
selectors (this mirrors `scripts/validate.sh`):

```bash
pip install -e ".[prod,semantica,llm,pdf,graph]"

# retrieval: real BGE-M3 embeddings over the in-memory vector store — this alone gives
# real hybrid retrieval, no external service needed. Leave VECTOR_STORE unset (default).
export EMBEDDING_MODEL=BAAI/bge-m3
# The API warms this model at startup (so no query eats the cold load). Once it's cached,
# skip the HuggingFace Hub round-trip on every boot — instant, proxy-independent loads:
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
# OPTIONAL: only if you actually run a Qdrant server. On localhost behind a corporate
# proxy you must also bypass it, or the platform will fall back to in-memory:
#   export VECTOR_STORE=qdrant QDRANT_URL=http://localhost:6333
#   export NO_PROXY=localhost,127.0.0.1

# the knowledge graph: extract entities/relations at ingest, using YOUR gateway model
export EXTRACTION_BACKEND=llm EXTRACTION_ON_INGEST=true
export EXTRACTION_MODEL=gpt-5.1                                  # your LiteLLM gateway model
export LLM_API_BASE=https://<your-ai-gateway>/... LLM_API_KEY=<key>

# deterministic layers via semantica
export REASONING_BACKEND=semantica PROVENANCE_BACKEND=semantica ONTOLOGY_VALIDATOR=shacl

# persistent, SPARQL-native RDF graph (survives restarts, SPARQL-queryable)
export GRAPH_STORE=rdf GRAPH_DB_PATH=./graph-oxigraph

# persist the retrieval index + KB too, so /search and /kb survive a restart (no re-ingest).
# With PROVENANCE_BACKEND=semantica this also persists decision lineage to a sibling
# SQLite file (<FABRIC_DB>.prov.db); override with PROVENANCE_DB if you want it elsewhere.
export FABRIC_DB=./fabric.db

# PDF layout parsing + figure captioning
export PDF_PARSER=pymupdf
export CAPTION_BACKEND=llm CAPTION_MODEL=<a vision-capable gateway model>

PYTHONPATH=client:. uvicorn api.main:app --port 8080
```

Re-run the demo (Terminal B, §3). Now **Extraction** and **Reason over the KG** light
up, and the report's **knowledge-graph diagram** fills with the entities and relations
extracted from your documents.

Notes:
- `EXTRACTION_MODEL` / `CAPTION_MODEL` are LiteLLM model strings — Anthropic, OpenAI,
  Ollama, or your organisation's gateway. **Figure captioning needs a *vision-capable*
  model group**; if your gateway can't serve one, captioning degrades gracefully (uses
  any caption already in the document, else a placeholder).
- Everything degrades gracefully: if an extra isn't installed the platform falls back to
  the default and the demo marks that capability `n/a` rather than failing.

---

## 6. How to read the report

- **What the platform did** — the capability map: a filled dot = exercised, hollow =
  not available in this run (with the reason).
- **Corpus ingested** — stat tiles (files, pages, entities, relations) and the **KB
  hierarchy** derived from your folder structure.
- **Knowledge graph** — a node-link diagram of the extracted entities (coloured by type)
  and their relations; hover a node or edge for detail.
- **Question → Answer** —
  - *Evidence*: the ranked hits for your question, each with type, source path and exact
    locator (page/section, or PDF page + bounding box).
  - *Related via the graph*: pages reached by GraphRAG from the top hit.
  - *Reasoning*: a rule run over the graph's facts, with the derived conclusion and trace.
  - *Provenance & lineage*: the recorded decision, its backend, and whether the
    tamper-evident chain verified — expandable to the raw W3C PROV-O.
  - *SHACL policy gate*: a conforming vs a violating entity, showing the gate accepting
    and rejecting.

`demo/out/report.json` holds the complete raw data behind the report.

---

## 7. The same steps as raw API calls

The demo is a thin driver over the REST API — every step is a plain HTTP call you can
reproduce (useful when integrating a real application):

```bash
# ingest a markdown page
curl -s localhost:8080/ingest -H 'content-type: application/json' -d '{
  "kind":"markdown_tree","namespace":"authored",
  "payload":{"pages":[{"path":"investments/isas/index.md",
    "frontmatter":{"title":"ISAs"},"body":"An ISA is a tax-efficient account from Aviva."}]}}'

curl -s localhost:8080/search        -d '{"query":"is a cash ISA tax free","top_k":5}' -H 'content-type: application/json'
curl -s localhost:8080/graph/expand  -d '{"seed":"investments/isas/index.md","hops":2}' -H 'content-type: application/json'
curl -s localhost:8080/extract       -d '{"text":"Aviva offers the Enhanced Pension Annuity."}' -H 'content-type: application/json'
curl -s localhost:8080/reason        -d '{"query":"offers(aviva, isa)","over_graph":true}' -H 'content-type: application/json'
curl -s localhost:8080/graph                                                              # whole-graph snapshot
DEC=$(curl -s localhost:8080/decisions -d '{"scenario":"q","outcome":"a","evidence":["investments/isas/index.md"]}' -H 'content-type: application/json' | python -c 'import sys,json;print(json.load(sys.stdin)["decision_id"])')
curl -s localhost:8080/decisions/$DEC/chain                                               # PROV-O lineage
```

The same capabilities are also exposed as **MCP tools** — see the next section.

---

## 7b. Query from an agent (MCP)

`fabric_mcp/` is a **standalone, query-focused MCP server** so an agent (Claude Code,
Cursor, …) can drive the fabric directly. It assumes the fabric is already running with
data ingested, and proxies the query surface over HTTP — the agent only needs `mcp` +
Python, not the fabric's backends.

The headline tool is **`fabric_answer`**, which runs the *whole* cycle in one call —
retrieve → graph-expand → record a decision → fetch its provenance lineage — and returns
`{question, evidence[], related[], decision, lineage, guidance}`, everything the agent
needs to answer with citations and an audit trail. Other tools: `fabric_search`,
`fabric_graph_expand`, `fabric_reason`, `fabric_validate`, `fabric_record_decision`,
`fabric_decision_chain`, `fabric_read_page`, `fabric_graph_snapshot`, `fabric_health`.

```bash
pip install -e ".[mcp]"                 # mcp (v1) client library — do this in a venv
```

**Claude Code** — with the fabric running on :8080 (data already ingested):
```bash
claude mcp add semantic-fabric -e FABRIC_URL=http://localhost:8080 -- python -m fabric_mcp
```

**opencode** — add it to `opencode.json` (project root) or `~/.config/opencode/opencode.json`:
```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "semantic-fabric": {
      "type": "local",
      "command": ["/abs/path/to/venv/bin/python", "-m", "fabric_mcp"],
      "environment": { "FABRIC_URL": "http://localhost:8080" },
      "enabled": true
    }
  }
}
```
Use the **absolute** python path of the venv where you ran `pip install -e ".[mcp]"`, so
`fabric_mcp` and `mcp` are importable regardless of opencode's working directory. opencode
picks the tools up on restart; check with `/mcp`.

Then, in either agent, just ask a knowledge question — it calls `fabric_answer`, reads the
returned evidence (each with `provenance.locator`), and answers with citations;
`decision`/`lineage` give the audit trail. Run it by hand with
`FABRIC_URL=http://localhost:8080 python -m fabric_mcp` (stdio). Ingestion is intentionally
**not** exposed here — keep it a separate, deliberate step.

---

## 8. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `could not GET …/health` but `curl` works | A proxy env var (`HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY`) is routing `localhost` through a corporate proxy (often a `400`/`407`). The driver already bypasses proxies; if it persists, `export NO_PROXY=localhost,127.0.0.1`. |
| `could not GET …/health` (nothing listening) | Start the service first (§3, Terminal A). |
| Extraction / Reason show `n/a` | You're on defaults — set `EXTRACTION_BACKEND=llm` + `EXTRACTION_ON_INGEST=true` + a model (§5). |
| Knowledge graph is empty | Same as above — the graph is built from extracted entities/relations. |
| Server log: `VECTOR_STORE=qdrant unavailable … falling back to in-memory` | No Qdrant server, or a proxy is intercepting `localhost:6333`. Retrieval still works (in-memory + real embeddings). To use Qdrant, run the server and `export NO_PROXY=localhost,127.0.0.1`; otherwise leave `VECTOR_STORE` unset. |
| PDFs reported as `failed` | Install `.[pdf]` and set `PDF_PARSER=pymupdf`. |
| Captions are placeholders | The caption model isn't vision-capable on your gateway; set `CAPTION_MODEL` to one that is (optional). |
| Reasoning answer is `No` | The synthesized demo rule derives from the *first* extracted relation; with an empty graph there are no relations to reason over. |
| Client `timed out` / ingest very slow on a big corpus | Extraction-on-ingest is one LLM call per page — see §9. |
| **First `/search` after a (re)start hangs ~10s+, later queries are instant** | With `EMBEDDING_MODEL=BAAI/bge-m3`, the model loads on first use. The API now **warms it at startup** (uvicorn holds "startup" until the model is loaded — a slow boot, never a hung query). If boot itself is slow/variable, it's the HuggingFace Hub round-trip through your proxy: once the model is cached, `export HF_HUB_OFFLINE=1` (and `TRANSFORMERS_OFFLINE=1`) to load from local cache with **no** Hub call. Set `WARM_INDEX=false` to opt out of warm-up. |
| Server log: `search stages (ms): … total=…` | Per-stage `/search` timing. `SEARCH_TIMING=1` logs every query; any stage over `SEARCH_SLOW_MS` (default 1500) warns. `vector=` high → Qdrant/proxy; `bm25=` high → lexical scan; `embed=` high → embedder (should be one-off; see the row above). `scripts/diag_search.py` isolates Qdrant-vs-proxy end to end. |

---

## 9. Large corpora & performance

Ingest cost is dominated by **LLM extraction: one model call per page** (only when
`EXTRACTION_ON_INGEST=true`). Retrieval indexing itself is fast. For hundreds–thousands
of documents:

- **The driver batches automatically** — markdown goes up `--batch-size` pages per
  request (default 25), each batch reports progress, and a failed/timed-out batch is
  recorded and skipped rather than losing the whole run. Lower `--batch-size` (e.g. 10)
  for more frequent checkpoints; raise `--timeout` (default 600s) for slow gateways.
- **Speed extraction up with `EXTRACTION_CONCURRENCY`** (server-side, default 4): the
  per-page LLM calls are network-bound and run concurrently. Raise it (e.g. `8`–`16`)
  to ingest faster; lower it to `1` if your gateway rate-limits (a rate-limited call
  degrades to "no extraction for that page", it doesn't fail the ingest).
  ```bash
  EXTRACTION_CONCURRENCY=8 ... uvicorn api.main:app --port 8080
  ```
- **Fast structural pass (no LLM):** to ingest a large corpus quickly for retrieval +
  the KB hierarchy without building the entity graph, start the service **without**
  `EXTRACTION_ON_INGEST`. Search, GraphRAG (hierarchy/topics), provenance and the SHACL
  gate all still work; the knowledge-graph diagram and reason-over-KG will be `n/a`.
  You can enrich later by re-ingesting with extraction enabled.

Rough guide: with `EXTRACTION_CONCURRENCY=8` and a ~2s/call gateway, ~850 pages ingest
in a handful of minutes; serially it would be ~30+ minutes. Without extraction, seconds.
