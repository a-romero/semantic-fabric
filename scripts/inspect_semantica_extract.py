#!/usr/bin/env python
"""Phase 1 spike — semantica LLM-mode entity/relation extraction.

Confirms, on an env with semantica installed, everything Phase 1 of
docs/plans/semantica-adoption-plan.md needs to write `extraction/semantica_backend.py`:

  1. the real class names in `semantica.semantic_extract` (the plan guesses
     NamedEntityRecognizer/NERExtractor, RelationExtractor, EventDetector, TripletExtractor);
  2. how to force **LLM mode** (a `method="llm"` arg? a config flag?) and how to pass the
     project's LiteLLM gateway model (reuse EXTRACTION_MODEL / LLM_API_BASE / LLM_API_KEY);
  3. the exact OUTPUT SHAPE — entity fields (does it carry a confidence/score?), relation
     fields, and whether events/triplets are produced — so the adapter can map to
     fabric_client.models.Extraction (+ additive confidence/events/triplets).

READ-ONLY. Prints signatures + a tiny end-to-end run. Paste output into
docs/plans/semantica-spike-findings.md.

    pip install -e ".[semantica,llm]"
    EXTRACTION_MODEL=anthropic/claude-opus-5 python scripts/inspect_semantica_extract.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _spike_common import dump_module, header, probe, require_semantica  # noqa: E402

SENTENCE = (
    "Aviva offers the Enhanced Pension Annuity, a tax-efficient product that provides a "
    "guaranteed income for life. It is regulated by the FCA."
)

MODEL = os.getenv("EXTRACTION_MODEL", "anthropic/claude-opus-5")
API_BASE = os.getenv("LLM_API_BASE") or None
API_KEY = os.getenv("LLM_API_KEY") or None


def _pp(label, obj) -> None:
    """Print an extractor result and, if possible, one element's dict/fields."""
    print(f"{label}: type={type(obj).__name__} repr={repr(obj)[:300]}")
    seq = obj
    if hasattr(obj, "entities") or hasattr(obj, "relations"):
        for attr in ("entities", "relations", "events", "triplets"):
            val = getattr(obj, attr, None)
            if val:
                first = list(val)[0]
                fields = getattr(first, "__dict__", None) or (
                    first if isinstance(first, dict) else str(first))
                print(f"    {attr}[0] fields -> {fields}")
        return
    try:
        first = list(seq)[0]
        print(f"    [0] fields -> {getattr(first, '__dict__', first)}")
    except Exception:  # noqa: BLE001
        pass


def main() -> None:
    require_semantica()

    header("1. semantica.semantic_extract — full public surface")
    mod = dump_module("semantica.semantic_extract")
    if mod is None:
        # Try alternate module names before giving up.
        for alt in ("semantica.extract", "semantica.extraction"):
            mod = dump_module(alt)
            if mod:
                break
    if mod is None:
        print("\n!! could not import an extraction module; check `dir(semantica)`")
        import semantica
        print("semantica public:", [n for n in dir(semantica) if not n.startswith("_")])
        return

    # Resolve whichever entity/relation extractor classes exist.
    def find(*names):
        for n in names:
            if hasattr(mod, n):
                return getattr(mod, n)
        return None

    NER = find("NamedEntityRecognizer", "NERExtractor", "EntityExtractor", "NER")
    REL = find("RelationExtractor", "RelationshipExtractor", "RelExtractor")
    EVT = find("EventDetector", "EventExtractor")
    TRI = find("TripletExtractor", "TripleExtractor")
    print("\nresolved classes:",
          {"NER": NER, "REL": REL, "EVT": EVT, "TRI": TRI})

    header("2. how to construct in LLM mode (try several shapes; report which works)")
    # The plan requires LLM mode via the project's gateway. Try the likely constructor
    # shapes and print which one is accepted; the implementer copies the winner.
    ctor_variants = [
        ("method='llm'", dict(method="llm")),
        ("mode='llm'", dict(mode="llm")),
        ("backend='llm'", dict(backend="llm")),
        ("extraction_method='llm'", dict(extraction_method="llm")),
        ("config={'method':'llm','model':MODEL}", dict(config={"method": "llm", "model": MODEL})),
        ("llm=True, model=MODEL", dict(llm=True, model=MODEL)),
        ("model=MODEL", dict(model=MODEL)),
        ("no-args", {}),
    ]
    for cls, label in ((NER, "NER"), (REL, "REL")):
        if cls is None:
            continue
        print(f"\n[{label}] {cls.__name__} constructor probes:")
        for desc, kwargs in ctor_variants:
            def _try(cls=cls, kwargs=kwargs):
                inst = cls(**kwargs)
                print(f"    OK: {cls.__name__}({desc}) -> {type(inst).__name__}")
            probe(f"{cls.__name__}({desc})", _try)

    header("3. end-to-end extraction on the sample sentence (LLM mode)")
    print(f"model={MODEL} api_base={API_BASE} api_key={'set' if API_KEY else 'unset'}")
    print("sentence:", SENTENCE)

    def run_entities():
        # Build with the first accepted variant that includes an llm hint, else no-args.
        inst = None
        for _desc, kwargs in ctor_variants:
            try:
                inst = NER(**kwargs)
                break
            except Exception:  # noqa: BLE001
                continue
        if inst is None:
            print("could not construct NER")
            return
        for meth in ("extract", "extract_entities", "run", "recognize", "__call__", "predict"):
            fn = getattr(inst, meth, None)
            if fn is None:
                continue
            def _call(fn=fn, meth=meth):
                out = fn(SENTENCE)
                _pp(f"NER.{meth}(text)", out)
            probe(f"NER.{meth}(text)", _call)
    if NER:
        run_entities()

    def run_relations():
        inst = None
        for _desc, kwargs in ctor_variants:
            try:
                inst = REL(**kwargs)
                break
            except Exception:  # noqa: BLE001
                continue
        if inst is None:
            print("could not construct REL")
            return
        for meth in ("extract", "extract_relations", "run", "__call__", "predict"):
            fn = getattr(inst, meth, None)
            if fn is None:
                continue
            def _call(fn=fn, meth=meth):
                out = fn(SENTENCE)
                _pp(f"REL.{meth}(text)", out)
            probe(f"REL.{meth}(text)", _call)
    if REL:
        run_relations()

    header("4. QUESTIONS FOR THE PLAN — answer from the output above")
    print("- exact class names + import path for entity and relation extraction?")
    print("- exact kwarg/flag that selects LLM mode, and how the gateway model is passed?")
    print("- entity output fields (name/type/confidence/span?) and relation fields?")
    print("- are events/triplets produced, and are they worth mapping into Extraction?")


if __name__ == "__main__":
    main()
