"""Ontology / SHACL validation (Phase 3): the deterministic policy gate.

Validates data (facts about entities) against declared constraints before an answer
leaves the semantic plane — "the LLM proposes, the deterministic layer disposes".
Two backends behind one protocol (same pattern as the other Phase 3 layers):

- ``SimpleConstraintValidator`` — dependency-free default: checks a compact set of
  declarative constraints (required properties, min/allowed values) over plain
  entity dicts. Real, tested, and enough to gate answers without pyshacl.
- ``ShaclValidator`` — optional (``.[semantica]`` extra): pyshacl-backed
  ``run_shacl_validation`` over an RDF data graph + SHACL shapes graph
  (spike-confirmed: conforming passes, violations report correct paths + messages).

Selected by ``ONTOLOGY_VALIDATOR`` (``simple`` default, ``shacl`` in deployment).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class Constraint:
    """A declarative constraint over entities of a given class.

    - ``required``: property names that must be present and non-null.
    - ``min_values``: property -> minimum numeric value.
    - ``allowed_values``: property -> allowed set of values.
    """

    target_class: str
    required: list[str] = field(default_factory=list)
    min_values: dict[str, float] = field(default_factory=dict)
    allowed_values: dict[str, list[Any]] = field(default_factory=dict)
    message: str | None = None


@dataclass
class Violation:
    entity_id: str
    target_class: str
    path: str
    message: str


@dataclass
class ValidationRequest:
    # entities: [{"id":..., "class":"Policy", "props": {...}}]
    entities: list[dict[str, Any]] = field(default_factory=list)
    constraints: list[Constraint] = field(default_factory=list)


@dataclass
class ValidationResult:
    conforms: bool
    violations: list[Violation] = field(default_factory=list)


class OntologyValidator(Protocol):
    def validate(self, req: ValidationRequest) -> ValidationResult: ...


class SimpleConstraintValidator:
    """Dependency-free constraint checker over entity dicts."""

    def validate(self, req: ValidationRequest) -> ValidationResult:
        by_class: dict[str, list[Constraint]] = {}
        for c in req.constraints:
            by_class.setdefault(c.target_class, []).append(c)

        violations: list[Violation] = []
        for ent in req.entities:
            cls = ent.get("class", "")
            props = ent.get("props", {}) or {}
            eid = str(ent.get("id", "<unknown>"))
            for c in by_class.get(cls, []):
                for prop in c.required:
                    if props.get(prop) in (None, "", []):
                        violations.append(Violation(
                            eid, cls, prop,
                            c.message or f"{cls}.{prop} is required.",
                        ))
                for prop, minv in c.min_values.items():
                    val = props.get(prop)
                    if isinstance(val, (int, float)) and val < minv:
                        violations.append(Violation(
                            eid, cls, prop,
                            c.message or f"{cls}.{prop} must be >= {minv} (got {val}).",
                        ))
                for prop, allowed in c.allowed_values.items():
                    if prop in props and props[prop] not in allowed:
                        violations.append(Violation(
                            eid, cls, prop,
                            c.message or f"{cls}.{prop}={props[prop]!r} not in {allowed}.",
                        ))
        return ValidationResult(conforms=not violations, violations=violations)


def build_ontology_validator(kind: str | None) -> OntologyValidator:
    """Factory from ONTOLOGY_VALIDATOR. Falls back to the simple validator."""
    choice = (kind or "simple").strip().lower()
    if choice == "shacl":
        try:
            from .shacl_backend import ShaclValidator

            return ShaclValidator()
        except Exception:
            return SimpleConstraintValidator()
    return SimpleConstraintValidator()
