# Implementation plan — enrich at ingest with semantica, serve through our contract

**Audience:** an independent engineering agent with full access to this repo.
**Supersedes:** the earlier three-feature draft (NLP extraction / kg analytics / decision
intelligence). Those capabilities survive, but re-sequenced into dependency-ordered phases
that reflect what we concluded:

- **Query-time richness is capped by what ingest materialises.** The goal is to capture as
  much semantic structure as possible **at ingest** — a properly-built knowledge graph,
  typed evidence, provenance, decisions and an ontology — so the query layer can exploit it
  fully. Ingest pays the cost once and writes it down durably; query is read + fuse.
- **semantica is the enrichment core; our platform is the serving layer.** semantica's
  pipeline (extract → conflict → dedupe → KG build → ontology · provenance · decisions)
  enriches at ingest. Our retrieval (chunks + vectors + BM25 + RRF, page/bbox-grade
  evidence) and our **REST contract** (`client/fabric_client/models.py`) stay the stable
  serving boundary.
- **Keep Oxigraph + RocksDB as the canonical graph store.** semantica *fills* the graph;
  the graph still physically lives in the embedded Oxigraph RocksDB directory
  (`GRAPH_DB_PATH`). The substrate stays behind our `GraphStore` protocol.
- **Extraction is LLM-powered, via semantica in LLM mode.** semantica's *NLP* extraction
  was tried on-env and produced wrong entities — it is **not used**. We use semantica's
  entity/relation extractors in their **LLM mode**, driven through our existing gateway.

---

## Target architecture (what we are building toward)

```
INGEST (materialise, once)                         SERVE (read + fuse, per query)
  sources ─▶ parse/normalise/split
          ─▶ EXTRACT (semantica, LLM mode) ─┐
          ─▶ conflict-detect + dedupe       │        POST /search  ─▶ hybrid retrieval (ours)
          ─▶ build KG (semantica)  ─────────┼──▶  ┌──────────────────┐   + graph expand (enriched KG)
          ─▶ ontology gen/align             │     │  our REST        │   + reason (ontology-aware)
          ─▶ provenance + decisions         │     │  contract        │   + decisions (precedents/rules)
          ─▶ embeddings + BM25   ───────────┘     │  (stable         │   + validate (generated ontology)
                                                   │   boundary)      │   + as_of (bitemporal)
   Physical stores:                                └──────────────────┘
     • Knowledge graph  → Oxigraph / RocksDB  (GRAPH_DB_PATH)   ← semantica writes here
     • Chunks + vectors → FABRIC_DB SQLite  (+ Qdrant vectors, optional)
     • KB pages         → FABRIC_DB SQLite
     • Object store     → figure bytes
     • Provenance       → semantica PROV-O (SQLite sibling of FABRIC_DB)
```

**The two indices, linked.** Ingest maintains (1) the **retrieval index** (chunks/vectors/
BM25 — evidence with page/bbox citations) and (2) the **enriched KG** in Oxigraph/RocksDB
(entities/relations with confidence + provenance, ontology types, communities). They are
joined by **entity ids** and **source locators**, so a query fuses evidence and structure.
Neither replaces the other: semantica's KG does not model "a ranked chunk with a bounding
box"; our retrieval does not model dedup families, confidence-weighted edges or an ontology.

**What materialises where, and when:**

| Stage | Materialise at **ingest** (durable) | Read at **query** (no recompute) |
|---|---|---|
| Extraction | typed entities, relations, events, triplets **with confidence** | — |
| Entity resolution | conflict-detected + **deduplicated** canonical entities (families) | — |
| KG build | edges with **per-fact provenance + confidence** in **Oxigraph/RocksDB** | graph-expand, filtered by confidence |
| Ontology | generated/aligned OWL + SHACL, entities typed against it | validation + reasoning use the real schema |
| Analytics | cached centrality + communities | ranking / clustering in results |
| Provenance/decisions | PROV-O per fact; decision context recorded | precedents, impact, rule checks |
| Temporal | `valid_time` / `recorded_time` populated per fact | point-in-time (`as_of`) queries |
| Retrieval | embeddings + BM25 | hybrid RRF, evidence + citations |

---

## Conventions (non-negotiable — read before any phase)

Mirror how every optional backend already works; reviewers reject deviations.

- **Pluggable backend pattern.** Each capability is a `Protocol` with (a) a dependency-free
  default fully implemented and tested in CI, and (b) an optional real backend imported
  **lazily**. A `build_*(kind)` factory selects by env var and **falls back to the default
  with a logged warning** on missing dep / construction failure. Canonical shapes:
  `extraction/extractor.py`, `provenance/store.py`, `graph/store.py`,
  `retrieval/vector_store.py`.
- **Our REST contract is the boundary.** `client/fabric_client/models.py` evolves by
  **backward-compatible addition only** (new optional fields, models, routes). **Never leak
  `ContextGraph`/semantica-native shapes onto the wire** — always project down to our
  models. This is what protects consumers (skilled-agent) from semantica's `0.6.x` churn.
- **Keep Oxigraph/RocksDB.** The graph persists to the embedded Oxigraph store at
  `GRAPH_DB_PATH` (default `./graph-oxigraph`), behind `GraphStore` (`graph/store.py`).
  semantica is configured to write into it; it is not replaced by a JSON/Markdown
  ContextGraph file. The in-memory default backend still runs in CI.
- **Process-shared singletons** in `api/state.py` (`get_*` lazy-build from env, `set_*` for
  tests). New services get the same treatment.
- **CI runs defaults only.** Optional-backend tests use `pytest.importorskip("semantica")`
  and are wired into `scripts/validate.sh`, never the default `pytest` run.
- **Spike before you code (mandatory).** semantica `0.6.8` is uneven — we already found
  `reasoning.SPARQLReasoner` ships as a stub (`scripts/inspect_semantica_graph.py`,
  `TODO.md`). Every phase that touches semantica starts with an on-env introspection spike
  (model: `scripts/inspect_semantica_graph.py`). If a class named here is absent or a stub,
  record it in `TODO.md` and ship the default backend + adapter seam anyway (drop-in later).
- **Gates:** `ruff check .` clean; default `pytest -q` green (baseline **72 passed /
  6 skipped**, commit `b5cab8e`); wire additions backward-compatible.

---

## Phase 0 — Spikes & foundations (prerequisite, no production code)

Confirm the real semantica surface on an env with `pip install -e ".[semantica,graph]"` and
credentials. Deliver one PR: the spike scripts + a `docs/plans/semantica-spike-findings.md`
note. **No phase below is coded against the class names in this document until Phase 0
confirms them.**

Spike scripts to add (mirror `scripts/inspect_semantica_graph.py`):
1. `scripts/inspect_semantica_extract.py` — real class names for entity + relation
   extraction (doc suggests `NamedEntityRecognizer`/`NERExtractor`, `RelationExtractor`,
   `EventDetector`, `TripletExtractor`); **how to force LLM mode** (`method="llm"` or a
   config flag); how to pass our gateway model (reuse `EXTRACTION_MODEL` / `LLM_API_BASE` /
   `LLM_API_KEY`); and the **exact output schema** (entity fields incl. confidence?, relation
   fields, events, triplets). Run it on the Aviva sentence and paste the shape.
2. `scripts/inspect_semantica_kg.py` — `semantica.kg` class names (`GraphBuilder`,
   `GraphAnalyzer`, `CentralityCalculator`, `CommunityDetector`, `LinkPredictor`); **and the
   decisive question: does the KG store persist live to an embedded Oxigraph store, or only
   via `RDFExporter`?** Probe configuring Oxigraph as the backend and re-opening the same
   RocksDB path; also probe feeding `OxigraphGraphStore.rdf_graph()` / a networkx graph to
   the analyzers.
3. `scripts/inspect_semantica_context.py` — `semantica.context` decision APIs
   (`record_decision`, `find_similar_decisions`, `check_decision_rules` — **especially the
   rules format**, `analyze_decision_impact`), and whether `context` persistence overlaps
   `provenance.ProvenanceManager`.
4. `scripts/inspect_semantica_ontology.py` — `OntologyGenerator` / `OntologyValidator`
   signatures; can it generate OWL/SHACL from a set of typed entities; SKOS support.

**Phase 0 acceptance:** every downstream phase's semantica calls are pinned to confirmed
signatures; the Oxigraph-persistence question (live vs export) is answered and drives
Phase 2's design.

---

## Phase 1 — Rich extraction (the linchpin)

**Why first:** every later layer (KG, ontology, analytics, decisions) is built from
extracted facts. Empty extraction ⇒ vacuous everything.

**Goal:** an `EXTRACTION_BACKEND=semantica` extractor using semantica's entity + relation
extractors in **LLM mode**, driven through our gateway, emitting richer typed output than we
have today, so it can feed semantica's KG builder (Phase 2).

**Anchors:** `extraction/extractor.py` (`Extractor` protocol `extract(text, hint) -> Extraction`,
`.name`, `.model`; `build_extractor(kind)`); `api/state.py::get_extractor`; consumers
`api/main.py::/extract`, `retrieval/index.py::apply_extraction` (called from
`ingest/markdown.py` + `ingest/pdf.py` when `EXTRACTION_ON_INGEST=true`). Contract:
`Extraction`, `ExtractedEntity{name,type}`, `ExtractedRelation{subject,predicate,object,confidence}`.

**Build:**
1. **`extraction/semantica_backend.py`** — `class SemanticaExtractor` (name `"semantica"`)
   implementing `Extractor`. Eager-import the extractor classes; construct them in **LLM
   mode** with our gateway model/base/key. `extract(text, hint)` → run NER + relation (and,
   if the spike shows value, event/triplet) extraction → map to `Extraction`. Filter by
   `EXTRACTION_MIN_CONFIDENCE` (default `0.0`). Empty text → `Extraction()`. try/except →
   warn + `Extraction()` (extraction must never fail an ingest, matching `LLMExtractor`).
   Keep the entity-span hygiene intent from `_SYSTEM` in `extractor.py`.
2. **Extend `build_extractor(kind)`**: add `semantica` → lazy `SemanticaExtractor` with the
   warn-and-fallback-to-`NullExtractor` pattern. **Keep the existing `llm` (LiteLLM) backend
   unchanged** as the non-semantica path. **Do not add an `nlp` backend** (semantica NLP
   mode is excluded by decision — note this in the docstring).
3. **Contract (additive):** add optional `confidence: float | None = None` to
   `ExtractedEntity`, and — if the spike confirms value — new optional
   `events: list[...]` / `triplets: list[...]` on `Extraction`. Backward-compatible;
   existing consumers ignore them.
4. **Env:** `EXTRACTION_BACKEND = null | llm | semantica` (default `null`);
   `EXTRACTION_MIN_CONFIDENCE` (default `0.0`); reuse `EXTRACTION_MODEL` / `LLM_API_BASE` /
   `LLM_API_KEY`. Document in the module docstring + RUNBOOK §5/§8.

**Integration depth:** Phase 1 keeps the **shallow** path (map to `Extraction`, feed our
existing graph) so it ships standalone. The **deep** path (keep native objects → semantica
KG builder) is Phase 2.

**Tests:** `tests/test_extraction.py` — a `pytest.importorskip("semantica")` case asserting
`build_extractor("semantica")` extracts ≥1 correct entity/relation from the Aviva sentence
with `ExtractResponse.backend == "semantica"` and confidence populated. Default (`null`)
path unchanged. Wire into `validate.sh`.

**Acceptance:** `EXTRACTION_BACKEND=semantica` + `EXTRACTION_ON_INGEST=true` populates the
graph via our existing `apply_extraction`, verifiable on `GET /graph`, using the LLM mode
through our gateway. semantica absent ⇒ warn + `NullExtractor`. CI unchanged.

**Risks:** exact class/flag names (Phase 0); LLM latency/cost is a deliberate operator
choice (document); gateway model must be capable — reuse the proven `EXTRACTION_MODEL`.

---

## Phase 2 — Enriched KG build in Oxigraph/RocksDB

**Why here:** turns Phase 1's per-page extraction into a *resolved, provenance-bearing*
graph — the substrate everything queries.

**Goal:** route extraction output through semantica's **conflict detection → deduplication →
KG build**, persisting into the **embedded Oxigraph store (RocksDB)**, behind our
`GraphStore` protocol. Entities become canonical/deduped; edges carry confidence + per-fact
provenance.

**Anchors:** `graph/store.py` (`GraphStore` protocol, `InMemoryGraphStore`,
`build_graph_store`, `GRAPH_STORE`, `expand_max_nodes`); `graph/oxigraph_backend.py`
(`OxigraphGraphStore`, `rdf_graph()`, `snapshot()`, `facts()`, `sparql()`, `GRAPH_DB_PATH`);
`retrieval/index.py` (`apply_extraction`, `add_pages`, `graph_*`).

**Design (driven by Phase 0's live-vs-export answer):**
- **If semantica KG persists live to embedded Oxigraph:** add
  `graph/semantica_backend.py::SemanticaGraphStore` implementing `GraphStore`, configured
  with the **same `GRAPH_DB_PATH` RocksDB directory**. `build_graph_store` gains
  `GRAPH_STORE=semantica`. Extraction (Phase 1, deep path) hands native objects to
  semantica's `GraphBuilder` (with conflict/dedup) which writes triples into Oxigraph. Our
  `expand`/`snapshot`/`facts` either delegate to semantica or keep reading the same store
  via SPARQL (reuse the bounded, aggregate-query patterns already in
  `oxigraph_backend.py` — **never per-node queries**).
- **If it only exports:** keep `OxigraphGraphStore` as the store of record; add an
  end-of-ingest step that runs semantica's conflict/dedup/build in-memory then
  `RDFExporter` → load the triples into our `pyoxigraph.Store` at `GRAPH_DB_PATH`.
- Either way: **RocksDB stays the physical home**; the enriched model (confidence,
  provenance, dedup families) is represented as additional RDF predicates in our `ex:`
  vocabulary (extend the vocabulary block documented in `oxigraph_backend.py`).

**Ingest wiring:** extend `retrieval/index.py::apply_extraction` (or a new
`apply_extraction_enriched`) so the deep path carries confidence/provenance onto edges;
`ingest/markdown.py` + `ingest/pdf.py` already call it.

**Serving (additive):** `GET /graph` and `/graph/expand` gain optional
`?min_confidence=` filtering; `EvidenceUnit`/graph responses may surface entity confidence.

**Tests:** CI-level test on `InMemoryGraphStore` proving dedup/confidence plumbing with a
fake extractor (two mentions of "Aviva" collapse to one canonical entity; edge confidence
preserved). On-env `importorskip` test proving `SemanticaGraphStore` reopens the **same
RocksDB path** and returns the enriched graph. Wire into `validate.sh`.

**Acceptance:** after an enriched ingest, `GET /graph` shows deduped entities with
confidence; the graph is durable in the RocksDB dir and reloads on restart;
`/graph/expand?min_confidence=` filters. Expansion latency stays bounded (`expand_max_nodes`
remains authoritative).

**Risks:** the live-vs-export path is the pivotal unknown (Phase 0); RDF vocabulary
extension must stay query-efficient (aggregate queries only — this repo already fixed an
N+1 snapshot and an unbounded expand).

---

## Phase 3 — Ontology generation & governance

**Why here:** reasoning and validation only reach "full potential" against a real schema.
Needs typed entities (Phases 1–2) to exist.

**Goal:** at ingest, seed a small hand-authored domain ontology (insurance/pensions core
classes) and **auto-generate/align** the rest with semantica's `OntologyGenerator`; type
extracted entities against it; validate with SHACL (we already have `run_shacl_validation`);
optional SKOS vocabulary.

**Anchors:** `ontology/validator.py`, `ontology/shacl_backend.py` (`run_shacl_validation`,
`ONTOLOGY_VALIDATOR`); contract `OntologyConstraint`, `ValidateRequest`, `Violation`.

**Build:** `ontology/generator.py` (`OntologyGenerator` backend + a dependency-free default
that derives a trivial class/property list from the graph's entity/relation types); persist
the generated ontology (Turtle) alongside the graph (a sibling file of `GRAPH_DB_PATH`, or a
named graph in Oxigraph). Wire `POST /validate` (and reason-over-KG) to load the generated
ontology instead of only ad-hoc constraints. Env `ONTOLOGY_BACKEND = none | generate`.

**Serving (additive):** `GET /ontology` (classes/properties/shapes); `/validate` uses the
generated ontology automatically.

**Tests:** CI test that the default generator produces classes for the entity types present
and that `/validate` still conforms/violates correctly; on-env test for real OWL/SHACL
generation.

**Acceptance:** entities are typed against a schema derived from the corpus; `/validate` and
reasoning consult it; the ontology persists with the graph.

**Risks:** ontology auto-generation quality varies — seed the core classes by hand and treat
generation as *extension*, not sole source.

---

## Phase 4 — Graph analytics (`kg.GraphAnalyzer`)

**Why here:** analytics need a populated, resolved graph (Phases 1–2). Compute **at ingest**,
cache, read at query.

**Goal:** centrality, community detection, link prediction over the enriched KG, exposed
read-only and reused for expansion ranking + report/explorer.

**Build:** `graph/analytics.py` — `GraphAnalytics` protocol
`analyze(store, top_k) -> GraphAnalysisResponse`; **`DefaultGraphAnalytics`** (pure-Python,
CI-tested: degree centrality, connected-component communities, common-neighbour link
prediction from one `snapshot()`); **`SemanticaGraphAnalytics`** (Louvain/Leiden + semantica
centrality, per Phase 0's input-type answer). Factory `GRAPH_ANALYTICS = default | semantica`.
Additive contract models `CentralityScore` / `Community` / `LinkPrediction` /
`GraphAnalysisResponse`. `api/state.py::get_graph_analytics`; endpoint
`GET /graph/analysis?top_k=&metrics=`. Cache results at ingest; recompute on graph change.
Reuse: optional centrality re-ranking in `graph_expand`; surface top entities + community
count in `demo/run_demo.py` and `explorer/` Overview. Optional MCP tool
`fabric_graph_analysis`.

**Tests:** CI test on a known topology (expected most-central node, component count); on-env
semantica test. **Compute on one materialised view — never per-node queries.**

**Acceptance:** `GET /graph/analysis` returns real centrality + communities on the default
backend, bounded by `top_k`, sub-second on a large graph; semantica backend swaps in
Louvain/Leiden with the same shape; no regression to `/graph`/`/graph/expand`.

---

## Phase 5 — Decisions & provenance intelligence (`context`)

**Why here:** precedent/impact/rules are most useful once evidence + a real graph exist.
Keeps the tamper-evident provenance chain intact.

**Goal:** beyond "record + trace lineage", add `find_similar_decisions`,
`check_decision_rules` (compliance gates), `analyze_decision_impact`, via semantica's
`context`, **composed with** (not replacing) the provenance hash-chain.

**Anchors:** `provenance/store.py` (chain unchanged), `provenance/semantica_backend.py`
(`ProvenanceManager`), routes `POST /decisions` + `GET /decisions/{id}/chain`, `Decision`
model, `fabric_mcp/client.py::answer()`.

**Build:** new package `decisions/` — `DecisionIntelligence` protocol
(`observe(decision_id, decision)`, `find_similar(scenario, top_k)`,
`check_rules(decision, rules)`, `analyze_impact(decision_id)`); **`InMemoryDecisionIntelligence`**
default (Jaccard/hashing-embedding similarity over scenarios; a small documented rule
vocabulary; impact via the provenance back-index) and **`SemanticaDecisionIntelligence`**
(delegates to `context`, per Phase 0). Factory `DECISION_BACKEND = memory | semantica`.
`api/state.py::get_decisions`. `POST /decisions` records into provenance **and** calls
`observe()`. New routes `POST /decisions/similar`, `POST /decisions/check-rules`,
`GET /decisions/{id}/impact`; additive models. Optional MCP tools + attach precedents to
`answer()`. If `context` supports `storage_path`, derive `<FABRIC_DB>.decisions.db` (confirm
no clash with `.prov.db`).

**Tests:** CI (default backend): similar-ranking, rule violation, impact listing via
`TestClient`; existing provenance tests stay green. On-env semantica test. Wire into
`validate.sh`.

**Acceptance:** recording still returns the current shape and still writes the hash-chain;
the three new endpoints work on the default backend; `DECISION_BACKEND=semantica` swaps in
`context` with identical shapes.

---

## Phase 6 — Bitemporal (point-in-time)

**Why last:** depends on facts carrying provenance/time from Phases 1–2.

**Goal:** populate `valid_time` / `recorded_time` (already fields on `Provenance` and
`Decision`, currently inert) at ingest, and add point-in-time query.

**Build:** carry temporal fields onto graph edges (semantica's bitemporal model / the RDF
vocabulary from Phase 2). Add optional `as_of: str | None` to `SearchRequest` /
`GraphExpandRequest` (additive) and filter the enriched graph by validity at query time
(`ContextGraph`'s `is_active(at_time)` semantics, or a SPARQL time filter). Env
`ENABLE_TEMPORAL` if a gate is wanted.

**Tests:** CI test that an `as_of` before/after a fact's `valid_from` includes/excludes it
(default backend, using a simple validity filter); on-env semantica test.

**Acceptance:** `POST /search?...as_of=` and graph expansion respect validity windows;
non-temporal queries unchanged.

**Risks:** temporal correctness is subtle — keep the default filter simple and well-tested;
lean on semantica's model on-env.

---

## Cross-cutting (do alongside the phases)

- **`pyproject.toml`:** `semantic_extract`/`kg`/`context`/`ontology` are in
  `semantica==0.6.8`. Add only transitive deps the spikes prove necessary (e.g. `networkx`
  for `kg`) to the `semantica` (or a new focused) extra. `graph` extra already has
  `pyoxigraph`/`rdflib`.
- **`scripts/validate.sh`:** add selectors (`EXTRACTION_BACKEND=semantica`,
  `GRAPH_STORE=semantica` or the export step, `GRAPH_ANALYTICS=semantica`,
  `ONTOLOGY_BACKEND=generate`, `DECISION_BACKEND=semantica`) and the new test files +
  `inspect_semantica_*.py` smokes.
- **Contract:** additive only; regenerate any committed JSON-Schema snapshot after adding
  models.
- **Docs:** update `README.md` (capability table + env), `docs/guide.html` (regen via
  `scripts/build_guide.py`), `demo/RUNBOOK.md` (§5 env, §8 troubleshooting), the data-flow
  diagram, and `TODO.md` (mark items done; record any stub found).

## Sequencing & effort

| Phase | Delivers (materialised at ingest) | Depends on | Rough size |
|---|---|---|---|
| 0 Spikes | confirmed semantica surface + Oxigraph-persistence answer | — | 0.5–1 day (on-env) |
| 1 Extraction (semantica LLM mode) | typed entities/relations/events + confidence | 0 | 1–1.5 days |
| 2 Enriched KG in Oxigraph/RocksDB | deduped entities, edges w/ confidence + provenance | 1 | 2–3 days |
| 3 Ontology | generated OWL/SHACL, typed entities | 1–2 | 1.5–2 days |
| 4 Analytics | cached centrality + communities | 2 | 1.5 days |
| 5 Decisions | precedents / impact / rule checks | 2 (4 helps) | 1.5–2 days |
| 6 Bitemporal | valid/record time per fact, `as_of` | 1–2 | 1–1.5 days |

Each phase ships as its own PR behind its env flag; the **default backends are real and
CI-tested**, so value lands even before a semantica class is validated on-env — and if a
spike finds a stub (as with `SPARQLReasoner`), the default ships and the semantica swap is a
later drop-in with no API change.

## Definition of done (every phase)
- [ ] Phase-0 spike output pinned the semantica signatures this phase uses.
- [ ] Default backend fully implemented + covered by a CI test.
- [ ] Optional semantica backend behind its env flag, with an `importorskip` on-env test.
- [ ] Factory falls back to the default (logged warning) when semantica is absent.
- [ ] Graph still persists to Oxigraph/RocksDB (`GRAPH_DB_PATH`); default path runs in CI.
- [ ] `ruff check .` clean; default `pytest -q` green; contract additions backward-compatible.
- [ ] `scripts/validate.sh` exercises the new backend on-env.
- [ ] README / RUNBOOK / TODO updated; no `ContextGraph`/semantica-native shape on the wire.
