"""Phase 3 reasoning tests (SimpleForwardChainer default backend)."""

from fastapi.testclient import TestClient

from api.main import app
from reasoning.engine import ReasoningRequest, Rule, SimpleForwardChainer

client = TestClient(app)


def test_forward_chaining_derives_transitively():
    eng = SimpleForwardChainer()
    req = ReasoningRequest(
        query="Insurable(motor_policy)",
        facts=["Policy(motor_policy)"],
        rules=[
            Rule(name="R1", body=["Policy(motor_policy)"], head="Underwritten(motor_policy)"),
            Rule(name="R2", body=["Underwritten(motor_policy)"], head="Insurable(motor_policy)"),
        ],
    )
    res = eng.reason(req)
    assert res.answer.startswith("Yes")
    # explanation trace names the rules used, in order
    assert any("R1" in t for t in res.rule_trace)
    assert any("R2" in t for t in res.rule_trace)


def test_unprovable_query_reports_no():
    eng = SimpleForwardChainer()
    res = eng.reason(ReasoningRequest(query="Insurable(x)", facts=["Policy(y)"], rules=[]))
    assert res.answer.startswith("No")


def test_reason_endpoint_explains_conclusion():
    r = client.post("/reason", json={
        "query": "Covered(claim1)",
        "facts": ["ValidPolicy(claim1)"],
        "rules": [{"name": "coverage", "body": ["ValidPolicy(claim1)"], "head": "Covered(claim1)"}],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["answer"].startswith("Yes")
    assert body["rule_trace"] and "coverage" in body["rule_trace"][0]


def test_reason_endpoint_gate(monkeypatch):
    monkeypatch.setenv("ENABLE_REASONING", "false")
    r = client.post("/reason", json={"query": "X", "facts": [], "rules": []})
    assert r.status_code == 200
    assert "disabled" in r.json()["answer"].lower()
