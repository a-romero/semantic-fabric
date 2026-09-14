#!/usr/bin/env python
"""End-to-end platform demo: ingest a directory, exercise every capability, visualise.

Point this at a folder of ``.md`` and/or ``.pdf`` files (nested is fine); it ingests
them into a running semantic-fabric service, then drives the full capability set —
retrieval, GraphRAG, LLM extraction, reason-over-KG, provenance + lineage, and the SHACL
gate — for a question you ask, and writes a single self-contained HTML report
visualising the corpus, the knowledge graph, and everything the platform did.

    # 1. start the service (defaults work; real backends light up with the env from
    #    scripts/validate.sh — e.g. EXTRACTION_ON_INGEST=true for the knowledge graph)
    uvicorn api.main:app --port 8080 &

    # 2. run the demo
    python demo/run_demo.py --source demo/sample_corpus \
        --question "Is a Cash ISA tax-free and who offers it?"

    # 3. open demo/out/report.html

Dependency-free (stdlib only). See demo/RUNBOOK.md for the full walkthrough.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# tiny HTTP helpers (stdlib) — the raw REST boundary, same calls as the runbook
# ---------------------------------------------------------------------------


# Bypass any HTTP(S)_PROXY / ALL_PROXY in the environment — the fabric is typically on
# localhost, and a corporate proxy will 400/407 a request it should never have seen.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_TIMEOUT = 600  # seconds; set from --timeout in main (LLM-on-ingest can be slow at scale)


def _req(method: str, url: str, body: dict | None = None,
         timeout: int | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"content-type": "application/json"} if data is not None else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with _OPENER.open(req, timeout=timeout or _TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"HTTP {e.code} from {method} {url}: {detail}") from e


def get(base: str, path: str) -> dict:
    return _req("GET", base + path)


def post(base: str, path: str, body: dict, timeout: int | None = None) -> dict:
    return _req("POST", base + path, body, timeout=timeout)


def _const(s: str) -> str:
    """Mirror graph.store.datalog_const so synthesized queries match server facts."""
    c = re.sub(r"[^a-z0-9]+", "_", str(s).strip().lower()).strip("_")
    return c if (c and c[0].isalpha()) else f"e_{c}"


# ---------------------------------------------------------------------------
# discovery + ingestion
# ---------------------------------------------------------------------------

_FM = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Minimal front-matter parser: title + topics (list or comma string)."""
    m = _FM.match(text)
    if not m:
        return {}, text
    fm: dict = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        if not val:
            continue
        if val.startswith("[") and val.endswith("]"):
            fm[key] = [v.strip() for v in val[1:-1].split(",") if v.strip()]
        elif key == "topics":
            fm[key] = [v.strip() for v in val.split(",") if v.strip()]
        else:
            fm[key] = val
    return fm, text[m.end():]


def _title_from(body: str, rel: str) -> str:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return Path(rel).stem.replace("-", " ").replace("_", " ").title()


def discover(source: Path) -> tuple[list[dict], list[dict]]:
    md_pages, pdf_docs = [], []
    for p in sorted(source.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(source).as_posix()
        if p.suffix.lower() == ".md":
            fm, body = parse_frontmatter(p.read_text(encoding="utf-8", errors="replace"))
            fm.setdefault("title", _title_from(body, rel))
            md_pages.append({"path": rel, "frontmatter": fm, "body": body})
        elif p.suffix.lower() == ".pdf":
            pdf_docs.append({
                "doc_id": Path(rel).with_suffix("").as_posix().replace("/", "_"),
                "title": Path(rel).stem.replace("-", " ").title(),
                "pdf_b64": base64.b64encode(p.read_bytes()).decode(),
                "source_path": rel,
            })
    return md_pages, pdf_docs


def maybe_make_sample_pdf(source: Path) -> None:
    """If PyMuPDF is available, drop a small PDF into the corpus so the PDF path runs."""
    target = source / "reports" / "q3-report.pdf"
    if target.exists():
        return
    try:
        import fitz  # PyMuPDF
    except Exception:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 90), "Aviva Q3 Report", fontsize=18)
    page.insert_text((72, 130),
                     "Group revenue grew in the third quarter across all regions.")
    page.insert_text((72, 150),
                     "The Enhanced Pension Annuity contributed to pensions growth.")
    doc.save(str(target))
    doc.close()


def ingest(base: str, md_pages: list[dict], pdf_docs: list[dict],
           batch_size: int = 25) -> dict:
    """Ingest in batches so a large corpus survives (a single mega-request would time
    out — LLM extraction-on-ingest runs one model call per page, server-side)."""
    import time

    files, counts = [], {"md": 0, "pdf": 0, "chunks": 0, "tables": 0, "figures": 0,
                         "generated_pages": 0, "failed": 0}
    t0 = time.time()

    # Markdown in batches of `batch_size`; a failed/timed-out batch is recorded and the
    # run continues with the next batch rather than losing everything.
    batches = [md_pages[i:i + batch_size] for i in range(0, len(md_pages), batch_size)]
    for bi, batch in enumerate(batches, 1):
        try:
            job = post(base, "/ingest", {"kind": "markdown_tree", "namespace": "authored",
                                         "payload": {"pages": batch}})
            ok, detail = job.get("status") == "done", job.get("detail", "")
        except Exception as e:
            ok, detail = False, str(e)[:200]
        for pg in batch:
            files.append({"path": pg["path"], "kind": "markdown",
                          "status": "ok" if ok else "failed", "detail": detail})
        counts["md"] += len(batch)
        counts["failed"] += 0 if ok else len(batch)
        done = min(bi * batch_size, len(md_pages))
        print(f"   markdown batch {bi}/{len(batches)} "
              f"({done}/{len(md_pages)} pages) [{'ok' if ok else 'FAILED'}] "
              f"{time.time() - t0:.0f}s", flush=True)

    for di, doc in enumerate(pdf_docs, 1):
        try:
            job = post(base, "/ingest", {"kind": "pdf_batch",
                       "payload": {"documents": [{k: doc[k] for k in
                                   ("doc_id", "title", "pdf_b64")}]}})
            status = job.get("status")
            files.append({"path": doc["source_path"], "kind": "pdf",
                          "status": "ok" if status == "done" else "failed",
                          "detail": job.get("detail", "")})
            counts["pdf"] += 1
            counts["failed"] += 0 if status == "done" else 1
        except Exception as e:
            files.append({"path": doc["source_path"], "kind": "pdf",
                          "status": "failed", "detail": str(e)[:200]})
            counts["failed"] += 1
        print(f"   pdf {di}/{len(pdf_docs)} {doc['source_path']} "
              f"{time.time() - t0:.0f}s", flush=True)

    counts["elapsed_s"] = round(time.time() - t0, 1)
    return {"files": files, "counts": counts}


# ---------------------------------------------------------------------------
# capability sweep
# ---------------------------------------------------------------------------


def capability_sweep(base: str, question: str, snapshot: dict, seed: str | None) -> dict:
    caps: list[dict] = []
    out: dict = {"capabilities": caps}

    def record(name: str, ok: bool, detail: str) -> None:
        caps.append({"name": name, "status": "ok" if ok else "n/a", "detail": detail})

    # 1. hybrid retrieval
    try:
        res = post(base, "/search", {"query": question, "top_k": 5})
        out["evidence"] = res.get("units", [])
        record("Hybrid retrieval (vector + BM25)", bool(out["evidence"]),
               f"{len(out['evidence'])} evidence units for the question")
    except Exception as e:
        out["evidence"] = []
        record("Hybrid retrieval (vector + BM25)", False, str(e))

    # 2. GraphRAG expansion — seed from the top evidence page, or a provided seed
    seed = seed or (out["evidence"][0]["path"] if out.get("evidence") else "")
    try:
        exp = post(base, "/graph/expand", {"seed": seed, "hops": 2}) if seed else {"units": []}
        out["graph_expand"] = {"seed": seed, "units": exp.get("units", [])}
        record("GraphRAG expansion", bool(exp.get("units")),
               f"{len(exp.get('units', []))} related pages from seed '{seed}'")
    except Exception as e:
        out["graph_expand"] = {"seed": seed, "units": []}
        record("GraphRAG expansion", False, str(e))

    # 3. LLM extraction (typed entities/relations) — over a snippet of top evidence
    snippet = (out["evidence"][0]["content"] if out.get("evidence") else question)[:600]
    try:
        ex = post(base, "/extract", {"text": snippet})
        out["extract"] = ex
        record("LLM extraction", bool(ex.get("entities") or ex.get("relations")),
               f"{len(ex.get('entities', []))} entities, {len(ex.get('relations', []))} "
               f"relations (backend={ex.get('backend')}, model={ex.get('model')})")
    except Exception as e:
        out["extract"] = {}
        record("LLM extraction", False, str(e))

    # 4. reason over the knowledge graph — synthesize a rule from a real relation
    rels = snapshot.get("relations", [])
    if rels:
        r = rels[0]
        fact = f"{_const(r['predicate'])}({_const(r['subject'])}, {_const(r['object'])})"
        head = f"related_to_{_const(r['subject'])}({_const(r['object'])})"
        try:
            rr = post(base, "/reason", {
                "query": head, "over_graph": True,
                "rules": [{"name": "demo", "body": [fact], "head": head}],
            })
            out["reason"] = {"query": head, "rule": f"{head} :- {fact}.", **rr}
            record("Reason over the KG (Datalog)", rr.get("answer", "").startswith("Yes"),
                   f"derived '{head}' from the graph fact {fact}")
        except Exception as e:
            out["reason"] = {}
            record("Reason over the KG (Datalog)", False, str(e))
    else:
        out["reason"] = {}
        record("Reason over the KG (Datalog)", False,
               "no relations in the graph (enable EXTRACTION_ON_INGEST to populate it)")

    # 5. provenance: record the decision + trace its lineage
    ev_ids = [u["path"] for u in out.get("evidence", [])[:3]]
    try:
        dec = post(base, "/decisions", {"scenario": question,
                   "outcome": (out["evidence"][0]["summary"] if out.get("evidence") else ""),
                   "evidence": ev_ids})
        chain = get(base, f"/decisions/{dec['decision_id']}/chain") if dec.get("decision_id") else {}
        out["decision"], out["chain"] = dec, chain
        record("Provenance + lineage", bool(dec.get("recorded")),
               f"decision {dec.get('decision_id')} recorded (backend={dec.get('backend')}), "
               f"chain verified={chain.get('verified')}")
    except Exception as e:
        out["decision"], out["chain"] = {}, {}
        record("Provenance + lineage", False, str(e))

    # 6. SHACL policy gate — a conforming vs a violating entity
    try:
        constraint = {"target_class": "Policy", "required": ["policyholder"],
                      "min_values": {"premium": 0}}
        good = post(base, "/validate", {"constraints": [constraint], "entities": [
            {"id": "p1", "class": "Policy", "props": {"policyholder": "Alice", "premium": 10}}]})
        bad = post(base, "/validate", {"constraints": [constraint], "entities": [
            {"id": "p2", "class": "Policy", "props": {"premium": 5}}]})
        out["validate"] = {"conforming": good, "violating": bad}
        record("SHACL policy gate", good.get("conforms") is True and bad.get("conforms") is False,
               f"conforming passes ({good.get('conforms')}), violating fails "
               f"({bad.get('conforms')}, {len(bad.get('violations', []))} violation(s))")
    except Exception as e:
        out["validate"] = {}
        record("SHACL policy gate", False, str(e))

    return out


# ---------------------------------------------------------------------------
# HTML report (self-contained, offline; palette from the dataviz reference)
# ---------------------------------------------------------------------------

_PALETTE = ["#2a78d6", "#eb6834", "#1baf7a"]  # slots 1-3, all-pairs safe
_OTHER = "#8a8a86"


def _esc(s) -> str:
    return html.escape(str(s), quote=True)


def _stat_tiles(counts: dict, graph_counts: dict, kb: dict) -> str:
    tiles = [
        ("Files ingested", counts["md"] + counts["pdf"]),
        ("Markdown", counts["md"]),
        ("PDF", counts["pdf"]),
        ("Authored pages", kb.get("authored", {}).get("count", 0)),
        ("Generated pages", kb.get("generated", {}).get("count", 0)),
        ("Entities", graph_counts.get("entities", 0)),
        ("Relations", graph_counts.get("relations", 0)),
        ("Failed", counts["failed"]),
    ]
    cells = "".join(
        f'<div class="tile"><div class="tile-n">{v}</div>'
        f'<div class="tile-l">{_esc(label)}</div></div>'
        for label, v in tiles
    )
    return f'<div class="tiles">{cells}</div>'


def _capability_map(caps: list[dict]) -> str:
    rows = ""
    for c in caps:
        ok = c["status"] == "ok"
        dot = "●" if ok else "○"
        cls = "ok" if ok else "na"
        rows += (f'<li class="{cls}"><span class="dot">{dot}</span>'
                 f'<span class="cap-name">{_esc(c["name"])}</span>'
                 f'<span class="cap-detail">{_esc(c["detail"])}</span></li>')
    return f'<ul class="caps">{rows}</ul>'


def _tree(pages: list[dict]) -> str:
    paths = sorted(p["path"] for p in pages)
    title_by = {p["path"]: p.get("title", p["path"]) for p in pages}
    items = ""
    for path in paths:
        depth = path.count("/")
        pad = 16 + depth * 20
        items += (f'<li style="padding-left:{pad}px">'
                  f'<span class="tree-t">{_esc(title_by.get(path, path))}</span>'
                  f'<span class="tree-p">{_esc(path)}</span></li>')
    return f'<ul class="tree">{items}</ul>' if items else '<p class="muted">No pages.</p>'


def _short(s: str, n: int = 26) -> str:
    s = str(s)
    return s if len(s) <= n else s[: n - 1] + "…"


def _graph_svg(snapshot: dict, max_nodes: int = 26, max_edges: int = 32) -> str:
    """A CONNECTED sample of the graph: the most-central entities and the relations
    among them. A real corpus has thousands of entities, most of them peripheral —
    drawing an arbitrary slice shows disconnected dots, so we rank by degree and grow a
    connected subgraph from the highest-degree relations."""
    import math
    from collections import Counter

    all_entities = snapshot.get("entities", [])
    all_relations = snapshot.get("relations", [])
    if not all_entities:
        return ('<p class="muted">No entities in the graph yet — start the service with '
                '<code>EXTRACTION_ON_INGEST=true</code> and an extraction model to populate '
                'the knowledge graph.</p>')

    ent_by_name = {e["name"]: e for e in all_entities}
    # degree over relations whose endpoints are both real entities
    deg: Counter = Counter()
    valid_rels = []
    for r in all_relations:
        s, o = r.get("subject"), r.get("object")
        if s in ent_by_name and o in ent_by_name and s != o:
            deg[s] += 1
            deg[o] += 1
            valid_rels.append(r)

    # Grow a connected subgraph from the most central relations.
    valid_rels.sort(key=lambda r: deg[r["subject"]] + deg[r["object"]], reverse=True)
    chosen_names: set[str] = set()
    chosen_rels: list[dict] = []
    for r in valid_rels:
        if len(chosen_rels) >= max_edges:
            break
        pair = {r["subject"], r["object"]}
        if chosen_names and len(chosen_names | pair) > max_nodes:
            continue
        chosen_names |= pair
        chosen_rels.append(r)

    if not chosen_rels:
        # No relations connect any entities — fall back to the top entities by page count.
        top = sorted(all_entities, key=lambda e: len(e.get("pages", [])), reverse=True)
        entities = top[:max_nodes]
        note = (f'<p class="muted small">No connected relations to draw; showing the '
                f'{len(entities)} entities mentioned on the most pages.</p>')
    else:
        entities = [ent_by_name[n] for n in chosen_names]
        note = (f'<p class="muted small">Showing the {len(entities)} most-connected of '
                f'{len(all_entities):,} entities and {len(chosen_rels)} of '
                f'{len(all_relations):,} relations. Hover a node or edge for detail.</p>')

    types = []
    for e in entities:
        if e["type"] not in types:
            types.append(e["type"])
    color = {t: (_PALETTE[i] if i < len(_PALETTE) else _OTHER) for i, t in enumerate(types)}

    W, H, cx, cy = 760, 520, 380, 260
    R = 200
    n = len(entities)
    pos = {}
    for i, e in enumerate(entities):
        ang = -math.pi / 2 + 2 * math.pi * i / max(n, 1)
        pos[e["name"]] = (cx + R * math.cos(ang), cy + R * math.sin(ang))

    edges = ""
    for r in chosen_rels:
        x1, y1 = pos[r["subject"]]
        x2, y2 = pos[r["object"]]
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        edges += (f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" '
                  f'class="edge" marker-end="url(#arrow)"><title>{_esc(r["subject"])} '
                  f'{_esc(r["predicate"])} {_esc(r["object"])}</title></line>'
                  f'<text x="{mx:.0f}" y="{my:.0f}" class="edge-l">'
                  f'{_esc(_short(r["predicate"], 18))}</text>')
    nodes = ""
    for e in entities:
        x, y = pos[e["name"]]
        anchor = "start" if x >= cx else "end"
        dx = 12 if x >= cx else -12
        nodes += (f'<circle cx="{x:.0f}" cy="{y:.0f}" r="7" fill="{color[e["type"]]}" '
                  f'class="node"><title>{_esc(e["name"])} ({_esc(e["type"])}) — '
                  f'{len(e.get("pages", []))} page(s), degree {deg[e["name"]]}</title></circle>'
                  f'<text x="{x + dx:.0f}" y="{y + 4:.0f}" text-anchor="{anchor}" '
                  f'class="node-l">{_esc(_short(e["name"], 24))}</text>')
    legend = "".join(
        f'<span class="lg"><span class="sw" style="background:{color[t]}"></span>'
        f'{_esc(t)}</span>' for t in types
    )
    return (f'{note}<div class="legend">{legend}</div>'
            f'<svg viewBox="0 0 {W} {H}" class="graph" role="img" '
            f'aria-label="Knowledge graph of entities and relations">'
            f'<defs><marker id="arrow" viewBox="0 0 10 10" refX="16" refY="5" '
            f'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" class="arrow"/></marker></defs>'
            f'{edges}{nodes}</svg>')


def _evidence_table(units: list[dict]) -> str:
    if not units:
        return '<p class="muted">No evidence returned.</p>'
    rows = ""
    for u in units:
        prov = u.get("provenance") or {}
        rows += (
            f'<tr><td class="num">{u.get("score", "")}</td>'
            f'<td><span class="pill">{_esc(u.get("type", ""))}</span></td>'
            f'<td>{_esc(u.get("title", ""))}</td>'
            f'<td class="mono">{_esc(u.get("path", ""))}</td>'
            f'<td class="mono">{_esc(prov.get("locator", ""))}</td>'
            f'<td>{_esc((u.get("content", "") or "")[:160])}</td></tr>'
        )
    return (
        '<table class="tbl"><thead><tr><th>score</th><th>type</th><th>title</th>'
        '<th>path</th><th>locator</th><th>snippet</th></tr></thead>'
        f'<tbody>{rows}</tbody></table>'
    )


def _qa_section(sweep: dict, question: str) -> str:
    parts = [f'<h2>Question &rarr; Answer</h2><p class="q">{_esc(question)}</p>']
    parts.append('<h3>Evidence (hybrid retrieval)</h3>')
    parts.append(_evidence_table(sweep.get("evidence", [])))

    exp = sweep.get("graph_expand", {})
    if exp.get("units"):
        parts.append(f'<h3>Related via the graph (seed: <code>{_esc(exp.get("seed"))}</code>)</h3>')
        parts.append(_evidence_table(exp["units"]))

    reason = sweep.get("reason") or {}
    if reason:
        parts.append('<h3>Reasoning over the knowledge graph</h3>')
        parts.append(f'<p class="mono small">rule: {_esc(reason.get("rule", ""))}</p>')
        parts.append(f'<p><b>{_esc(reason.get("answer", "(no answer)"))}</b></p>')
        for t in reason.get("rule_trace", [])[:6]:
            parts.append(f'<p class="trace">{_esc(t)}</p>')

    dec, chain = sweep.get("decision") or {}, sweep.get("chain") or {}
    if dec:
        parts.append('<h3>Provenance &amp; lineage</h3>')
        parts.append(
            f'<p>Decision <code>{_esc(dec.get("decision_id"))}</code> recorded '
            f'(backend <b>{_esc(dec.get("backend"))}</b>); chain verified: '
            f'<b>{_esc(chain.get("verified"))}</b>.</p>')
        if chain.get("prov_o"):
            parts.append('<details><summary>PROV-O (W3C provenance, Turtle)</summary>'
                         f'<pre class="prov">{_esc(chain["prov_o"][:1600])}</pre></details>')

    val = sweep.get("validate") or {}
    if val:
        good = val.get("conforming", {})
        bad = val.get("violating", {})
        parts.append('<h3>SHACL policy gate</h3>')
        parts.append(
            f'<p>Conforming entity: <b>{_esc(good.get("conforms"))}</b>. '
            f'Violating entity: <b>{_esc(bad.get("conforms"))}</b> '
            f'({len(bad.get("violations", []))} violation(s): '
            f'{_esc("; ".join(v.get("message", "") for v in bad.get("violations", [])))}).</p>')
    return "\n".join(parts)


_CSS = """
:root{--bg:#f4f4f2;--surface:#fcfcfb;--line:#e3e2dd;--text:#0b0b0b;--muted:#6b6a66;
--accent:#2a78d6;--pill:#eef3fb;--pillink:#1c5fb0;--edge:#cfcec8;--codebg:#f0efe9;}
@media(prefers-color-scheme:dark){:root{--bg:#141413;--surface:#1c1c1a;--line:#33322e;
--text:#f4f4f2;--muted:#a6a59d;--accent:#3987e5;--pill:#1e2a3c;--pillink:#8fc0ff;
--edge:#45443f;--codebg:#26251f;}}
*{box-sizing:border-box}body{margin:0}
.wrap{max-width:1040px;margin:0 auto;padding:32px 20px 80px;color:var(--text)}
h1{font-size:26px;margin:0 0 4px}h2{font-size:19px;margin:34px 0 10px;
border-bottom:1px solid var(--line);padding-bottom:6px}h3{font-size:15px;margin:20px 0 8px}
.sub{color:var(--muted);margin:0 0 4px}.muted{color:var(--muted)}.small{font-size:12px}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin:14px 0}
.tile{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px}
.tile-n{font-size:26px;font-weight:650}.tile-l{color:var(--muted);font-size:12px;margin-top:2px}
.caps{list-style:none;padding:0;margin:8px 0}
.caps li{display:grid;grid-template-columns:18px 260px 1fr;gap:8px;align-items:baseline;
padding:7px 0;border-bottom:1px solid var(--line)}
.caps .dot{font-size:12px}.caps .ok .dot,.caps li.ok .dot{color:#1baf7a}
.caps li.na .dot{color:var(--muted)}.cap-name{font-weight:600}.cap-detail{color:var(--muted);font-size:13px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px;margin:12px 0}
.tree{list-style:none;padding:0;margin:0}
.tree li{padding:4px 0;border-bottom:1px solid var(--line);display:flex;gap:12px;align-items:baseline}
.tree-t{font-weight:600}.tree-p{color:var(--muted);font-size:12px;font-family:ui-monospace,monospace}
.graph{width:100%;height:auto;background:var(--surface);border:1px solid var(--line);border-radius:12px}
.node{stroke:var(--surface);stroke-width:2}.node-l{font-size:11px;fill:var(--text)}
.edge{stroke:var(--edge);stroke-width:1.5}.edge-l{font-size:9px;fill:var(--muted)}
.arrow{fill:var(--edge)}
.legend{margin:6px 0}.lg{display:inline-flex;align-items:center;gap:5px;margin-right:14px;font-size:12px;color:var(--muted)}
.sw{width:11px;height:11px;border-radius:3px;display:inline-block}
.tbl{width:100%;border-collapse:collapse;font-size:13px}
.tbl th{text-align:left;color:var(--muted);font-weight:600;border-bottom:2px solid var(--line);padding:6px 8px}
.tbl td{border-bottom:1px solid var(--line);padding:6px 8px;vertical-align:top}
.tbl .num{font-variant-numeric:tabular-nums}
.pill{background:var(--pill);color:var(--pillink);border-radius:20px;padding:2px 9px;font-size:11px;font-weight:600}
.q{font-size:17px;font-weight:600;background:var(--pill);padding:10px 14px;border-radius:10px}
.trace{color:var(--muted);font-size:13px;margin:3px 0;padding-left:10px;border-left:2px solid var(--line)}
pre{background:var(--codebg);border-radius:8px;padding:12px;overflow:auto;font-size:12px}
code{background:var(--codebg);padding:1px 5px;border-radius:4px;font-size:12px}
details summary{cursor:pointer;color:var(--accent);font-size:13px;margin:6px 0}
.foot{color:var(--muted);font-size:12px;margin-top:40px;border-top:1px solid var(--line);padding-top:12px}
"""


def render_html(report: dict) -> str:
    m = report["meta"]
    ing = report["ingest"]
    snap = report["graph"]
    sweep = report["sweep"]
    skipped = ing["counts"].get("skipped")
    corpus_desc = ("querying previously ingested data" if skipped else
                   f'{_esc(ing["counts"]["md"])} md + {_esc(ing["counts"]["pdf"])} pdf '
                   f'from <code>{_esc(m["source"])}</code>')
    body = [
        '<div class="wrap">',
        '<h1>semantic-fabric — capability run</h1>',
        f'<p class="sub">{corpus_desc} &middot; '
        f'generated {_esc(m["generated_at"])} &middot; contract '
        f'{_esc(m.get("contract_version", "?"))}</p>',

        '<h2>What the platform did</h2>',
        _capability_map(sweep["capabilities"]),

        '<h2>' + ('Data in the platform' if skipped else 'Corpus ingested') + '</h2>',
        _stat_tiles(ing["counts"], snap.get("counts", {}), report["kb"]),
        '<div class="card"><h3>Knowledge base hierarchy</h3>'
        + _tree(snap.get("pages", [])) + '</div>',

        '<h2>Knowledge graph</h2>',
        '<div class="card">' + _graph_svg(snap) + '</div>',

        _qa_section(sweep, m["question"]),

        f'<p class="foot">Generated by <code>demo/run_demo.py</code> against '
        f'{_esc(m["fabric_url"])}. Full data in <code>report.json</code>. '
        f'This report reflects whichever backends the service was started with — see '
        f'demo/RUNBOOK.md.</p>',
        '</div>',
    ]
    return (f'<!doctype html><html><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>semantic-fabric capability run</title><style>{_CSS}</style></head>'
            f'<body>{"".join(body)}</body></html>')


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="semantic-fabric end-to-end demo")
    ap.add_argument("--source", default="demo/sample_corpus", help="directory of .md/.pdf")
    ap.add_argument("--question", default="Is a Cash ISA tax-free, and who offers it?")
    ap.add_argument("--url", default=os.getenv("FABRIC_URL", "http://localhost:8080"))
    ap.add_argument("--out", default="demo/out")
    ap.add_argument("--seed", default=None, help="graph-expand seed (default: top hit)")
    ap.add_argument("--batch-size", type=int, default=25,
                    help="markdown pages per /ingest request (smaller = more resilient "
                         "when extraction-on-ingest is enabled)")
    ap.add_argument("--timeout", type=int, default=600,
                    help="per-request timeout in seconds (raise for slow LLM ingest)")
    ap.add_argument("--make-sample-pdf", action="store_true",
                    help="synthesize a small PDF into the corpus (needs PyMuPDF)")
    ap.add_argument("--no-ingest", action="store_true",
                    help="skip ingestion and ask against data already loaded in the "
                         "service (query previously ingested data)")
    args = ap.parse_args(argv)

    global _TIMEOUT
    _TIMEOUT = args.timeout
    base = args.url.rstrip("/")
    source = Path(args.source)
    if not args.no_ingest and not source.is_dir():
        print(f"error: source dir not found: {source}\n"
              f"(or pass --no-ingest to query data already loaded in the service)",
              file=sys.stderr)
        return 2

    try:
        health = get(base, "/health")
    except Exception as e:
        print(f"error: could not GET {base}/health — {e}\n"
              f"If curl works but this doesn't, a proxy env var is likely intercepting "
              f"localhost; the driver already bypasses proxies, but you can also set "
              f"NO_PROXY=localhost,127.0.0.1. Otherwise start the service:  "
              f"uvicorn api.main:app --port 8080", file=sys.stderr)
        return 2

    if args.no_ingest:
        print("== skipping ingestion — querying data already loaded in the service ==")
        ingest_report = {"files": [], "counts": {"md": 0, "pdf": 0, "failed": 0,
                                                  "skipped": True}}
    else:
        if args.make_sample_pdf:
            maybe_make_sample_pdf(source)
        print(f"== discovering {source} ==")
        md_pages, pdf_docs = discover(source)
        print(f"   {len(md_pages)} markdown, {len(pdf_docs)} pdf")

        print(f"== ingesting (batch size {args.batch_size}, timeout {args.timeout}s) ==")
        ingest_report = ingest(base, md_pages, pdf_docs, batch_size=args.batch_size)
        c = ingest_report["counts"]
        print(f"   done: {c['md']} md + {c['pdf']} pdf, {c['failed']} failed, "
              f"{c.get('elapsed_s', 0)}s")
        if c["failed"]:
            for f in ingest_report["files"]:
                if f["status"] != "ok":
                    print(f"   [failed] {f['kind']:8} {f['path']}: {f['detail']}")

    snapshot = get(base, "/graph")
    kb = {"authored": get(base, "/kb/authored/tree"),
          "generated": get(base, "/kb/generated/tree")}

    print("== capability sweep ==")
    sweep = capability_sweep(base, args.question, snapshot, args.seed)
    for c in sweep["capabilities"]:
        print(f"   [{c['status']:3}] {c['name']}: {c['detail']}")

    report = {
        "meta": {"source": str(source), "fabric_url": base, "question": args.question,
                 "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                 "contract_version": health.get("contract_version")},
        "ingest": ingest_report, "graph": snapshot, "kb": kb, "sweep": sweep,
    }

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out / "report.html").write_text(render_html(report), encoding="utf-8")
    print(f"\nWrote {out/'report.html'} and {out/'report.json'}")
    print("Open the HTML report in a browser to explore the run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
