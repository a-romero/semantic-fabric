# START HERE — semantica enrichment work

You are an engineering agent picking up a multi-phase piece of work on this repository
(`semantic-fabric`). This is the only onboarding you need. Read it top to bottom once, then
begin at **Your first task** below.

---

## 1. Mission (one paragraph)

This project is a retrieval + knowledge-graph platform. Today it under-captures semantic
structure at ingest, so queries can't exploit much. Your job is to make ingestion **enrich**
the data — build a real knowledge graph with typed entities/relations, provenance,
decisions and an ontology — using the third-party library **semantica** (already an optional
dependency, `semantica==0.6.8`) as the enrichment engine, while keeping this project's own
REST API contract and hybrid retrieval as the stable serving layer. The work is specified as
dependency-ordered phases in **`docs/plans/semantica-adoption-plan.md`**. Deliver it
phase by phase.

## 2. Read these, in this order (≤ 30 min)

1. `docs/plans/semantica-adoption-plan.md` — the full plan: target architecture, the
   six phases, and for each phase the exact files/protocols/env-vars/endpoints/tests. **This
   is your specification.**
2. `docs/plans/semantica-spike-findings.md` — currently empty; **you fill it in Phase 0**,
   and every later phase codes against what it says (not against guessed class names).
3. The extension-point patterns you will copy (read the whole file for each):
   - `extraction/extractor.py` — the `Protocol` + `build_*` factory + env-selected backend
     pattern **every** capability in this repo follows.
   - `provenance/store.py` and `graph/store.py` — the same pattern for provenance and the
     graph; `graph/oxigraph_backend.py` for the on-disk Oxigraph/RocksDB store.
   - `api/state.py` — process-shared singletons (`get_*` lazy-build from env, `set_*` for
     tests); `api/main.py` — the routes and how they call state.
   - `client/fabric_client/models.py` — the wire contract (pydantic). You extend this by
     **addition only**.
   - `scripts/validate.sh` and `tests/test_semantica_backends.py` — how optional backends
     are validated on-env.

## 3. Prime directives (do not violate — reviewers reject these)

1. **Pluggable-backend pattern, always.** Each capability = a `Protocol` + a dependency-free
   default that is fully implemented and tested in CI + an optional semantica backend
   imported **lazily**, chosen by an env var via a `build_*()` factory that **falls back to
   the default with a logged warning** on missing dep / failure. Never make the default path
   require semantica.
2. **The REST contract is the boundary.** Evolve `client/fabric_client/models.py` by
   backward-compatible **addition only**. **Never put a semantica-native shape (e.g.
   `ContextGraph`) on the wire** — always project down to this repo's models.
3. **Keep Oxigraph + RocksDB as the graph store.** The graph persists to the embedded
   Oxigraph store at `GRAPH_DB_PATH` (default `./graph-oxigraph`), behind the `GraphStore`
   protocol. semantica *fills* it; it does not replace it with a JSON/Markdown file.
4. **Extraction is LLM-powered via semantica's LLM mode.** semantica's NLP extraction is
   excluded (it produces poor entities on this domain). Drive its entity/relation extractors
   in LLM mode through this repo's existing LiteLLM gateway (`EXTRACTION_MODEL` /
   `LLM_API_BASE` / `LLM_API_KEY`). Do not add an NLP option.
5. **Spike before you code.** semantica 0.6.8 is uneven — some published classes are stubs
   (e.g. `reasoning.SPARQLReasoner`). Confirm real signatures with the Phase-0 scripts before
   writing any semantica adapter. If a class is a stub, ship the default backend + the seam
   anyway and note it in `TODO.md`.
6. **CI stays green on defaults.** `ruff check .` clean and `pytest -q` green (baseline
   **72 passed / 6 skipped**) after every commit. Optional-backend tests use
   `pytest.importorskip("semantica")` and run only via `scripts/validate.sh`.

## 4. Environment & commands

```bash
# from the repo root
pip install -e ./client                       # the wire-contract package (needed for imports)
pip install -e ".[dev,prod,pdf,graph]"        # base + defaults you can run locally
# semantica + llm extras are only needed to RUN the semantica backends / spikes:
pip install -e ".[semantica,llm]"             # on the env that has semantica + gateway creds

ruff check .                                  # lint — must be clean
pytest -q                                     # default suite — must stay 72 passed / 6 skipped
scripts/validate.sh                           # on-env: exercises the real backends (skips what's absent)
```

Gateway/config env vars you will reuse (don't invent new ones for the same purpose):
`EXTRACTION_BACKEND`, `EXTRACTION_MODEL`, `LLM_API_BASE`, `LLM_API_KEY`,
`EXTRACTION_ON_INGEST`, `GRAPH_STORE`, `GRAPH_DB_PATH`, `FABRIC_DB`, `PROVENANCE_BACKEND`,
`REASONING_BACKEND`, `ONTOLOGY_VALIDATOR`.

If a network/proxy issue blocks a semantica model download or a localhost service, do **not**
disable TLS or unset the proxy; check `/root/.ccr/README.md` (this env routes HTTPS through
an agent proxy) and set `NO_PROXY=localhost,127.0.0.1` where a local service is involved.

## 5. Your first task — Phase 0 (do this now)

The Phase-0 spike scripts already exist. On an environment with semantica installed:

```bash
pip install -e ".[semantica,graph,llm]"
python scripts/inspect_semantica_extract.py     # Phase 1 inputs
python scripts/inspect_semantica_kg.py          # Phases 2 & 4 — incl. the pivotal question
python scripts/inspect_semantica_context.py     # Phase 5 inputs
python scripts/inspect_semantica_ontology.py    # Phase 3 inputs
```

Then **fill in `docs/plans/semantica-spike-findings.md`** with the output and your
conclusions, and commit it. The single most important finding is in Spike 2: **does
semantica's KG store persist live to embedded Oxigraph/RocksDB, or only via an RDF export
step?** — it decides the Phase 2 design.

If you cannot access an environment with semantica installed, **stop and report that** — do
not implement semantica adapters from guesses. You may still start the *default* backends of
each phase (they need no semantica), but the semantica-backed halves wait on Phase 0.

## 6. Then work the phases in order

Phase 1 → 2 → 3 → 4 → 5 → 6 (each depends on the ones before; the plan's sequencing table
shows why). For **each phase**:

1. Build the **dependency-free default backend first** and its CI test — this lands value and
   keeps CI green regardless of semantica.
2. Add the **optional semantica backend** behind its env flag, against the confirmed Phase-0
   signatures, with an `importorskip` on-env test and a factory fallback.
3. Wire it into `scripts/validate.sh`; update `README.md` / `demo/RUNBOOK.md` / `TODO.md`.
4. Tick the phase's **Definition of Done** checklist in the plan.

## 7. Working agreement

- **One branch + one PR per phase** (e.g. `feat/phase-1-semantica-extraction`). Keep PRs
  reviewable; do not batch multiple phases.
- Match the surrounding code's style, docstring density and naming. Every new module gets a
  top docstring explaining its backend choices and env vars, like the existing ones.
- Commit messages: conventional, imperative, explain the *why*. Do not include any model or
  assistant identifiers in commits, code, or PRs.
- **Do not** change route signatures, rename/remove contract fields, weaken the graph's
  bounded-traversal safeguards (`expand_max_nodes`), or add per-node graph queries (the
  graph endpoints must use aggregate queries — see `graph/oxigraph_backend.py`).
- When something in the plan proves wrong on-env, update the plan and the findings doc in the
  same PR rather than silently diverging.

## 8. Definition of done (whole effort)

Every phase merged; each with a real default backend (CI-tested) and an on-env semantica
backend behind a flag; the graph still persisting to Oxigraph/RocksDB; `ruff` clean and the
default `pytest` green throughout; the wire contract extended only additively; and
`docs/plans/semantica-spike-findings.md`, `README.md`, `demo/RUNBOOK.md` and `TODO.md` kept
current. Success test: with the semantica backends enabled, an ingest builds a deduplicated,
confidence-and-provenance-bearing knowledge graph with an ontology, and a query returns
evidence plus graph structure, decisions and (where enabled) point-in-time answers — while a
consumer speaking only the REST contract sees no semantica-specific shapes.
