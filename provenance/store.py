"""Provenance + decision store (Phase 3).

Records decisions and the entities they derive from, and traces transitive lineage —
answering "why did the agent conclude this, and from what?". Two backends behind one
protocol (same pattern as retrieval/graph):

- ``InMemoryProvenanceStore`` — dependency-free default: a derivation graph plus a
  tamper-evident hash chain over the append log. Real and fully tested; used by CI.
- ``SemanticaProvenanceStore`` — optional (``.[semantica]`` extra): emits
  standards-correct W3C PROV-O via semantica's ProvenanceManager and uses its
  ``verify_chain``. Per the evaluation spike it links with ``parent_entity_id``
  (NOT ``derived_from_id``, which is silently not serialized).

Selected by ``PROVENANCE_BACKEND`` (``memory`` default, ``semantica`` in deployment).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from fabric_client.models import Decision


@dataclass
class ProvRecord:
    """One node in the derivation graph (a decision, an evidence unit, a source)."""

    id: str
    kind: str  # "decision" | "evidence" | "source"
    derived_from: list[str] = field(default_factory=list)
    attrs: dict[str, Any] = field(default_factory=dict)
    checksum: str = ""
    previous_checksum: str = ""


class ProvenanceStore(Protocol):
    def record_entity(
        self, entity_id: str, kind: str, derived_from: list[str] | None = None,
        attrs: dict[str, Any] | None = None,
    ) -> str: ...

    def record_decision(self, decision: Decision) -> dict: ...

    def trace_chain(self, decision_id: str) -> dict: ...

    def verify_chain(self) -> bool: ...


def _checksum(previous: str, payload: dict) -> str:
    body = previous + json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(body.encode()).hexdigest()


class InMemoryProvenanceStore:
    """Derivation graph + tamper-evident hash chain. Dependency-free."""

    def __init__(self) -> None:
        self._records: dict[str, ProvRecord] = {}
        self._log: list[str] = []          # append order of record ids
        self._last_checksum: str = ""
        self._decision_seq = 0

    # -- writes -----------------------------------------------------------
    def record_entity(
        self, entity_id: str, kind: str, derived_from: list[str] | None = None,
        attrs: dict[str, Any] | None = None,
    ) -> str:
        derived_from = derived_from or []
        attrs = attrs or {}
        payload = {"id": entity_id, "kind": kind, "derived_from": derived_from, "attrs": attrs}
        checksum = _checksum(self._last_checksum, payload)
        self._records[entity_id] = ProvRecord(
            id=entity_id, kind=kind, derived_from=list(derived_from), attrs=attrs,
            checksum=checksum, previous_checksum=self._last_checksum,
        )
        self._log.append(entity_id)
        self._last_checksum = checksum
        return entity_id

    def record_decision(self, decision: Decision) -> dict:
        self._decision_seq += 1
        decision_id = f"decision-{self._decision_seq}"
        # A decision was derived from the evidence units it cited.
        self.record_entity(
            decision_id,
            kind="decision",
            derived_from=list(decision.evidence),
            attrs={
                "scenario": decision.scenario,
                "outcome": decision.outcome,
                "reasoning": decision.reasoning,
                "valid_time": decision.valid_time,
                "recorded_time": decision.recorded_time,
            },
        )
        rec = self._records[decision_id]
        return {
            "decision_id": decision_id,
            "recorded": True,
            "checksum": rec.checksum,
            "derived_from": rec.derived_from,
        }

    # -- reads ------------------------------------------------------------
    def trace_chain(self, decision_id: str) -> dict:
        """Transitive `wasDerivedFrom` closure from a decision, breadth-first."""
        root = self._records.get(decision_id)
        if root is None:
            return {"decision_id": decision_id, "found": False, "chain": []}
        chain: list[dict] = []
        seen: set[str] = set()
        frontier = [(decision_id, 0)]
        while frontier:
            node_id, depth = frontier.pop(0)
            if node_id in seen:
                continue
            seen.add(node_id)
            rec = self._records.get(node_id)
            if rec is None:
                # referenced but never registered (e.g. an evidence id we didn't record)
                chain.append({"id": node_id, "kind": "unregistered", "distance": depth,
                              "derived_from": []})
                continue
            chain.append({
                "id": rec.id, "kind": rec.kind, "distance": depth,
                "source_id": rec.attrs.get("source_id"),
                "derived_from": rec.derived_from,
            })
            for parent in rec.derived_from:
                frontier.append((parent, depth + 1))
        return {
            "decision_id": decision_id,
            "found": True,
            "verified": self.verify_chain(),
            "chain": chain,
        }

    def verify_chain(self) -> bool:
        previous = ""
        for rid in self._log:
            rec = self._records[rid]
            payload = {"id": rec.id, "kind": rec.kind, "derived_from": rec.derived_from,
                       "attrs": rec.attrs}
            if rec.previous_checksum != previous or rec.checksum != _checksum(previous, payload):
                return False
            previous = rec.checksum
        return True


def build_provenance_store(kind: str | None) -> ProvenanceStore:
    """Factory from PROVENANCE_BACKEND. Falls back to in-memory if semantica is absent.

    When the semantica backend is selected, decision lineage persists across restarts to
    a SQLite file: ``PROVENANCE_DB`` if set, else derived from ``FABRIC_DB`` (a sibling
    ``.prov.db``). Without either it runs in-process (the CI/default behaviour).
    """
    import os

    choice = (kind or "memory").strip().lower()
    if choice == "semantica":
        try:
            from .semantica_backend import SemanticaProvenanceStore

            db = os.getenv("PROVENANCE_DB")
            if not db and os.getenv("FABRIC_DB"):
                from pathlib import Path
                db = str(Path(os.getenv("FABRIC_DB")).with_suffix(".prov.db"))
            return SemanticaProvenanceStore(storage_path=db)
        except Exception:  # not installed / import failure -> safe fallback
            return InMemoryProvenanceStore()
    return InMemoryProvenanceStore()
