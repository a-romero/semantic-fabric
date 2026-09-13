"""Reasoning engine (Phase 3): deterministic, explainable inference.

Two backends behind one protocol (same pattern as retrieval/graph/provenance):

- ``SimpleForwardChainer`` — dependency-free default: naive forward chaining to a
  fixpoint over Horn-style rules, with a real natural-language explanation per derived
  fact. Enough to exercise and test the /reason contract without semantica.
- ``SemanticaReasoningEngine`` — optional (``.[semantica]`` extra): semantica's
  recursive Datalog fixpoint + forward-chaining with NL explanations (spike-confirmed:
  each InferenceResult carries rule + premises + confidence).

A "query" asks whether/what can be derived given a fact base + rules. Phase 3 keeps
the rule/fact format simple and explicit; ontology-driven rulesets come with SHACL.
Selected by ``REASONING_BACKEND`` and gated by ``ENABLE_REASONING``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from fabric_client.models import ReasonResponse


@dataclass
class Rule:
    """A Horn rule: all `body` atoms present -> derive `head`. Atoms are plain strings."""

    name: str
    body: list[str]
    head: str


@dataclass
class ReasoningRequest:
    query: str                       # the atom to prove/derive, e.g. "Insurable(motor_policy)"
    facts: list[str] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)


class ReasoningEngine(Protocol):
    def reason(self, req: ReasoningRequest) -> ReasonResponse: ...


class SimpleForwardChainer:
    """Naive forward chaining to a fixpoint. Deterministic and explainable."""

    def reason(self, req: ReasoningRequest) -> ReasonResponse:
        known: set[str] = set(req.facts)
        trace: list[str] = []
        changed = True
        while changed:
            changed = False
            for rule in req.rules:
                if rule.head in known:
                    continue
                if all(atom in known for atom in rule.body):
                    known.add(rule.head)
                    premises = ", ".join(rule.body) or "(no premises)"
                    trace.append(
                        f"Given {premises}, we conclude {rule.head} using rule '{rule.name}'."
                    )
                    changed = True

        derivable = req.query in known
        if derivable:
            answer = f"Yes — {req.query} holds."
        elif req.query:
            answer = f"No — {req.query} could not be derived from the given facts and rules."
        else:
            # No specific query: report everything newly derived.
            answer = "Derived: " + (", ".join(sorted(known - set(req.facts))) or "(nothing new)")
        return ReasonResponse(answer=answer, rule_trace=trace)


def build_reasoning_engine(kind: str | None) -> ReasoningEngine:
    """Factory from REASONING_BACKEND. Falls back to the simple engine if semantica absent."""
    choice = (kind or "simple").strip().lower()
    if choice == "semantica":
        try:
            from .semantica_backend import SemanticaReasoningEngine

            return SemanticaReasoningEngine()
        except Exception:
            return SimpleForwardChainer()
    return SimpleForwardChainer()
