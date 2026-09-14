"""fabric-explorer service: serve the UI and proxy the fabric's read API.

The browser talks only to this service (same-origin `/api/...`), which forwards to the
fabric at FABRIC_URL — so there's no CORS to configure and the fabric stays untouched.
Proxy env vars are bypassed (a corporate proxy otherwise intercepts localhost).

    FABRIC_URL=http://localhost:8080 uvicorn explorer.server:app --port 8090
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

FABRIC_URL = os.getenv("FABRIC_URL", "http://localhost:8080").rstrip("/")
_TIMEOUT = int(os.getenv("FABRIC_TIMEOUT", "60"))
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="fabric-explorer", summary="Browse what's in the semantic-fabric.")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "fabric_url": FABRIC_URL}


@app.api_route("/api/{path:path}", methods=["GET", "POST"])
async def proxy(path: str, request: Request) -> Response:
    """Forward /api/<path> to the fabric, preserving method, query string and body."""
    body = await request.body()
    query = request.url.query
    url = f"{FABRIC_URL}/{path}" + (f"?{query}" if query else "")
    method = request.method

    def _do() -> tuple[int, bytes, str]:
        req = urllib.request.Request(
            url,
            data=body if method == "POST" else None,
            method=method,
            headers={"content-type": "application/json"} if body else {},
        )
        ct = "application/json"
        try:
            with _OPENER.open(req, timeout=_TIMEOUT) as resp:
                return resp.status, resp.read(), resp.headers.get("content-type", ct)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers.get("content-type", ct)
        except Exception as e:  # unreachable fabric / timeout / proxy
            payload = json.dumps({"error": f"cannot reach fabric at {FABRIC_URL}: {e}"})
            return 502, payload.encode(), "application/json"

    status, content, ctype = await run_in_threadpool(_do)
    return Response(content=content, status_code=status, media_type=ctype)


# Serve the SPA. Mounted last so the /api route and /healthz take precedence.
app.mount("/", StaticFiles(directory=str(_STATIC), html=True), name="ui")
