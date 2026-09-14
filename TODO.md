# semantic-fabric — deferred work

## Deferred: SPARQL-native inference over the RDF graph (Option 2)

**Status:** deferred by decision. Reasoning over the KG today uses **Option 1** (Datalog
over the graph via `/reason?over_graph=true`), which is built, tested, and sufficient.
This note captures why, and what Option 2 would add if a future need arises.

### Background — how we got here

We standardised the knowledge graph on semantica's own model: **RDF triples queried
with SPARQL** (the persistent `OxigraphGraphStore`). The intent was to also feed that
graph to semantica's reasoners so KG + reasoning + provenance + SHACL share one RDF
substrate. Introspection of the installed `semantica==0.6.8`
(`scripts/inspect_semantica_graph.py`) established two facts:

1. `DatalogReasoner.load_from_graph(graph)` expects a semantica **ContextGraph**, not an
   `rdflib.Graph` (feeding rdflib derived 0 facts). Its working primitives are
   `add_fact` / `add_rule` / `derive_all` / `query`.
2. `SPARQLReasoner` is an **unimplemented stub** in 0.6.8: `execute_query()` raises
   `NotImplementedError` ("no triplet-store execution path exists yet"), and the
   constructor doesn't accept a graph. There is nothing to wire.

So SPARQL over the KG runs through **our own** working engine
(`OxigraphGraphStore.sparql()`), and deterministic reasoning over the KG uses semantica's
`DatalogReasoner` seeded from `RetrievalIndex.graph_facts()` (Option 1, shipped).

### The two reasoning shapes — worked example

Shared setup — extracted into the graph by ingestion:

```
Entities:  Aviva (Org), ISA (Product), CashISA (Product), StocksSharesISA (Product)
Relations: offers(Aviva, ISA), is_a(CashISA, ISA), is_a(StocksSharesISA, ISA)
Pages:     investments/index.md  ──parent──  investments/isas/index.md
```

`RetrievalIndex.graph_facts()` renders this as Datalog atoms:

```
offers(aviva, isa)
is_a(cash_isa, isa)
is_a(stocks_shares_isa, isa)
parent(investments_isas_index_md, investments_index_md)
mentions(investments_isas_index_md, aviva)
```

Business question: **"Which products are ISA-eligible?"** — rule: anything that is a
kind of ISA is ISA-eligible, and eligibility is inherited by sub-types (so `CashISA` and
`StocksSharesISA` qualify, transitively).

#### Option 1 — Datalog over the KG (SHIPPED: `/reason?over_graph=true`)

```jsonc
POST /reason
{
  "over_graph": true,
  "query": "isa_eligible(cash_isa)",
  "rules": [
    {"name": "direct",    "body": ["is_a(X, isa)"],                  "head": "isa_eligible(X)"},
    {"name": "inherited", "body": ["is_a(X, Y)", "isa_eligible(Y)"], "head": "isa_eligible(X)"}
  ]
}
```

Response:

```jsonc
{ "answer": "Yes — isa_eligible(cash_isa) holds.",
  "rule_trace": ["... via 'direct': is_a(cash_isa, isa) ⇒ isa_eligible(cash_isa)"] }
```

- Recursive inference to a fixpoint (Datalog's strength); returns a **yes/no answer + a
  proof trace**.
- The derived fact is **ephemeral** — it exists only in this response. A later SPARQL
  query or search over the graph will NOT see `isa_eligible`.
- Fits **decision-time questions**: "can this customer hold this in an ISA? why?"
- On-env this runs through semantica's `DatalogReasoner`; in CI through the default
  `SimpleForwardChainer`. Same `ReasoningRequest.facts` path either way.

#### Option 2 — SPARQL CONSTRUCT inference (DEFERRED; would need building)

Register a rule as a SPARQL `CONSTRUCT`; running it **writes new triples back into the
RDF graph**:

```sparql
CONSTRUCT { ?x ex:isaEligible true }
WHERE {
  ?x (ex:relObject/^ex:relSubject)* ?isa .   # walk is_a edges transitively
  FILTER(?isa = ex:ISA)
}
```

`infer()` would materialise:

```
ex:ISA              ex:isaEligible true .
ex:CashISA          ex:isaEligible true .
ex:StocksSharesISA  ex:isaEligible true .
```

- Inferences become **persistent RDF triples** in the store: a plain
  `SELECT ?x WHERE { ?x ex:isaEligible true }` returns all three, `rdf_graph()` and any
  downstream consumer/dashboard/export sees them, and they survive restarts.
- Fits **enrich-once, query-by-many**: the graph itself carries derived classifications
  so readers don't re-run logic.
- Weaker at deep recursion than Datalog; **no per-answer explanation trace** (output is
  triples, not a proof).

#### Decision table

| | Option 1 — Datalog (`over_graph`) | Option 2 — SPARQL CONSTRUCT inference |
|---|---|---|
| You ask | "Is CashISA ISA-eligible? Explain." | "Mark all ISA-eligible products in the graph." |
| Output | yes/no **answer + proof trace**, computed now | **new triples written into the graph** |
| Lifetime | ephemeral (per request) | persistent, queryable by everyone |
| Recursion | strong (semi-naive fixpoint) | limited (property paths) |
| Explanation | yes (rule trace) | no |
| Status | **built & validated** | **deferred** (small, self-contained) |

### If/when we build Option 2

Trigger: a consumer needs derived classifications to **persist as queryable graph data**
(search facets, dashboards, other agents) rather than as one-off answers.

Sketch (all in `graph/oxigraph_backend.py`, testable on pyoxigraph — no semantica):
- `add_inference_rule(construct_query: str)` — store a SPARQL CONSTRUCT rule.
- `infer(max_rounds: int = 10)` — run each CONSTRUCT via `store.query(...)`, insert the
  returned triples, repeat to a fixpoint (bounded) so rules can chain; return a count of
  new triples. Guard against unbounded growth.
- Expose over `/reason` (e.g. `materialize: true`) or a dedicated `/graph/infer`.
- Do **not** route through semantica's `SPARQLReasoner` unless a later release implements
  `execute_query` (re-check with `scripts/inspect_semantica_graph.py`).
- Tests: register the ISA-eligibility CONSTRUCT above, `infer()`, then assert a plain
  SPARQL SELECT returns the three eligible products and that the triples persist across a
  fresh store at the same path.

## DONE: persist the retrieval index + KB across restarts

**Status:** shipped. `FABRIC_DB=<path>` enables a SQLite sidecar
(`retrieval/persistence.py`) that write-through persists the retrieval chunks (with
their embedding vectors) and the KB pages. On startup `RetrievalIndex.load_persisted()`
rebuilds the chunk store, re-derives BM25 from the chunk text, and re-upserts vectors
into the in-memory vector store (a self-persisting store like Qdrant keeps its own);
`KBStore.load_persisted()` reloads pages. So `/search`, `/kb` and `--no-ingest` work
immediately after a restart with no re-ingest. In-memory stays the default (no
`FABRIC_DB` → previous behaviour). The knowledge graph persists separately via
`GRAPH_STORE=rdf`. Verified by `tests/test_persistence.py` and an end-to-end
ingest → restart → query check.

**Provenance too:** with `PROVENANCE_BACKEND=semantica`, decision lineage (PROV-O +
chain) persists to a SQLite file — `PROVENANCE_DB`, or a sibling `<FABRIC_DB>.prov.db` —
via semantica's `ProvenanceManager(storage_path=…)`; decision ids are UUIDs so they stay
unique across restarts. `/decisions/{id}/chain` survives a restart. (The dependency-free
in-memory provenance default remains process-scoped, like the in-memory graph/retrieval
defaults.) Opt-in test: `test_semantica_provenance_persists_across_restart`.
