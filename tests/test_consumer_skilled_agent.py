"""Consumer-driven contract test: skilled-agent's RemoteFabricBackend.

These assertions encode exactly what skilled-agent depends on TODAY, so a breaking
change to the wire contract fails here — in semantic-fabric's CI — rather than in
production. Each test mirrors a specific call RemoteFabricBackend makes:

    backend/knowledge/backends.py :: RemoteFabricBackend
        __init__ -> FabricClient(...).health()          # probe at construction
        search   -> FabricClient.search(...)            # POST /search
                 -> [u.to_legacy() for u in units]      # {path, title, summary}

If you change EvidenceUnit / SearchResponse / the /health or /search shapes, update
skilled-agent's backend AND these expectations together.
"""

from fabric_client.models import SearchResponse
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

LEGACY_KEYS = {"path", "title", "summary"}


def test_health_probe_used_at_backend_construction():
    # RemoteFabricBackend.__init__ calls client.health() and marks itself available
    # only if this succeeds and reports a contract version.
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert "contract_version" in body, "RemoteFabricBackend relies on /health returning a version"


def test_search_units_project_to_legacy_shape(sample_kb):
    # This is the exact path RemoteFabricBackend.search follows.
    r = client.post("/search", json={"query": "tax-efficient savings account", "top_k": 5})
    assert r.status_code == 200
    resp = SearchResponse.model_validate(r.json())
    assert resp.units, "consumer expects at least one unit for a matching query"
    for unit in resp.units:
        legacy = unit.to_legacy()
        # skilled-agent hands these dicts straight to its existing UI/agent contract.
        assert set(legacy.keys()) == LEGACY_KEYS
        assert all(isinstance(legacy[k], str) for k in LEGACY_KEYS)


def test_search_response_carries_contract_version(sample_kb):
    r = client.post("/search", json={"query": "insurance", "top_k": 1})
    assert r.status_code == 200
    assert SearchResponse.model_validate(r.json()).contract_version
