"""fabric-explorer — a small, separate web service to browse what's in the fabric.

Serves a single-page UI (``explorer/static``) and proxies the fabric's read API so the
browser makes same-origin calls (no CORS; the fabric is untouched). Point it at a running
fabric with ``FABRIC_URL`` and run it on its own port:

    FABRIC_URL=http://localhost:8080 uvicorn explorer.server:app --port 8090
"""
