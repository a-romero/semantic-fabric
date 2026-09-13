# On-env validation

CI runs only the pure-Python defaults (in-memory vector store + graph + KB, hashing
embedder, simple reasoner/validator, null extractor, null captioner, null PDF parser).
The **real backends** — Qdrant, BGE-M3, the semantica layers (PROV-O provenance,
Datalog reasoning, SHACL), LiteLLM extraction, LiteLLM VLM figure captioning, PyMuPDF
layout parsing, and the persistent Kuzu (LPG) / Oxigraph (RDF) graph stores — need
models/services/credentials CI doesn't have, so they run behind optional extras and
are validated on a capable host.

## One command

```bash
scripts/validate.sh
```

It installs the extras, sets the backend selectors, and runs the opt-in suites. Each
layer runs only if its dependency + credential are present; anything missing **skips
with a reason** (shown via `pytest -rs`). A **failure** means a real backend is broken
(e.g. a semantica API drifted from the spike) and needs a fix.

## What it checks

| Layer | Test | Requires | Validates |
|---|---|---|---|
| Vector store | `test_qdrant.py` | `qdrant-client` | Qdrant round-trip (create/upsert/`query_points`) via in-memory mode; ISA ranked first |
| Embeddings | `test_bge_m3.py` | `FlagEmbedding` + HF egress | BGE-M3 loads; dim 1024; real dense vectors |
| Provenance | `test_semantica_backends.py` | `semantica` | real W3C PROV-O export + `verify_chain` tamper-evidence |
| Reasoning | `test_semantica_backends.py` | `semantica` | Datalog/forward-chaining derives the fact, with an explanation trace |
| Ontology / SHACL | `test_semantica_backends.py` | `semantica`/`pyshacl` | conforming passes, violating fails |
| Extraction | `test_extraction.py` (`test_llm_extractor_live`) | `litellm` + `EXTRACTION_LIVE=1` + provider creds | typed entities/relations from real text |
| PDF layout | `test_pdf_parser.py` (`test_pdf_pymupdf_live`) | `PyMuPDF` (`.[pdf]`) | raw PDF bytes → per-page text/tables/figures (parses a PDF synthesized with fitz) |
| VLM captioning | `test_captioner.py` (`test_llm_captioner_live`) | `litellm` + `CAPTION_LIVE=1` + vision model creds | a real caption generated from image bytes |
| Graph (LPG) | `test_graph_persistence.py` | `kuzu` (`.[graph]`) | pages/entities/relations persist to Kuzu and reload into a fresh store |
| Graph (RDF) | `test_graph_persistence.py` | `pyoxigraph` (`.[graph]`) | same graph persists to Oxigraph as RDF triples and reloads |

Provider for extraction is chosen by `EXTRACTION_MODEL`, for captioning by `CAPTION_MODEL`
(`anthropic/claude-opus-5` | `openai/gpt-4o-mini` | `ollama/llama3.1` | proxy — the
captioner needs a **vision-capable** model). The persistent graph store is selected by
`GRAPH_STORE` (`lpg` = Kuzu, `rdf` = Oxigraph) at `GRAPH_DB_PATH`; the PDF parser by
`PDF_PARSER=pymupdf` and the captioner by `CAPTION_BACKEND=llm`.

## Live end-to-end (optional)

`scripts/validate.sh` prints a copy-paste block to start the service with the real
backends and hit `/ingest` (with `EXTRACTION_ON_INGEST=true`), `/search`, `/extract`,
`/reason`, `/decisions` + `/decisions/{id}/chain`.

## skilled-agent round-trip

With the fabric running on `:8080`:

```bash
# in the skilled-agent repo
pip install "fabric-client @ git+https://github.com/a-romero/semantic-fabric.git#subdirectory=client"
export RETRIEVAL_BACKEND=fabric FABRIC_URL=http://localhost:8080 RECORD_DECISIONS=true
python - <<'PY'
from backend.knowledge.knowledge_graph import KnowledgeGraph
kg = KnowledgeGraph()
print("search:", [r["path"] for r in kg.search("tax efficient savings", top_k=3)])
print("graph :", [r["path"] for r in kg.graph_expand("investments/isas/index.md")])
print("decide:", kg.record_decision("q", "a", evidence=["investments/isas/index.md"]))
PY
```

Then `GET /decisions/{id}/chain` on the fabric shows the recorded decision's lineage.

## Notes / known-risk areas (from the spike)

- **semantica is pinned to `0.6.8`** (ADR 0001). If these tests fail after a bump,
  suspect API drift; the adapters vendor the spike's workarounds (`parent_entity_id`,
  `valid_until`) and may need updating.
- **BGE-M3** needs HuggingFace egress on first load (or a local model path /
  `HF_ENDPOINT` mirror).
