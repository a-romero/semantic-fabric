"""semantica-backed reasoning engine (optional; requires the .[semantica] extra).

Uses semantica's ``DatalogReasoner`` (recursive Datalog fixpoint with real
explanations). Written to the real ``0.6.8`` API (``add_fact`` / ``add_rule`` /
``derive_all`` / ``query``); CI here runs the dependency-free SimpleForwardChainer.

Our request format uses plain string atoms (e.g. ``Insurable(motor_policy)``) with a
Horn ``Rule(name, body, head)``. We translate those into Datalog: predicates are
lower-cased (Datalog reserves leading-uppercase tokens for variables), each rule
becomes ``head :- b1, b2.`` and facts are asserted verbatim.
"""

from __future__ import annotations

from fabric_client.models import ReasonResponse

from .engine import ReasoningRequest


class SemanticaReasoningEngine:
    def __init__(self) -> None:
        # Import eagerly so a missing extra fails fast at construction time.
        from semantica.reasoning import DatalogReasoner  # type: ignore

        self._Reasoner = DatalogReasoner

    @staticmethod
    def _atom(s: str) -> str:
        """Normalize an atom to Datalog form: lower-case the predicate name."""
        s = s.strip()
        if "(" in s:
            pred, rest = s.split("(", 1)
            return f"{pred.strip().lower()}({rest.strip()}"
        return s.lower()

    @staticmethod
    def _canon(s: str) -> str:
        """Whitespace/case-insensitive canonical form for comparing derived atoms."""
        return "".join(s.split()).rstrip(".").lower()

    def reason(self, req: ReasoningRequest) -> ReasonResponse:
        # Fresh reasoner per request — no state bleed across calls.
        reasoner = self._Reasoner()

        facts = [self._atom(f) for f in req.facts]
        for fact in facts:
            reasoner.add_fact(fact)

        rule_strs: list[str] = []
        for rule in req.rules:
            body = ", ".join(self._atom(b) for b in rule.body)
            head = self._atom(rule.head)
            rule_str = f"{head} :- {body}."
            reasoner.add_rule(rule_str)
            rule_strs.append(rule_str)

        derived = list(reasoner.derive_all())  # -> list[str]

        query = self._atom(req.query) if req.query else ""
        holds = False
        if query:
            known = {self._canon(x) for x in derived} | {self._canon(f) for f in facts}
            holds = self._canon(query) in known
            if not holds:
                # Fall back to the pattern-query API in case derive_all elides bases.
                try:
                    holds = bool(reasoner.query(query))
                except Exception:
                    pass

        trace: list[str] = [
            f"rule '{rule.name}': {rs}" for rule, rs in zip(req.rules, rule_strs)
        ]
        if derived:
            trace.append("derived: " + ", ".join(sorted(set(derived))))

        if query:
            answer = (
                f"Yes — {req.query} holds." if holds
                else f"No — {req.query} could not be derived from the given facts and rules."
            )
        else:
            answer = "Derived: " + (", ".join(sorted(set(derived))) or "(nothing new)")
        return ReasonResponse(answer=answer, rule_trace=trace)
