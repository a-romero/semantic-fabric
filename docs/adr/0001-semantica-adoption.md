# ADR 0001 — Adopt semantica partially, behind our interfaces

**Status:** Accepted
**Date:** 2026-09-13
**Deciders:** project owner + design session
**Context source:** evaluation spike run against 6 real Aviva insurance/pension PDFs
(spaCy NER, localhost Qdrant, pyshacl, rdflib, pyoxigraph). Full findings in the
spike report.

## Context

semantic-fabric (Phases 0–2) implements retrieval (hybrid vector+BM25 via
Qdrant/BGE-M3), a basic page graph, dense-PDF ingestion, and the `generated/` KB
namespace — all with our own code. semantica had not been used. Before building the
high-value layers (provenance, reasoning, ontology, bi-temporal), we ran a time-boxed
spike to decide: adopt semantica for those layers, or build over standard libraries.

## Decision

**Adopt semantica partially — for the layers whose DIY cost is highest and which the
spike proved genuinely work — behind our own interfaces. Keep our retrieval and
extraction. Do not wholesale-replace what we have.**

Adopt from semantica:
- **Provenance** — `ProvenanceManager.export_prov()` produces standards-correct W3C
  PROV-O (qualified derivation/association/generation), loads into rdflib, and SPARQL
  `wasDerivedFrom+` returns full transitive lineage. Bonus: hash-chained,
  tamper-evident audit trail (`verify_chain`).
- **Ontology / SHACL** — `run_shacl_validation` (pyshacl) enforces real constraints
  with correct paths + messages; OWL generation is usable (relationship→OWL mapping
  is shallow — we supplement `subclass_of` → `rdfs:subClassOf`).
- **Reasoning** — recursive Datalog fixpoint + forward-chaining with real NL
  explanations; each `InferenceResult` carries rule + premises + confidence. SPARQL
  reasoner present.
- **Bi-temporal** — `BiTemporalFact` (valid + recorded axes) with `query_at_time`.

Keep ours (do **not** adopt semantica's equivalents):
- **Retrieval** — hybrid vector+BM25+BGE-M3+RRF is stronger than semantica's Qdrant
  wrapper; stays behind `RetrievalBackend`.
- **Extraction** — semantica's offline default emits only generic `related_to`
  co-occurrence edges and noisy spans; typed extraction needs an LLM backend we own.
  Keep extraction quality as our problem (ontology-guided / LLM-with-validation).
- **Dense-PDF ingestion robustness** — table/chart extraction, OCR, provenance
  locators remain ours.

## Guardrails (from spike findings)

1. **Pin a release** (spike used v0.6.8, 2026-09-05) — 0.x churn + maintainer
   concentration (bus-factor) make version drift a real risk.
2. **Wrap behind new interfaces** — `ProvenanceStore`, `ReasoningEngine`,
   `OntologyValidator` — never call `semantica.*` directly from API routes. This
   isolates the sharp edges and keeps semantica swappable, like the retrieval seam.
3. **Vendor small patches / avoid known-broken paths:** use `parent_entity_id` (not
   `derived_from_id`) for PROV `wasDerivedFrom`; use `valid_until` (not the
   cookbook's `valid_to`, silently ignored); we don't use their Qdrant/PDF happy
   paths, so those bugs don't reach us.
4. **Keep it optional in the base install** — semantica goes in a `.[semantica]`
   extra and behind config flags, so CI and the dependency-free defaults are
   unaffected (same pattern as Qdrant/BGE-M3).

## Consequences

- The enterprise differentiators (auditor-defensible PROV-O lineage, SHACL policy
  gates, explainable reasoning, point-in-time queries) become real instead of
  lookalike — saving months of specialist work.
- We take on a pinned dependency with known rough edges; mitigated by interfaces +
  vendored patches + the option to swap to standard libs (rdflib/pyshacl/oxigraph)
  behind the same interfaces if semantica stalls.
- Extraction quality and retrieval remain our engineering responsibility either way.

## Alternatives considered

- **DIY over standard libraries** (rdflib/pyshacl/oxigraph/a Datalog lib): viable
  fallback; more integration work than semantica for the same standards, but no
  framework-survival risk. Chosen as the swap-out path, not the default.
- **Pure from-scratch** engines: rejected — specialist, months of work, no upside.
