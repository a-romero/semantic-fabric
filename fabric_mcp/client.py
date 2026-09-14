"""HTTP client for semantic-fabric's query surface (stdlib only, no mcp dependency).

Every call goes through ``_call`` — one seam that the tests replace with an in-process
transport, and that bypasses proxy env vars (a corporate proxy will otherwise intercept
``localhost`` and 400 the request).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

_HINT = ("Check that the fabric is running and FABRIC_URL is correct "
         "(default http://localhost:8080), and that data has been ingested.")


def base_url() -> str:
    return os.getenv("FABRIC_URL", "http://localhost:8080").rstrip("/")


def _timeout() -> int:
    return int(os.getenv("FABRIC_TIMEOUT", "60"))


def _call(method: str, path: str, body: dict | None = None) -> dict:
    """Single HTTP seam. Raises RuntimeError with an actionable message on failure."""
    data = json.dumps(body).encode() if body is not None else None
    headers = {"content-type": "application/json"} if data is not None else {}
    req = urllib.request.Request(base_url() + path, data=data, method=method, headers=headers)
    try:
        with _OPENER.open(req, timeout=_timeout()) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"fabric HTTP {e.code} on {method} {path}: {detail}") from e
    except Exception as e:  # connection refused, timeout, DNS, proxy, …
        raise RuntimeError(f"cannot reach fabric at {base_url()} ({e}). {_HINT}") from e


# -- query surface ----------------------------------------------------------


def health() -> dict:
    return _call("GET", "/health")


def search(query: str, top_k: int = 5, section: str | None = None) -> list[dict]:
    return _call("POST", "/search",
                 {"query": query, "top_k": top_k, "section": section})["units"]


def graph_expand(seed: str, hops: int = 2, rel_types: list[str] | None = None) -> list[dict]:
    return _call("POST", "/graph/expand",
                 {"seed": seed, "hops": hops, "rel_types": rel_types})["units"]


def graph_snapshot() -> dict:
    return _call("GET", "/graph")


def reason(query: str, facts: list[str] | None = None,
           rules: list[dict] | None = None, over_graph: bool = False) -> dict:
    return _call("POST", "/reason", {
        "query": query, "facts": facts or [], "rules": rules or [], "over_graph": over_graph,
    })


def record_decision(scenario: str, outcome: str = "", evidence: list[str] | None = None,
                    reasoning: str = "") -> dict:
    return _call("POST", "/decisions", {
        "scenario": scenario, "outcome": outcome, "reasoning": reasoning,
        "evidence": evidence or [],
    })


def decision_chain(decision_id: str) -> dict:
    return _call("GET", f"/decisions/{decision_id}/chain")


def validate(entities: list[dict], constraints: list[dict]) -> dict:
    return _call("POST", "/validate", {"entities": entities, "constraints": constraints})


def read_page(namespace: str, path: str) -> dict:
    return _call("GET", f"/kb/{namespace}/{path}")


# -- the full query cycle ---------------------------------------------------

_GUIDANCE = (
    "Answer the question using ONLY the evidence content above. Cite each claim with its "
    "provenance.locator (page/section, or PDF page + bounding box). 'related' gives graph-"
    "connected context. 'decision'/'lineage' record what was used, for audit — quote the "
    "decision_id if the caller needs the trail."
)


def answer(question: str, top_k: int = 5, section: str | None = None,
           expand: bool = True, record: bool = True) -> dict:
    """Run the full query cycle and return everything needed to answer with provenance.

    retrieve → (graph-expand from the top hit) → (record a decision citing the top
    evidence) → (fetch the decision's lineage). Sub-steps degrade gracefully so a partial
    fabric still yields evidence.
    """
    units = search(question, top_k=top_k, section=section)
    top = units[0] if units else None

    related: list[dict] = []
    if expand and top:
        try:
            related = graph_expand(top["path"], hops=2)
        except Exception:
            related = []

    decision = lineage = None
    if record and top:
        try:
            decision = record_decision(
                scenario=question,
                outcome=top.get("summary", ""),
                evidence=[u["path"] for u in units[:3]],
            )
            did = decision.get("decision_id")
            if did:
                lineage = decision_chain(did)
        except Exception as e:
            decision = {"recorded": False, "error": str(e)}

    return {
        "question": question,
        "fabric": base_url(),
        "evidence": units,
        "related": related,
        "decision": decision,
        "lineage": lineage,
        "guidance": _GUIDANCE,
    }
