"""Shared helpers for the semantica introspection spikes (scripts/inspect_semantica_*.py).

These scripts are READ-ONLY probes. They print the real API surface and run tiny probes so
the adoption plan (docs/plans/semantica-adoption-plan.md) is implemented against confirmed
signatures rather than guesses. Run on an env where semantica is installed:

    pip install -e ".[semantica,graph,llm]"
    python scripts/inspect_semantica_extract.py     # (etc.)

Paste each script's output into docs/plans/semantica-spike-findings.md.
"""

from __future__ import annotations

import importlib
import inspect
import traceback


def sig(obj) -> str:
    try:
        return str(inspect.signature(obj))
    except (TypeError, ValueError):
        return "(<no signature>)"


def firstdoc(obj) -> str:
    doc = (inspect.getdoc(obj) or "").strip()
    return doc.splitlines()[0][:160] if doc else ""


def dump_class(cls, methods: int = 40) -> None:
    """Print a class: its __init__ signature and public methods with signatures/docs."""
    print(f"\n  class {cls.__name__}{sig(getattr(cls, '__init__', cls))}")
    d = firstdoc(cls)
    if d:
        print(f"      · {d}")
    shown = 0
    for name, member in inspect.getmembers(cls, predicate=callable):
        if name.startswith("_"):
            continue
        print(f"    - {name}{sig(member)}")
        md = firstdoc(member)
        if md:
            print(f"        {md}")
        shown += 1
        if shown >= methods:
            print("    … (more methods elided)")
            break


def dump_module(modname: str):
    """Import a module and print every public class/function with signatures. Returns it."""
    try:
        mod = importlib.import_module(modname)
    except Exception as exc:  # noqa: BLE001 - spike: report, don't fail
        print(f"\n### {modname}: IMPORT FAILED: {exc}")
        return None
    print(f"\n### {modname}")
    public = [n for n in dir(mod) if not n.startswith("_")]
    print("public names:", public)
    for name in public:
        obj = getattr(mod, name)
        if inspect.isclass(obj):
            dump_class(obj)
        elif inspect.isfunction(obj):
            print(f"\n  def {name}{sig(obj)}")
            fd = firstdoc(obj)
            if fd:
                print(f"      · {fd}")
    return mod


def probe(label: str, fn) -> None:
    """Run a probe closure; print its result or a short traceback. Never raises."""
    print(f"\n--- probe: {label} ---")
    try:
        fn()
    except Exception:  # noqa: BLE001 - spike: capture and print
        print("EXC:")
        traceback.print_exc(limit=4)


def header(title: str) -> None:
    print("\n" + "=" * 78)
    print(f"## {title}")
    print("=" * 78)


def require_semantica() -> None:
    try:
        import semantica  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            f"semantica not importable ({exc}). Install with: "
            'pip install -e ".[semantica,graph,llm]"'
        )
    print("semantica version:", getattr(__import__("semantica"), "__version__", "?"))
