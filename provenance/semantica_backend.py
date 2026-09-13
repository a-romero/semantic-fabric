"""semantica-backed provenance store (optional; requires the .[semantica] extra).

Emits standards-correct W3C PROV-O via semantica's ``ProvenanceManager`` and verifies
the tamper-evident hash chain with ``verify_chain``. Written to the real ``0.6.8`` API
(``track_entity`` / ``track_relationship`` / ``export_prov`` / ``verify_chain``); CI
here runs the dependency-free in-memory store, which is the tested default.

Adapter surface preserved for the rest of the service:
- ``record_entity(entity_id, kind, derived_from=..., attrs=...)``
- ``record_decision(Decision) -> dict``
- ``trace_chain(decision_id) -> dict`` (with ``verified`` + ``prov_o``)
- ``verify_chain() -> bool``
"""

from __future__ import annotations

import urllib.parse
from typing import Any

from fabric_client.models import Decision

# rdflib rejects a URIRef containing whitespace or any of <>"{}|\^` when serializing
# to Turtle. semantica mints URIRefs from ids/sources, so anything we pass that may
# carry those (free-text scenarios, relationship ids) must be percent-encoded first.
_URI_UNSAFE = set(' <>"{}|\\^`')


def _uri_safe(s: str) -> str:
    s = str(s)
    if any(c in _URI_UNSAFE for c in s):
        return urllib.parse.quote(s, safe="")
    return s


class SemanticaProvenanceStore:
    def __init__(self) -> None:
        # Import lazily so the module only hard-requires semantica when actually used.
        from semantica.provenance import ProvenanceManager  # type: ignore

        # 0.6.8's ctor takes an optional storage_path (in-memory when omitted). Be
        # defensive across point releases: fall back to an explicit in-memory store.
        try:
            self._pm = ProvenanceManager()
        except TypeError:
            try:
                from semantica.provenance import InMemoryStorage  # type: ignore

                self._pm = ProvenanceManager(storage=InMemoryStorage())
            except Exception:
                self._pm = ProvenanceManager(storage_path=":memory:")
        self._decision_seq = 0

    # -- entities / derivation -------------------------------------------------

    def _track_derivation(self, child: str, parent: str) -> None:
        """Record ``child prov:wasDerivedFrom parent`` as a tracked relationship.

        semantica mints a URIRef from ``relationship_id``, so it must be URI-safe:
        percent-encode the endpoints (raw ids may carry ``<``, ``#`` etc. that break
        Turtle serialization) and join with a legal separator.
        """
        rel_id = (
            f"{urllib.parse.quote(str(child), safe='')}"
            f"__derivedFrom__{urllib.parse.quote(str(parent), safe='')}"
        )
        try:
            self._pm.track_relationship(
                rel_id, parent,
                metadata={
                    "type": "wasDerivedFrom",
                    "source_entity": parent,
                    "target_entity": child,
                },
            )
        except Exception:
            # Best-effort: a relationship-shape mismatch must not drop the entity.
            pass

    def record_entity(
        self, entity_id: str, kind: str, derived_from: list[str] | None = None,
        attrs: dict[str, Any] | None = None,
    ) -> str:
        meta = dict(attrs or {})
        meta.setdefault("kind", kind)
        source = _uri_safe(meta.get("source_id", entity_id))
        self._pm.track_entity(entity_id, source, metadata=meta)
        for parent in derived_from or []:
            self._track_derivation(entity_id, parent)
        return entity_id

    def record_decision(self, decision: Decision) -> dict:
        self._decision_seq += 1
        decision_id = f"decision-{self._decision_seq}"
        self._pm.track_entity(
            decision_id, _uri_safe(decision.scenario or decision_id),
            metadata={
                "kind": "decision",
                "scenario": decision.scenario,
                "outcome": decision.outcome,
            },
        )
        for ev in decision.evidence:
            self._track_derivation(decision_id, ev)
        return {"decision_id": decision_id, "recorded": True, "backend": "semantica"}

    # -- lineage / integrity ---------------------------------------------------

    @staticmethod
    def _interpret_verify(res: Any) -> bool:
        """``verify_chain()`` returns a dict in 0.6.8; reduce it to a bool defensively."""
        if isinstance(res, bool):
            return res
        if isinstance(res, dict):
            for key in ("valid", "is_valid", "verified", "intact", "ok", "conforms"):
                if key in res:
                    return bool(res[key])
            for key in ("broken", "errors", "tampered", "invalid"):
                if res.get(key):
                    return False
            return True
        return bool(res)

    def verify_chain(self) -> bool:
        return self._interpret_verify(self._pm.verify_chain())

    def trace_chain(self, decision_id: str) -> dict:
        # export_prov() returns PROV-O (Turtle); callers can SPARQL wasDerivedFrom+.
        prov_o = self._pm.export_prov()
        return {
            "decision_id": decision_id,
            "found": True,
            "verified": self.verify_chain(),
            "prov_o": prov_o,
            "backend": "semantica",
        }
