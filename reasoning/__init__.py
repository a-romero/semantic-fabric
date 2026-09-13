"""Deterministic reasoning (Phase 3): explainable inference.

Backs api.main.reason(). A dependency-free forward chainer is the default; the
optional semantica backend adds Datalog/forward-chaining. Every result carries a
rule trace. SHACL policy guardrails (validation before answers leave the plane) are
the next Phase 3 step. Public surface:

    build_reasoning_engine(kind) -> ReasoningEngine
    ReasoningEngine.reason(ReasoningRequest) -> ReasonResponse
"""

from .engine import (
    ReasoningEngine,
    ReasoningRequest,
    Rule,
    SimpleForwardChainer,
    build_reasoning_engine,
)

__all__ = [
    "ReasoningEngine",
    "ReasoningRequest",
    "Rule",
    "SimpleForwardChainer",
    "build_reasoning_engine",
]
