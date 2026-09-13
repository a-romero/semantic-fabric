"""Ontology / SHACL validation (Phase 3): the deterministic policy gate.

Validates entity data against declared constraints before an answer leaves the
semantic plane. A dependency-free constraint checker is the default; the optional
pyshacl/semantica backend runs real SHACL. Public surface:

    build_ontology_validator(kind) -> OntologyValidator
    OntologyValidator.validate(ValidationRequest) -> ValidationResult
"""

from .validator import (
    Constraint,
    OntologyValidator,
    SimpleConstraintValidator,
    ValidationRequest,
    ValidationResult,
    Violation,
    build_ontology_validator,
)

__all__ = [
    "Constraint",
    "OntologyValidator",
    "SimpleConstraintValidator",
    "ValidationRequest",
    "ValidationResult",
    "Violation",
    "build_ontology_validator",
]
