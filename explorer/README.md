# fabric-explorer

A small **separate web service** to browse what's in the semantic-fabric — a
content-focused front end (not a run report), in the platform guide's look-and-feel.

It serves a single-page UI and **proxies the fabric's read API**, so the browser makes
same-origin calls (no CORS to configure, and the fabric is left untouched).

## Run

```bash
# 1. the fabric must be running (with data ingested), e.g. on :8080
# 2. start the explorer on its own port, pointed at the fabric:
FABRIC_URL=http://localhost:8080 uvicorn explorer.server:app --port 8090
# open http://localhost:8090
```

Only needs FastAPI + uvicorn (already the base deps) — no extra install. `FABRIC_URL`
defaults to `http://localhost:8080`; proxy env vars are bypassed for localhost.

## What you can see

- **Overview** — counts (authored/generated pages, entities, relations), the most-
  connected entities, top relation types, and sections.
- **Knowledge base** — browse the `authored/` and `generated/` namespaces; click a page
  to read it (Markdown rendered, with frontmatter).
- **Knowledge graph** — searchable/sortable **Entities** and **Relations** tables; click
  an entity for its type, relations, a neighbourhood diagram, and the pages that mention
  it (which link back into the KB view).
- **Search** — hybrid retrieval; each result links to open its KB page.

Read-only: it never writes to the fabric. Ingestion stays a separate, deliberate step.
