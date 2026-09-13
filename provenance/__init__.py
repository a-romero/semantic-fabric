"""Provenance + decisions (Phase 3): auditable lineage.

record_decision() persists agent answers as decision nodes derived from the evidence
they cited; trace_chain() returns the transitive lineage — "why did the agent say
this, and from what?". The in-memory default adds a tamper-evident hash chain; the
optional semantica backend emits W3C PROV-O. Public surface:

    build_provenance_store(kind) -> ProvenanceStore
    ProvenanceStore.record_decision(decision) / .trace_chain(id) / .verify_chain()
"""

from .store import (
    InMemoryProvenanceStore,
    ProvenanceStore,
    build_provenance_store,
)

__all__ = ["ProvenanceStore", "InMemoryProvenanceStore", "build_provenance_store"]
