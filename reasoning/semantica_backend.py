"""semantica-backed reasoning engine (optional; requires the .[semantica] extra).

Uses semantica's forward-chaining / Datalog reasoner, which the evaluation spike
confirmed produces correct fixpoints and real NL explanations (each InferenceResult
carries rule + premises + confidence). Written to the spike-confirmed API; MUST be
validated on an environment where semantica is installed — CI here runs the
dependency-free SimpleForwardChainer.
"""

from __future__ import annotations

from fabric_client.models import ReasonResponse

from .engine import ReasoningRequest


class SemanticaReasoningEngine:
    def __init__(self) -> None:
        from semantica.reasoning import ForwardChainer  # type: ignore

        self._chainer = ForwardChainer()

    def reason(self, req: ReasoningRequest) -> ReasonResponse:
        # Load facts + rules, run to fixpoint, collect explained inferences.
        for fact in req.facts:
            self._chainer.add_fact(fact)
        for rule in req.rules:
            self._chainer.add_rule(name=rule.name, body=rule.body, head=rule.head)

        results = self._chainer.run()  # -> list[InferenceResult]
        trace = [getattr(r, "explanation", str(r)) for r in results]
        derived = {getattr(r, "conclusion", getattr(r, "head", "")) for r in results}

        if req.query:
            holds = req.query in derived or req.query in set(req.facts)
            answer = f"Yes — {req.query} holds." if holds else (
                f"No — {req.query} could not be derived."
            )
        else:
            answer = "Derived: " + (", ".join(sorted(d for d in derived if d)) or "(nothing new)")
        return ReasonResponse(answer=answer, rule_trace=trace)
