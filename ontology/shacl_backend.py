"""pyshacl / semantica-backed SHACL validator (optional; .[semantica] extra).

Translates the same declarative constraints into a SHACL shapes graph and validates
an RDF data graph with pyshacl (via semantica's run_shacl_validation, which the
evaluation spike confirmed: conforming data passes, violations report correct
paths + custom messages). Written to the spike-confirmed API; MUST be validated on an
environment where semantica/pyshacl are installed — CI runs the simple validator.
"""

from __future__ import annotations

from .validator import Constraint, ValidationRequest, ValidationResult, Violation

EX = "http://semantic-fabric/ex#"


def _attr(obj: object, *names: str) -> str:
    """First present attribute (or dict key) among ``names``, as a string."""
    for name in names:
        val = obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)
        if val:
            return str(val)
    return ""


def _shapes_ttl(constraints: list[Constraint]) -> str:
    lines = [
        "@prefix sh: <http://www.w3.org/ns/shacl#> .",
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
        f"@prefix ex: <{EX}> .",
        "",
    ]
    for i, c in enumerate(constraints):
        s = f"ex:Shape{i}"
        lines.append(f"{s} a sh:NodeShape ; sh:targetClass ex:{c.target_class} ;")
        for prop in c.required:
            lines.append(
                f'  sh:property [ sh:path ex:{prop} ; sh:minCount 1 ; '
                f'sh:message "{c.message or f"{c.target_class}.{prop} is required."}" ] ;'
            )
        for prop, minv in c.min_values.items():
            lines.append(
                f"  sh:property [ sh:path ex:{prop} ; sh:minInclusive {minv} ] ;"
            )
        lines[-1] = lines[-1].rstrip(" ;") + " ."
    return "\n".join(lines)


def _data_ttl(entities: list[dict]) -> str:
    lines = [f"@prefix ex: <{EX}> .", ""]
    for ent in entities:
        subj = f"ex:{ent.get('id', 'x')}"
        lines.append(f"{subj} a ex:{ent.get('class', 'Thing')} ;")
        props = ent.get("props", {}) or {}
        for k, v in props.items():
            lit = v if isinstance(v, (int, float)) else f'"{v}"'
            lines.append(f"  ex:{k} {lit} ;")
        lines[-1] = lines[-1].rstrip(" ;") + " ."
    return "\n".join(lines)


class ShaclValidator:
    def __init__(self) -> None:
        # Prefer semantica's wrapper; fall back to pyshacl directly.
        try:
            from semantica.ontology import run_shacl_validation  # type: ignore

            self._run = run_shacl_validation
            self._mode = "semantica"
        except Exception:
            import pyshacl  # type: ignore

            self._pyshacl = pyshacl
            self._mode = "pyshacl"

    def validate(self, req: ValidationRequest) -> ValidationResult:
        shapes = _shapes_ttl(req.constraints)
        data = _data_ttl(req.entities)
        if self._mode == "semantica":
            # 0.6.8: run_shacl_validation(data_graph_str, shacl_str, ...) -> report.
            report = self._run(data, shapes)
            conforms = bool(getattr(report, "conforms", False))
            raw = getattr(report, "violations", None) or []
            violations = [
                Violation(
                    _attr(v, "focus_node", "focus", "focusNode"),
                    _attr(v, "target_class", "source_shape", "sourceShape"),
                    _attr(v, "path", "result_path", "resultPath"),
                    _attr(v, "message", "result_message", "resultMessage") or str(v),
                )
                for v in raw
            ]
            return ValidationResult(conforms=conforms, violations=violations)
        # pyshacl direct
        conforms, _graph, text = self._pyshacl.validate(
            data, shacl_graph=shapes, data_graph_format="turtle",
            shacl_graph_format="turtle", inference="none",
        )
        violations = [] if conforms else [Violation("", "", "", text)]
        return ValidationResult(conforms=conforms, violations=violations)
