#!/usr/bin/env python3
"""Diagnose a hanging /search — isolate Qdrant-vs-proxy without touching the fabric.

Run it on the SAME machine/env as the fabric:

    QDRANT_URL=http://localhost:6333 QDRANT_COLLECTION=authored \\
    FABRIC_URL=http://localhost:8080 python scripts/diag_search.py

It prints four things:
  1. the proxy env this process sees (and whether localhost is excluded);
  2. Qdrant reachability + vector count, fetched with the proxy BYPASSED;
  3. the same fetch WITHOUT bypassing the proxy (what qdrant-client/httpx actually do)
     — if this stalls while (2) is instant, a corporate/agent proxy is intercepting
     localhost and that is your hang;
  4. a timed real vector query against the collection, so you can see whether Qdrant
     itself has become slow at the current data volume.

Nothing here writes to Qdrant or the fabric.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333").rstrip("/")
COLLECTION = os.getenv("QDRANT_COLLECTION", "authored")
FABRIC_URL = os.getenv("FABRIC_URL", "http://localhost:8080").rstrip("/")
TIMEOUT = float(os.getenv("DIAG_TIMEOUT", "20"))

_BYPASS = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_ENVPROXY = urllib.request.build_opener()  # honours HTTP(S)_PROXY / NO_PROXY like httpx


def _get(opener, url: str) -> tuple[float, object]:
    t0 = time.perf_counter()
    req = urllib.request.Request(url, method="GET")
    with opener.open(req, timeout=TIMEOUT) as resp:
        body = json.loads(resp.read().decode())
    return (time.perf_counter() - t0) * 1000, body


def _post(opener, url: str, payload: dict) -> tuple[float, object]:
    t0 = time.perf_counter()
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, method="POST", headers={"content-type": "application/json"}
    )
    with opener.open(req, timeout=TIMEOUT) as resp:
        body = json.loads(resp.read().decode())
    return (time.perf_counter() - t0) * 1000, body


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> None:
    # 1. proxy env
    section("1. proxy environment seen by this process")
    https = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy") or "(none)"
    noproxy = os.getenv("NO_PROXY") or os.getenv("no_proxy") or "(none)"
    print(f"HTTPS_PROXY = {https}")
    print(f"NO_PROXY    = {noproxy}")
    host = QDRANT_URL.split("://", 1)[-1].split(":", 1)[0]
    excluded = any(tok and tok in noproxy for tok in (host, "localhost", "127.0.0.1"))
    print(f"Qdrant host '{host}' excluded from proxy? {'YES' if excluded else 'NO'}")
    if https != "(none)" and not excluded:
        print("  ^ WARNING: a proxy is set and Qdrant's host is NOT in NO_PROXY. "
              "qdrant-client (httpx) will route localhost through the proxy.")

    # 2. Qdrant, proxy bypassed
    section("2. Qdrant collection info (proxy BYPASSED — should be instant)")
    try:
        ms, info = _get(_BYPASS, f"{QDRANT_URL}/collections/{COLLECTION}")
        res = info.get("result", {})
        count = res.get("points_count") or res.get("vectors_count")
        status = res.get("status")
        print(f"OK in {ms:.0f} ms — points={count} status={status}")
    except Exception as e:
        print(f"FAILED: {e}")

    # 3. Qdrant, honouring proxy env (what the client actually does)
    section("3. Qdrant collection info (proxy env HONOURED — as qdrant-client does)")
    try:
        ms, _ = _get(_ENVPROXY, f"{QDRANT_URL}/collections/{COLLECTION}")
        print(f"OK in {ms:.0f} ms")
        print("  -> proxy is NOT intercepting localhost; the hang is not the proxy.")
    except Exception as e:
        print(f"FAILED/STALLED: {e}")
        print("  -> if step 2 was instant but this stalls, THE PROXY IS YOUR HANG. "
              "Start the fabric with NO_PROXY including localhost,127.0.0.1.")

    # 4. real timed vector query (proxy bypassed), at the current data volume
    section("4. timed vector query against the collection (proxy bypassed)")
    try:
        _, info = _get(_BYPASS, f"{QDRANT_URL}/collections/{COLLECTION}")
        dim = (info["result"]["config"]["params"]["vectors"]["size"])
        vec = [0.0] * dim
        vec[0] = 1.0
        for i in range(3):
            ms, body = _post(
                _BYPASS, f"{QDRANT_URL}/collections/{COLLECTION}/points/query",
                {"query": vec, "limit": 20},
            )
            n = len(body.get("result", {}).get("points", []))
            print(f"query {i + 1}: {ms:.0f} ms ({n} hits)")
    except Exception as e:
        print(f"FAILED: {e}")

    # 5. the fabric's own /search
    section("5. fabric POST /search (proxy bypassed)")
    try:
        for i in range(2):
            ms, body = _post(_BYPASS, f"{FABRIC_URL}/search",
                             {"query": "test query", "top_k": 5})
            print(f"/search {i + 1}: {ms:.0f} ms ({len(body.get('units', []))} units)")
    except Exception as e:
        print(f"FAILED/STALLED: {e}")


if __name__ == "__main__":
    main()
