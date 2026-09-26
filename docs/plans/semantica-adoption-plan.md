# Implementation plan — adopt three semantica capabilities

**Audience:** an independent engineering agent with full access to this repo.
**Status:** ready to implement. **Owner on completion:** update `TODO.md` and this file's checklist.

This plan adds three semantica-backed capabilities, each behind the repo's existing
**pluggable-backend pattern** (a dependency-free default that CI runs, plus an optional
real backend selected by an environment variable and validated on-env via
`scripts/validate.sh`):

1. **`semantic-extract` (NLP) extraction backend** — a second `Extractor` implementation
   using semantica's `semantic_extract` module, selectable alongside the current LLM one
   via `EXTRACTION_BACKEND`.
2. **`kg.GraphAnalyzer` graph analytics** — centrality, community detection and link
   prediction over the knowledge graph, exposed on a new read endpoint and reused to
   improve GraphRAG ranking and the report/explorer.
3. **`context` decision-intelligence** — `find_similar_decisions`,
   `check_decision_rules`, `analyze_decision_impact` on top of the decisions we already
   record.

---

## 0. Non-negotiable conventions (read first)

These mirror how every optional backend in this repo already works. Follow them exactly;
reviewers will reject deviations.

- **Pluggable backend pattern.** Every capability is a `Protocol` with (a) a
  dependency-free default that is fully implemented and tested in CI, and (b) an optional
  real backend imported **lazily** so the base install and CI never require the heavy dep.
  A `build_*(kind)` factory selects by env var and **falls back to the default with a
  logged warning** if the optional dependency is missing or construction fails. See
  `extraction/extractor.py`, `provenance/store.py`, `graph/store.py`,
  `retrieval/vector_store.py` for the canonical shape.
- **Never change route signatures or break the wire contract.** `client/fabric_client/models.py`
  is the single source of truth; evolve by **backward-compatible addition only** (new
  optional fields / new models / new routes). Never rename or remove.
- **Process-shared singletons** live in `api/state.py` (`get_*` builds lazily from env,
  `set_*` for test injection). New services get the same treatment.
- **CI runs defaults only.** The default backend must give a real, useful result with no
  network/model/credential. Optional-backend tests use `pytest.importorskip("semantica")`
  and are wired into `scripts/validate.sh`, never the default `pytest` run.
- **Spike before you code (mandatory).** semantica's `0.6.8` surface is uneven — we
  already found `reasoning.SPARQLReasoner` ships as an unimplemented stub
  (`docs/adr`, `TODO.md`, `scripts/inspect_semantica_graph.py`). **Do not code any
  semantica backend against the class names in this document without first confirming the
  real signatures on an env where semantica is installed.** Each feature below starts with
  a required introspection spike modeled on `scripts/inspect_semantica_graph.py`. If a
  class named here does not exist or is a stub, record it in `TODO.md` and ship the
  default backend + adapter seam anyway (so the switch is a later drop-in).
- **semantica is one package.** `semantic_extract`, `kg`, `context` are submodules of the
  existing `semantica==0.6.8` dependency (`pyproject.toml` `[project.optional-dependencies].semantica`).
  They may pull **transitive** needs (spaCy + a model for NER, networkx for `kg`) — the
  spike must surface these; add them to the `semantica` extra (or a new `nlp` extra) only
  if required.
- **Lint/format/tests gate every commit:** `ruff check .` clean, `pytest -q` green
  (72 passed / 6 skipped baseline as of `b5cab8e`).

---

## Feature 1 — NLP extraction backend (`semantic_extract`)

### Goal
Add `EXTRACTION_BACKEND=nlp` selecting a semantica `semantic_extract`-based `Extractor`,
alongside the existing `null` (default) and `llm` backends. Same `Extraction` output
contract, so **nothing downstream changes** (ingestion graph-enrichment and `/extract`
already consume `Extractor`).

### Where it plugs in (existing anchors)
- Protocol + factory: `extraction/extractor.py` — `Extractor` protocol
  (`extract(text, hint) -> Extraction`, `.name`, `.model`), `NullExtractor`,
  `LLMExtractor`, `build_extractor(kind)`.
- Wiring: `api/state.py::get_extractor()` builds from `EXTRACTION_BACKEND`;
  consumed by `api/main.py::/extract`, and by `retrieval/index.py::apply_extraction`
  (called from `ingest/markdown.py` and `ingest/pdf.py` when `EXTRACTION_ON_INGEST=true`).
- Output contract: `client/fabric_client/models.py` — `Extraction`,
  `ExtractedEntity{name,type}`, `ExtractedRelation{subject,predicate,object,confidence}`.
  **No contract change needed** (confidence already exists).

### Spike (do first)
Create `scripts/inspect_semantica_extract.py` (mirror `inspect_semantica_graph.py`) that,
on an env with `pip install -e ".[semantica]"`, prints:
- `dir(semantica.semantic_extract)` and the real class names (doc claims
  `NamedEntityRecognizer`, `RelationExtractor`, `EventDetector`, `TripletExtractor`).
- `inspect.signature(...)` of each `__init__` and the extract/run method.
- One tiny end-to-end run on a sentence (e.g. *"Aviva offers the Enhanced Pension
  Annuity, a tax-efficient product."*) printing the **exact return shape** (entity fields:
  surface/type/confidence? relation fields: subject/predicate/object/confidence?).
- Whether it needs a spaCy model / other artifact (catch `OSError`/`ImportError` and print
  the remedy).
Paste the output into the PR description; the adapter is written against it, not this doc.

### Build
1. **New file `extraction/semantica_backend.py`** — `class NlpExtractor` implementing the
   `Extractor` protocol:
   - `name = "nlp"`; `model` returns the NER/relation model id if semantica exposes one,
     else `None`.
   - `__init__`: lazily `from semantica.semantic_extract import ...` (eager import so a
     missing extra fails fast at construction, like `SemanticaReasoningEngine`). Read
     `EXTRACTION_MIN_CONFIDENCE` (default `0.0`).
   - `extract(text, hint=None) -> Extraction`: run NER + relation extraction, map results
     into `ExtractedEntity`/`ExtractedRelation`, **filter relations by
     `confidence >= EXTRACTION_MIN_CONFIDENCE`**, dedupe entities by canonical name, and
     return `Extraction(entities=..., relations=...)`. Empty text → `Extraction()`.
     Wrap the semantica call in try/except → log a warning and return `Extraction()` on
     failure (match `LLMExtractor.extract`'s graceful degradation — extraction must never
     fail an ingest).
   - Reuse the entity-span hygiene intent from `_SYSTEM` in `extractor.py` (strip page
     numbers / newlines) if semantica returns raw spans.
2. **Extend `build_extractor(kind)`** in `extraction/extractor.py`: add
   `nlp`/`semantica`/`ner` → `try: from .semantica_backend import NlpExtractor; return NlpExtractor()`
   with the same warn-and-fallback-to-`NullExtractor` as the `llm` branch. Keep the `llm`
   mapping untouched.
3. **Env vars** (document in the module docstring and RUNBOOK §5/§8):
   - `EXTRACTION_BACKEND = null | llm | nlp` (default `null`).
   - `EXTRACTION_MIN_CONFIDENCE` = float, default `0.0` (nlp only).
   - `EXTRACTION_NLP_MODEL` = optional model id if the spike shows one is configurable.
4. **`ExtractResponse.backend`** will now report `"nlp"` automatically (it echoes
   `extractor.name`) — no code change, but add an assertion in tests.

### Tests
- `tests/test_extraction.py` (exists, env-aware): add a case guarded by
  `pytest.importorskip("semantica")` asserting `build_extractor("nlp")` returns an
  `NlpExtractor` and extracts ≥1 entity from the Aviva sentence, with
  `ExtractResponse.backend == "nlp"`. Keep the default (`null`) path assertions unchanged
  so CI is unaffected.
- Add `EXTRACTION_BACKEND` matrix note to `scripts/validate.sh` (see §Cross-cutting).

### Acceptance criteria
- `EXTRACTION_BACKEND=nlp` + `EXTRACTION_ON_INGEST=true` populates the knowledge graph
  with entities/relations **without any LLM/network call**, verifiable via `GET /graph`.
- With semantica absent, `build_extractor("nlp")` logs a warning and returns
  `NullExtractor` (no crash).
- CI (`pytest -q`) unchanged; on-env `validate.sh` exercises the nlp path.

### Risks / unknowns
- semantica NER likely needs a spaCy model download (network/offline concern behind the
  agent proxy). Surface in the spike; if so, document the one-time model install and, if
  the model is cached, note `HF_HUB_OFFLINE`-style offline behavior.
- Quality/latency differ from the LLM path — this is a *choice* the operator makes, not a
  regression. State that in the RUNBOOK.

---

## Feature 2 — Graph analytics (`kg.GraphAnalyzer`)

### Goal
Compute **centrality**, **community detection** and **link prediction** over the
knowledge graph and expose them read-only, then reuse them to (a) rank GraphRAG expansion
and (b) enrich the demo report / explorer.

### Where it plugs in
- Graph store: `graph/store.py` (`GraphStore` protocol, `InMemoryGraphStore`,
  `build_graph_store`, `expand_max_nodes`), `graph/oxigraph_backend.py`
  (`OxigraphGraphStore`, importantly `rdf_graph() -> rdflib.Graph`, `snapshot()`,
  `facts()`, `sparql()`).
- Access: `retrieval/index.py` holds the store (`RetrievalIndex.graph`,
  `.graph_snapshot()`, `.graph_facts()`); `api/state.py::get_index()`.
- Endpoint home: `api/main.py` (`GET /graph` already returns `snapshot()+counts`).

### Spike (do first)
Create `scripts/inspect_semantica_kg.py` printing, on-env:
- `dir(semantica.kg)` and real class names (doc claims `GraphAnalyzer`,
  `CentralityCalculator`, `CommunityDetector`, `PathFinder`, `LinkPredictor`).
- `inspect.signature` of each `__init__` and the analysis methods.
- **Critical:** what input each analyzer accepts — a semantica `GraphBuilder`/`ContextGraph`,
  an `rdflib.Graph`, or a `networkx` graph? Probe by feeding
  `OxigraphGraphStore.rdf_graph()` and also a `networkx.Graph` built from `snapshot()`.
  This decides the adapter shape. If analyzers only accept semantica's own graph object,
  the adapter must first build it from our triples (spike the `GraphBuilder` ingest path).
- Whether `networkx` (or another dep) is required; note it.

### Build
1. **New wire models** (`client/fabric_client/models.py`, additive):
   ```python
   class CentralityScore(BaseModel):   node: str; score: float; type: str = ""
   class Community(BaseModel):          id: int; members: list[str]; size: int
   class LinkPrediction(BaseModel):     source: str; target: str; score: float
   class GraphAnalysisResponse(BaseModel):
       backend: str = "default"
       centrality: list[CentralityScore] = []
       communities: list[Community] = []
       link_predictions: list[LinkPrediction] = []
       counts: dict[str, int] = {}
   ```
2. **New file `graph/analytics.py`** — `GraphAnalytics` protocol
   `analyze(store: GraphStore, top_k: int) -> GraphAnalysisResponse`, plus two backends:
   - **`DefaultGraphAnalytics`** (dependency-free, CI-tested, **real**): compute from
     `store.snapshot()`/`store.facts()` in pure Python — **degree centrality** (rank nodes
     by edge count), **communities = connected components** (union-find over the
     entity/relation edges), and a simple **common-neighbours link-prediction** score for
     top non-adjacent pairs. This keeps the pattern's promise that the default is genuinely
     useful, and gives the endpoint stable semantics regardless of backend.
   - **`SemanticaGraphAnalytics`** (optional): feed the graph (per the spike's answer —
     `rdf_graph()`, a networkx graph, or a built `GraphBuilder`) into
     `kg.CentralityCalculator` / `CommunityDetector` (Louvain/Leiden) / `LinkPredictor`,
     normalize into the same `GraphAnalysisResponse`. Lazy import; try/except per-metric so
     one unsupported metric degrades to empty rather than failing the whole call.
   - `build_graph_analytics(kind)` factory: `GRAPH_ANALYTICS = default | semantica`
     (default `default`), warn-and-fallback like the others.
3. **State + endpoint**:
   - `api/state.py`: `get_graph_analytics()` singleton from `GRAPH_ANALYTICS`.
   - `api/main.py`: `GET /graph/analysis?top_k=20&metrics=centrality,communities,links`
     → `get_graph_analytics().analyze(get_index().graph, top_k)`; response
     `GraphAnalysisResponse`. Keep it read-only and **bounded** (respect `top_k`; cap
     community member lists) — remember the N+1/large-graph lessons in
     `graph/oxigraph_backend.py::snapshot()` and the expansion cap; compute on a single
     `snapshot()`/`rdf_graph()` read, never per-node queries.
4. **Reuse (phase 2 of this feature, keep as separate commits):**
   - **Rank expansion by centrality:** in `retrieval/index.py::graph_expand` (or the
     Oxigraph `expand`), optionally break ties / re-rank `related` results by the
     centrality score of the target page's entities. Gate behind `GRAPH_ANALYTICS=semantica`
     or a flag so default behavior is unchanged.
   - **Report/explorer:** surface top-centrality entities and community count in
     `demo/run_demo.py` (report) and `explorer/` (Overview). Read from `/graph/analysis`.
5. **Optional MCP tool:** add `fabric_graph_analysis` to `fabric_mcp/` (client `analysis()`
   + server tool) so agents can ask "what are the central entities / clusters".

### Tests
- `tests/test_graph_analytics.py` (**runs in CI**): build a small `InMemoryGraphStore`
  with a known topology, assert `DefaultGraphAnalytics.analyze` returns the expected
  most-central node, the right number of connected components, and a plausible link
  prediction. Assert the `/graph/analysis` endpoint shape via `TestClient`.
- On-env: guarded `pytest.importorskip("semantica")` test asserting
  `SemanticaGraphAnalytics` returns non-empty centrality on the same topology; wire into
  `validate.sh`.

### Acceptance criteria
- `GET /graph/analysis` returns real centrality + communities on the default backend with
  no optional deps, bounded by `top_k`, on a large graph in well under a second (use one
  snapshot read; no per-node queries).
- `GRAPH_ANALYTICS=semantica` swaps in Louvain/Leiden + semantica centrality with the same
  response shape.
- No regression to `/graph`, `/graph/expand`, or expansion latency (the cap in
  `expand_max_nodes()` stays authoritative).

### Risks / unknowns
- Whether `kg` analyzers consume `rdflib`/`networkx`/semantica-native graphs (spike
  decides the adapter). If only semantica-native, building its graph from our triples adds
  a conversion step — still fine, just more code.
- Large-graph cost: analytics on thousands of nodes must run on one materialized view; do
  **not** call SPARQL per node (this repo already fixed exactly that class of bug).

---

## Feature 3 — Decision intelligence (`context`)

### Goal
Move beyond "record a decision + trace its lineage" to **`find_similar_decisions`**,
**`check_decision_rules`** (compliance/policy gates), and **`analyze_decision_impact`**,
using semantica's `context` module, while keeping the existing tamper-evident provenance
chain intact.

### Where it plugs in
- Existing decisions: `provenance/store.py` (`ProvenanceStore` protocol,
  `InMemoryProvenanceStore`, `build_provenance_store`, `PROVENANCE_BACKEND`),
  `provenance/semantica_backend.py` (`SemanticaProvenanceStore` via `ProvenanceManager`),
  routes `POST /decisions` + `GET /decisions/{id}/chain` in `api/main.py`, `Decision`
  model, and `fabric_mcp/client.py::answer()` which calls `record_decision` + `decision_chain`.

### Design decision (keep provenance and intelligence separate)
Do **not** overload `ProvenanceStore` (its job is the audit hash-chain). Add a **new,
composable service** `DecisionIntelligence` selected by `DECISION_BACKEND`, that observes
recorded decisions and answers similarity/impact/rule queries. `POST /decisions` records
into **both** the provenance store (lineage, unchanged) **and** the decision-intelligence
store (so similar/impact work). This preserves the existing audit guarantees.

### Spike (do first)
Create `scripts/inspect_semantica_context.py` printing, on-env:
- `dir(semantica.context)` and real classes (doc claims `ContextGraph`, `AgentContext`,
  `AgentMemory`) and the decision-intelligence functions (`record_decision`,
  `trace_decision_chain`, `find_similar_decisions`, `analyze_decision_impact`,
  `check_decision_rules`).
- Exact signatures — **especially the `rules` format** `check_decision_rules` expects
  (SHACL? a rule DSL? predicate callables?) and what `record_decision` takes
  (scenario/outcome/evidence/attrs?).
- Whether `context` has its own storage/persistence (`storage_path`) and whether it
  overlaps `provenance.ProvenanceManager` (so we don't double-persist confusingly).
- A tiny end-to-end: record two similar decisions, call `find_similar_decisions`, print the
  result shape (ids? scores?).

### Build
1. **New wire models** (additive, `client/fabric_client/models.py`):
   ```python
   class SimilarDecision(BaseModel):     decision_id: str; scenario: str; score: float; outcome: str = ""
   class DecisionRuleResult(BaseModel):  conforms: bool; violations: list[str] = []
   class DecisionImpact(BaseModel):      decision_id: str; dependents: list[str] = []; summary: str = ""
   class SimilarDecisionsRequest(BaseModel): scenario: str; top_k: int = 5
   class CheckRulesRequest(BaseModel):   decision: Decision; rules: list[dict] = []
   ```
2. **New package `decisions/`**:
   - `decisions/store.py` — `DecisionIntelligence` protocol:
     `observe(decision_id: str, decision: Decision) -> None`,
     `find_similar(scenario: str, top_k: int) -> list[SimilarDecision]`,
     `check_rules(decision: Decision, rules: list[dict]) -> DecisionRuleResult`,
     `analyze_impact(decision_id: str) -> DecisionImpact`.
   - **`InMemoryDecisionIntelligence`** (default, CI-tested, real): keep a list of
     `(decision_id, Decision)`; `find_similar` = token/Jaccard overlap over scenario text
     (or reuse `retrieval/bm25.py::tokenize` + a tiny cosine over hashing vectors from
     `retrieval/embedder.py::HashingEmbedder` for a real-but-dep-free semantic-ish score);
     `check_rules` = evaluate simple declarative rules (e.g. `{"require_evidence": true}`,
     `{"forbid_outcome": "..."}`) — a small, documented rule vocabulary; `analyze_impact`
     = decisions/entities that cite this decision id (walk the provenance `derived_from`
     back-index).
   - `decisions/semantica_backend.py` — **`SemanticaDecisionIntelligence`**: delegate to
     `semantica.context` per the spike (`ContextGraph`/`AgentContext`), mapping to the same
     return models. Lazy import + graceful per-method fallback.
   - `build_decision_intelligence(kind)` factory: `DECISION_BACKEND = memory | semantica`
     (default `memory`), warn-and-fallback.
3. **State + wiring**:
   - `api/state.py`: `get_decisions()` singleton from `DECISION_BACKEND`.
   - `api/main.py::record_decision` (`POST /decisions`): after
     `get_provenance().record_decision(decision)`, call
     `get_decisions().observe(decision_id, decision)`. Keep the existing response shape;
     it's additive.
   - New routes:
     `POST /decisions/similar` (`SimilarDecisionsRequest` → `list[SimilarDecision]`),
     `POST /decisions/check-rules` (`CheckRulesRequest` → `DecisionRuleResult`),
     `GET /decisions/{decision_id}/impact` (→ `DecisionImpact`).
4. **MCP + answer flow** (optional, high value): add `fabric_similar_decisions` and
   `fabric_check_rules` tools to `fabric_mcp/`. In `fabric_mcp/client.py::answer()`,
   optionally attach `similar_decisions` (precedents) to the returned bundle so an agent
   sees prior rulings — gate behind a flag to avoid extra latency by default.
5. **Persistence:** if `DECISION_BACKEND=semantica` and `context` supports `storage_path`,
   derive it from `FABRIC_DB` like the provenance backend does
   (`<FABRIC_DB>.decisions.db`), so precedents survive restarts. Confirm no conflict with
   the `.prov.db` file in the spike.

### Tests
- `tests/test_decision_intelligence.py` (**CI**): record three decisions via `TestClient`,
  assert `/decisions/similar` ranks the semantically closest first; assert
  `/decisions/check-rules` flags a decision missing required evidence; assert
  `/decisions/{id}/impact` lists a dependent decision. All on the default backend.
- On-env: `pytest.importorskip("semantica")` test for `SemanticaDecisionIntelligence`;
  wire into `validate.sh`.

### Acceptance criteria
- Recording a decision still returns the current shape and still writes the provenance
  hash-chain (existing `tests/` stay green).
- The three new endpoints work on the **default** backend with no optional deps.
- `DECISION_BACKEND=semantica` swaps in `context` with identical response shapes.

### Risks / unknowns
- `check_decision_rules` rule format is the biggest unknown — the default backend defines a
  **small, documented** rule vocabulary; the semantica backend maps to whatever the spike
  reveals. Keep the wire `rules: list[dict]` generic so both fit.
- Overlap between `semantica.context` and `semantica.provenance` storage — resolve in the
  spike so we don't persist the same decision twice in confusing ways.

---

## Cross-cutting work (do once, covers all three)

1. **`pyproject.toml`** — `semantic_extract`/`kg`/`context` are in `semantica==0.6.8`
   already. Only add transitive deps the spikes prove necessary (e.g. `networkx` for `kg`,
   a spaCy model for NER). Prefer adding to the existing `semantica` extra; introduce a new
   extra (e.g. `nlp`) only if a heavy, separable dep warrants it.
2. **`api/state.py`** — three new singletons: `get_extractor` (already exists; nlp is just a
   new `build_extractor` branch), `get_graph_analytics`, `get_decisions`, each with a
   `set_*` for tests.
3. **`scripts/validate.sh`** — add selectors and test files:
   - export `GRAPH_ANALYTICS=${GRAPH_ANALYTICS:-semantica}`,
     `DECISION_BACKEND=${DECISION_BACKEND:-semantica}`; add an
     `EXTRACTION_BACKEND=nlp` run (a second invocation or a matrix note, so both `llm` and
     `nlp` get exercised).
   - add `tests/test_extraction.py` (nlp case), `tests/test_graph_analytics.py`,
     `tests/test_decision_intelligence.py`, and the new `scripts/inspect_semantica_*.py`
     smoke to the run.
4. **Docs** — update `README.md` (capability table + env vars), `docs/guide.html`
   (regenerate via `scripts/build_guide.py` if the backend list is shown), `demo/RUNBOOK.md`
   (§5 env block + §8 troubleshooting rows), and the data-flow story. Mark the adopted
   items done in `TODO.md`, and record any class that turned out to be a stub.
5. **Contract snapshot** — if `EvidenceUnit`/contract JSON snapshots are regenerated by a
   Makefile target (`contracts`), run it after adding models.

---

## Suggested sequencing & effort (independent, shippable per feature)

| # | Work item | Depends on | Rough size |
|---|-----------|-----------|-----------|
| 1 | Spikes: `inspect_semantica_extract/kg/context.py` (all three) | — | 0.5 day (on-env) |
| 2 | Feature 1: NLP extraction backend + tests + docs | spike 1 | 1 day |
| 3 | Feature 2a: `GraphAnalytics` protocol + default backend + `/graph/analysis` + tests | — | 1–1.5 days |
| 4 | Feature 2b: semantica backend + report/explorer/expansion reuse | 3, spike | 1–1.5 days |
| 5 | Feature 3: `decisions/` service + default backend + 3 routes + tests | — | 1.5 days |
| 6 | Feature 3: semantica backend + MCP tools + persistence | 5, spike | 1 day |
| 7 | Cross-cutting: `validate.sh`, README/guide/RUNBOOK/TODO | each feature | 0.5 day |

Features are independent; ship each as its own PR behind its env flag. The **default
backends are real and CI-tested**, so value lands even before the semantica classes are
validated on-env — and if a spike finds a stub (as with `SPARQLReasoner`), the default
ships and the semantica swap is a later drop-in with no API change.

## Definition of done (per feature)
- [ ] Spike output pasted into the PR; adapter written against real signatures.
- [ ] Default backend fully implemented and covered by a CI test.
- [ ] Optional semantica backend behind its env flag, with `importorskip` on-env test.
- [ ] Factory falls back to default (with a logged warning) when semantica is absent.
- [ ] `ruff check .` clean; default `pytest -q` green with no new required deps.
- [ ] `scripts/validate.sh` exercises the new backend on-env.
- [ ] README / RUNBOOK / TODO updated; wire contract additions are backward-compatible.
