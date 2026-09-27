#!/usr/bin/env python
"""Phase 3 spike — semantica ontology generation & governance (semantica.ontology).

Confirms what Phase 3 of docs/plans/semantica-adoption-plan.md needs to write
`ontology/generator.py`:

  1. the real classes/functions in `semantica.ontology` (the repo already uses
     `run_shacl_validation`; the plan adds OntologyGenerator / OntologyValidator);
  2. can it **generate** an OWL/SHACL ontology from a set of typed entities/relations, and
     what input shape does it take;
  3. SKOS vocabulary support;
  4. the output shape (an rdflib.Graph? a Turtle string? a file?) so it can be persisted
     alongside the Oxigraph graph and fed back into /validate and reasoning.

READ-ONLY except a throwaway temp dir. Paste output into
docs/plans/semantica-spike-findings.md.

    pip install -e ".[semantica,graph]"
    python scripts/inspect_semantica_ontology.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _spike_common import dump_module, header, probe, require_semantica, sig  # noqa: E402

# A tiny typed sample mirroring what Phase 1 extraction yields (entities with a type,
# relations subject/predicate/object). The generator should turn this into OWL/SHACL.
SAMPLE_ENTITIES = [
    {"name": "Aviva", "type": "Organization"},
    {"name": "Enhanced Pension Annuity", "type": "Product"},
    {"name": "FCA", "type": "Regulator"},
]
SAMPLE_RELATIONS = [
    {"subject": "Aviva", "predicate": "offers", "object": "Enhanced Pension Annuity"},
    {"subject": "Enhanced Pension Annuity", "predicate": "regulated_by", "object": "FCA"},
]


def main() -> None:
    require_semantica()
    tmp = Path(tempfile.mkdtemp(prefix="semantica-onto-spike-"))
    print("temp dir:", tmp)

    header("1. semantica.ontology — full public surface")
    onto = dump_module("semantica.ontology")

    def find(*names):
        return next((getattr(onto, n) for n in names if onto and hasattr(onto, n)), None)

    Gen = find("OntologyGenerator", "OWLGenerator", "OntologyBuilder")
    Val = find("OntologyValidator", "ShaclValidator", "Validator")
    run_shacl = find("run_shacl_validation")
    print("\nresolved:", {"OntologyGenerator": Gen, "OntologyValidator": Val,
                          "run_shacl_validation": bool(run_shacl)})

    header("2. OntologyGenerator — signature + generate from typed entities")
    if Gen:
        print(f"{Gen.__name__}{sig(getattr(Gen, '__init__', Gen))}")
        for meth in ("generate", "generate_ontology", "build", "from_entities",
                     "from_graph", "infer", "run"):
            fn = getattr(Gen, meth, None)
            if fn:
                print(f"  - {meth}{sig(fn)}")

        def gen_probe():
            inst = None
            for kwargs in (dict(), dict(config={}), dict(namespace="http://semantic-fabric/ex#")):
                try:
                    inst = Gen(**kwargs)
                    print(f"constructed OntologyGenerator({list(kwargs)})")
                    break
                except Exception as e:  # noqa: BLE001
                    print(f"  x OntologyGenerator({list(kwargs)}) -> {type(e).__name__}: {e}")
            if inst is None:
                return
            gen = next((getattr(inst, m) for m in
                        ("generate", "generate_ontology", "build", "from_entities", "run")
                        if hasattr(inst, m)), None)
            if gen is None:
                print("no generate-like method found")
                return
            print("generate method:", sig(gen))
            # Try several input shapes and report which is accepted + the output shape.
            for desc, args in (
                ("entities=..., relations=...",
                 dict(entities=SAMPLE_ENTITIES, relations=SAMPLE_RELATIONS)),
                ("(entities, relations)", (SAMPLE_ENTITIES, SAMPLE_RELATIONS)),
                ("(entities)", (SAMPLE_ENTITIES,)),
            ):
                def _try(args=args, desc=desc):
                    out = gen(**args) if isinstance(args, dict) else gen(*args)
                    print(f"    OK generate({desc}) -> type={type(out).__name__} "
                          f"repr={repr(out)[:300]}")
                probe(f"generate({desc})", _try)
        probe("generate ontology from sample", gen_probe)
    else:
        print("no OntologyGenerator-like class; see section 1")

    header("3. OntologyValidator / run_shacl_validation — signature")
    if Val:
        print(f"{Val.__name__}{sig(getattr(Val, '__init__', Val))}")
    if run_shacl:
        print(f"run_shacl_validation{sig(run_shacl)}")
        print("  (repo already uses this in ontology/shacl_backend.py: "
              "run_shacl_validation(data_ttl, shapes_ttl) -> report)")

    header("4. SKOS vocabulary support")
    for m in ("semantica.ontology.skos", "semantica.ontology.vocabulary"):
        dump_module(m)
    for n in (dir(onto) if onto else []):
        if "skos" in n.lower() or "vocab" in n.lower():
            print("SKOS-related name:", n, "->", getattr(onto, n))

    header("5. QUESTIONS FOR THE PLAN")
    print("- OntologyGenerator import path + generate() input shape (entities/relations/graph)?")
    print("- output: rdflib.Graph / Turtle string / file? (drives how it's persisted)")
    print("- can the generated ontology be fed to run_shacl_validation as the shapes graph?")
    print("- SKOS support available and needed for typed vocabularies?")
    print(f"\n(You can delete the temp dir: {tmp})")


if __name__ == "__main__":
    main()
