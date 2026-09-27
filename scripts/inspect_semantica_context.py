#!/usr/bin/env python
"""Phase 5 spike — semantica decision intelligence (semantica.context).

Confirms what Phase 5 of docs/plans/semantica-adoption-plan.md needs to write
`decisions/semantica_backend.py`:

  1. where the decision APIs live (ContextGraph methods, or dedicated modules
     decision_recorder / decision_query / policy_engine / causal_analyzer);
  2. signatures for record_decision, find_similar_decisions, analyze_decision_impact, and —
     the biggest unknown — **the rules format check_decision_rules expects**;
  3. whether context has its own persistence (storage_path) and whether it overlaps
     semantica.provenance (so decisions are not double-persisted confusingly).

READ-ONLY except a throwaway in-memory/temp graph. Paste output into
docs/plans/semantica-spike-findings.md.

    pip install -e ".[semantica]"
    python scripts/inspect_semantica_context.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _spike_common import dump_module, header, probe, require_semantica, sig  # noqa: E402


def main() -> None:
    require_semantica()
    tmp = Path(tempfile.mkdtemp(prefix="semantica-ctx-spike-"))

    header("1. semantica.context — full public surface")
    ctx = dump_module("semantica.context")

    header("2. decision-focused submodules")
    for m in ("semantica.context.decision_recorder", "semantica.context.decision_query",
              "semantica.context.decision_methods", "semantica.context.decision_models",
              "semantica.context.decision_context", "semantica.context.policy_engine",
              "semantica.context.causal_analyzer", "semantica.context.agent_context",
              "semantica.context.agent_memory"):
        dump_module(m)

    header("3. locate the decision-intelligence callables")

    def find(mod, *names):
        return next((getattr(mod, n) for n in names if mod and hasattr(mod, n)), None)

    CG = find(ctx, "ContextGraph", "AgentContext", "AgentMemory")
    print("primary class:", CG)
    if CG:
        wanted = ("record_decision", "find_similar_decisions", "analyze_decision_impact",
                  "check_decision_rules", "trace_decision_chain", "get_decision",
                  "find_precedents")
        for name in wanted:
            fn = getattr(CG, name, None)
            print(f"  {name}: {sig(fn) if fn else 'NOT on ' + CG.__name__}")

    header("4. construct + tiny end-to-end (record two decisions, find similar, check rules)")

    def e2e():
        if CG is None:
            print("no ContextGraph/AgentContext class found; see sections 1-2")
            return
        # Try to construct with and without a storage_path.
        inst = None
        for desc, kwargs in (("storage_path=tmp", dict(storage_path=str(tmp / "ctx"))),
                             ("no-args", {}),
                             ("config={}", dict(config={}))):
            try:
                inst = CG(**kwargs)
                print(f"constructed {CG.__name__}({desc})")
                break
            except Exception as e:  # noqa: BLE001
                print(f"  x {CG.__name__}({desc}) -> {type(e).__name__}: {e}")
        if inst is None:
            return

        rec = getattr(inst, "record_decision", None)
        if rec:
            print("record_decision signature:", sig(rec))
            for kwargs in (
                dict(scenario="Can I open a cash ISA?", outcome="Yes",
                     evidence=["investments/isas/index.md"]),
                dict(decision="Can I open a cash ISA?", outcome="Yes"),
            ):
                def _rec(kwargs=kwargs):
                    out = rec(**kwargs)
                    print(f"    record_decision({list(kwargs)}) -> {repr(out)[:200]}")
                probe(f"record_decision({list(kwargs)})", _rec)

        sim = getattr(inst, "find_similar_decisions", None)
        if sim:
            print("find_similar_decisions signature:", sig(sim))
            probe("find_similar_decisions('open an ISA')",
                  lambda: print(sim("open an ISA")))

        chk = getattr(inst, "check_decision_rules", None)
        if chk:
            print("check_decision_rules signature:", sig(chk))
            print("    -> the signature above reveals the rules format; the plan needs it.")
            # Best-effort call with a plausible rule shape (the probe wrapper catches errors,
            # and the error message itself usually reveals the expected format).
            probe("check_decision_rules([{'require_evidence': True}])",
                  lambda: print(chk([{"require_evidence": True}])))

        imp = getattr(inst, "analyze_decision_impact", None)
        if imp:
            print("analyze_decision_impact signature:", sig(imp))
    probe("decision e2e", e2e)

    header("5. persistence + overlap with semantica.provenance")
    print("temp dir contents after e2e (did context write files? which?):")
    for p in sorted(tmp.rglob("*")):
        print("   ", p.relative_to(tmp))
    dump_module("semantica.provenance")
    print("\nQ: does context.record_decision also write PROV-O, or is provenance separate?")

    header("6. QUESTIONS FOR THE PLAN")
    print("- import path + class for decision recording/query (ContextGraph vs submodule)?")
    print("- signatures for record_decision / find_similar_decisions / analyze_decision_impact?")
    print("- exact rules format for check_decision_rules?")
    print("- storage_path support + relationship to semantica.provenance persistence?")
    print(f"\n(You can delete the temp dir: {tmp})")


if __name__ == "__main__":
    main()
