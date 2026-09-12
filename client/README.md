# fabric-client

The thin, **semantica-free** client and wire-contract types for
[semantic-fabric](../README.md). Consumers (e.g. skilled-agent's
`RemoteFabricBackend`) depend on **this package only** — never on `semantica` or any
graph/vector library.

```python
from fabric_client import FabricClient

fc = FabricClient("http://semantic-fabric:8080", token="...")
units = fc.search("what are ISAs?", section="investments")
legacy = [u.to_legacy() for u in units]   # {path, title, summary}
```

## What's in here

- `fabric_client.models` — the pydantic wire contract (`EvidenceUnit`, `Provenance`,
  request/response types). **This is the single source of truth for the boundary.**
- `fabric_client.http.FabricClient` — synchronous HTTP client mirroring the REST API.

## Compatibility

The `EvidenceUnit` schema evolves by **backward-compatible addition only**. Breaking
changes require a major version bump. `contracts/evidence_unit.schema.json` in the
repo root is a committed snapshot of this model.
