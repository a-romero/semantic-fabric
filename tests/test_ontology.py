"""Phase 3 SHACL policy-gate tests (SimpleConstraintValidator default backend)."""

from fastapi.testclient import TestClient

from api.main import app
from ontology.validator import (
    Constraint,
    SimpleConstraintValidator,
    ValidationRequest,
)

client = TestClient(app)

# "Every Policy must have a policyholder; premium >= 0" — the spike's example.
POLICY_CONSTRAINT = Constraint(
    target_class="Policy",
    required=["policyholder"],
    min_values={"premium": 0},
    message=None,
)


def test_conforming_data_passes():
    v = SimpleConstraintValidator()
    res = v.validate(ValidationRequest(
        entities=[
            {"id": "p1", "class": "Policy",
             "props": {"policyholder": "Alice", "premium": 12.5}}
        ],
        constraints=[POLICY_CONSTRAINT],
    ))
    assert res.conforms is True
    assert res.violations == []


def test_missing_required_property_fails_with_path():
    v = SimpleConstraintValidator()
    res = v.validate(ValidationRequest(
        entities=[{"id": "p2", "class": "Policy", "props": {"premium": 10}}],
        constraints=[POLICY_CONSTRAINT],
    ))
    assert res.conforms is False
    assert any(viol.path == "policyholder" and viol.entity_id == "p2" for viol in res.violations)


def test_min_value_violation():
    v = SimpleConstraintValidator()
    res = v.validate(ValidationRequest(
        entities=[{"id": "p3", "class": "Policy", "props": {"policyholder": "Bob", "premium": -5}}],
        constraints=[POLICY_CONSTRAINT],
    ))
    assert res.conforms is False
    assert any(viol.path == "premium" for viol in res.violations)


def test_allowed_values_violation():
    v = SimpleConstraintValidator()
    res = v.validate(ValidationRequest(
        entities=[{"id": "c1", "class": "Claim", "props": {"status": "banana"}}],
        constraints=[Constraint(target_class="Claim",
                                allowed_values={"status": ["open", "closed"]})],
    ))
    assert res.conforms is False


def test_validate_endpoint_gate():
    # conforming
    ok = client.post("/validate", json={
        "entities": [{"id": "p1", "class": "Policy", "props": {"policyholder": "A", "premium": 1}}],
        "constraints": [{"target_class": "Policy", "required": ["policyholder"],
                         "min_values": {"premium": 0}}],
    })
    assert ok.status_code == 200 and ok.json()["conforms"] is True

    # violating -> the gate would block this answer from leaving the plane
    bad = client.post("/validate", json={
        "entities": [{"id": "p2", "class": "Policy", "props": {"premium": -1}}],
        "constraints": [{"target_class": "Policy", "required": ["policyholder"],
                         "min_values": {"premium": 0}}],
    })
    body = bad.json()
    assert body["conforms"] is False
    paths = {v["path"] for v in body["violations"]}
    assert {"policyholder", "premium"} <= paths
