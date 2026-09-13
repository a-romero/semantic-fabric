"""On-env validation: the optional semantica-backed layers.

These are SKIPPED unless `semantica` is installed (the `.[semantica]` extra). They
exercise the real adapters end to end — the checks CI here cannot run — so a failure
means the spike-confirmed API drifted and the adapter needs a fix (that's the point).

Run on an environment with semantica installed:
    pip install -e ".[semantica]"
    pytest -q tests/test_semantica_backends.py
"""

import pytest

pytest.importorskip("semantica")

from fabric_client.models import Decision  # noqa: E402

from ontology.shacl_backend import ShaclValidator  # noqa: E402
from ontology.validator import Constraint, ValidationRequest  # noqa: E402
from provenance.semantica_backend import SemanticaProvenanceStore  # noqa: E402
from reasoning.engine import ReasoningRequest, Rule  # noqa: E402
from reasoning.semantica_backend import SemanticaReasoningEngine  # noqa: E402


def test_semantica_provenance_prov_o_and_chain():
    store = SemanticaProvenanceStore()
    store.record_entity("report-q3.pdf#p12", kind="evidence",
                        attrs={"source_id": "report-q3.pdf"})
    rec = store.record_decision(
        Decision(scenario="Q3 revenue?", outcome="4.2", evidence=["report-q3.pdf#p12"])
    )
    assert rec["recorded"] is True and rec["backend"] == "semantica"
    chain = store.trace_chain(rec["decision_id"])
    # real PROV-O export + tamper-evident chain
    assert chain["verified"] is True
    assert chain.get("prov_o"), "expected a non-empty PROV-O export"


def test_semantica_reasoning_forward_chain_with_explanation():
    eng = SemanticaReasoningEngine()
    res = eng.reason(ReasoningRequest(
        query="Insurable(motor_policy)",
        facts=["Policy(motor_policy)"],
        rules=[
            Rule(name="R1", body=["Policy(motor_policy)"], head="Underwritten(motor_policy)"),
            Rule(name="R2", body=["Underwritten(motor_policy)"], head="Insurable(motor_policy)"),
        ],
    ))
    assert res.answer.startswith("Yes")
    assert res.rule_trace, "expected an explanation trace"


def test_semantica_shacl_conform_and_violate():
    v = ShaclValidator()
    constraint = Constraint(target_class="Policy", required=["policyholder"],
                            min_values={"premium": 0})
    ok = v.validate(ValidationRequest(
        entities=[{"id": "p1", "class": "Policy",
                   "props": {"policyholder": "Alice", "premium": 10}}],
        constraints=[constraint],
    ))
    assert ok.conforms is True

    bad = v.validate(ValidationRequest(
        entities=[{"id": "p2", "class": "Policy", "props": {"premium": 5}}],
        constraints=[constraint],
    ))
    assert bad.conforms is False
