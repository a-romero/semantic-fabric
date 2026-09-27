# semantica spike findings (Phase 0)

Fill this in by running the four introspection spikes on an environment where semantica is
installed (`pip install -e ".[semantica,graph,llm]"`) and pasting their output + your
conclusions. Every later phase in `semantica-adoption-plan.md` is implemented against what
this document confirms — not against the guessed class names in the plan.

> Status: **NOT RUN YET.** semantica is not installed in CI; run on-env.

---

## Spike 1 — extraction (`scripts/inspect_semantica_extract.py`) → Phase 1

- Entity extractor class + import path: _TBD_
- Relation extractor class + import path: _TBD_
- Event / triplet extractors present & useful? _TBD_
- **How LLM mode is selected** (exact kwarg/flag) and how the gateway model is passed: _TBD_
- Entity output fields (name / type / **confidence** / span?): _TBD_
- Relation output fields (subject / predicate / object / **confidence**?): _TBD_
- Conclusion for `extraction/semantica_backend.py`: _TBD_

```
<paste script output here>
```

## Spike 2 — KG build & analytics (`scripts/inspect_semantica_kg.py`) → Phases 2 & 4

- **PIVOTAL:** does a builder/store persist LIVE to embedded Oxigraph at a path, or only via
  `RDFExporter`? _TBD_  → decides Phase 2 "live `SemanticaGraphStore`" vs "export bridge".
- GraphBuilder class + constructor for an Oxigraph backend: _TBD_
- Mutation methods that carry **confidence + provenance** onto an edge: _TBD_
- Analytics classes + the graph representation they accept (semantica / rdflib / networkx): _TBD_
- Extra deps required (e.g. networkx)? _TBD_
- Conclusion for `graph/semantica_backend.py` + `graph/analytics.py`: _TBD_

```
<paste script output here>
```

## Spike 3 — decision intelligence (`scripts/inspect_semantica_context.py`) → Phase 5

- Where the decision APIs live (ContextGraph vs decision_* submodules): _TBD_
- `record_decision` / `find_similar_decisions` / `analyze_decision_impact` signatures: _TBD_
- **`check_decision_rules` rules format** (the biggest unknown): _TBD_
- `storage_path` support + overlap with `semantica.provenance` (double-persist?): _TBD_
- Conclusion for `decisions/semantica_backend.py`: _TBD_

```
<paste script output here>
```

## Spike 4 — ontology (`scripts/inspect_semantica_ontology.py`) → Phase 3

- `OntologyGenerator` import path + `generate()` input shape (entities / relations / graph): _TBD_
- Output type (rdflib.Graph / Turtle string / file) → how it's persisted: _TBD_
- Can the generated ontology feed `run_shacl_validation` as the shapes graph? _TBD_
- SKOS support present & needed? _TBD_
- Conclusion for `ontology/generator.py`: _TBD_

```
<paste script output here>
```

---

## Stubs / gaps found

Record any class named in the plan that is **absent or an unimplemented stub** (as
`reasoning.SPARQLReasoner` already is). For each: ship the dependency-free default backend
and the adapter seam anyway, and add a `TODO.md` entry so the semantica swap is a later
drop-in.

- _TBD_
