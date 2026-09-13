"""semantica-backed provenance store (optional; requires the .[semantica] extra).

Emits standards-correct W3C PROV-O via semantica's ProvenanceManager and verifies the
tamper-evident chain with its verify_chain. Written to the API confirmed by the
evaluation spike; MUST be validated on an environment where semantica is installed
(CI here runs the in-memory store, which is the tested default).

Spike-confirmed guardrails baked in:
- link derivations with ``parent_entity_id`` (NOT ``derived_from_id`` — the latter is
  silently not serialized to ``prov:wasDerivedFrom``).
"""

from __future__ import annotations

from typing import Any

from fabric_client.models import Decision


class SemanticaProvenanceStore:
    def __init__(self) -> None:
        # Import lazily so the module only hard-requires semantica when actually used.
        from semantica.provenance import ProvenanceManager  # type: ignore

        self._pm = ProvenanceManager()
        self._decision_seq = 0

    def record_entity(
        self, entity_id: str, kind: str, derived_from: list[str] | None = None,
        attrs: dict[str, Any] | None = None,
    ) -> str:
        # parent_entity_id drives prov:wasDerivedFrom (see guardrail above).
        for parent in derived_from or []:
            self._pm.record_entity(entity_id=entity_id, parent_entity_id=parent,
                                   attributes=attrs or {})
        if not derived_from:
            self._pm.record_entity(entity_id=entity_id, attributes=attrs or {})
        return entity_id

    def record_decision(self, decision: Decision) -> dict:
        self._decision_seq += 1
        decision_id = f"decision-{self._decision_seq}"
        for ev in decision.evidence:
            self._pm.record_entity(
                entity_id=decision_id, parent_entity_id=ev,
                attributes={"scenario": decision.scenario, "outcome": decision.outcome},
            )
        return {"decision_id": decision_id, "recorded": True, "backend": "semantica"}

    def trace_chain(self, decision_id: str) -> dict:
        # export_prov() returns PROV-O (Turtle); callers can SPARQL wasDerivedFrom+.
        prov_o = self._pm.export_prov()
        return {
            "decision_id": decision_id,
            "found": True,
            "verified": bool(self._pm.verify_chain()),
            "prov_o": prov_o,
            "backend": "semantica",
        }

    def verify_chain(self) -> bool:
        return bool(self._pm.verify_chain())
