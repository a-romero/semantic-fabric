#!/usr/bin/env python
"""Build docs/guide.html — a self-contained, offline guide to semantic-fabric.

Aimed at three audiences at once: business/decision-makers ("is this the right
platform?"), technical evaluators ("how does it work, in detail?"), and new users
("how do I get started?"). Regenerate after content or diagram changes:

    python scripts/build_guide.py
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIAGRAMS = ROOT / "docs" / "diagrams"


def svg(name: str) -> str:
    raw = (DIAGRAMS / name).read_text(encoding="utf-8")
    raw = re.sub(r"^<\?xml.*?\?>\s*", "", raw, flags=re.DOTALL)  # drop XML prolog
    raw = re.sub(r"<!DOCTYPE.*?>\s*", "", raw, flags=re.DOTALL)
    return f'<div class="fig">{raw}</div>'


CSS = """
:root{
  --bg:#f5f5f3; --surface:#fff; --surface-2:#faf9f6; --line:#e4e3de;
  --ink:#111110; --muted:#6b6a64; --faint:#93928a;
  --accent:#2a78d6; --accent-ink:#1c5fb0; --pill:#eef3fb; --pill-ink:#1c5fb0;
  --good:#1baf7a; --warn:#eda100; --bad:#e34948; --code:#f0efe9;
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#131312; --surface:#1c1c1a; --surface-2:#232320; --line:#33322d;
  --ink:#f3f3f0; --muted:#a8a79e; --faint:#807f77;
  --accent:#3987e5; --accent-ink:#8fc0ff; --pill:#1e2a3c; --pill-ink:#8fc0ff;
  --good:#3bcf97; --warn:#eda100; --bad:#e66767; --code:#26251f;
}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  -webkit-font-smoothing:antialiased}
a{color:var(--accent-ink);text-decoration:none}a:hover{text-decoration:underline}
code{background:var(--code);padding:1.5px 6px;border-radius:5px;
  font:13px ui-monospace,SFMono-Regular,Menlo,monospace}
pre{background:var(--code);border-radius:10px;padding:14px 16px;overflow:auto;
  font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}
pre code{background:none;padding:0}

.layout{display:grid;grid-template-columns:250px minmax(0,1fr);gap:0;max-width:1180px;margin:0 auto}
nav.toc{position:sticky;top:0;align-self:start;height:100vh;overflow:auto;padding:26px 14px 40px;
  border-right:1px solid var(--line)}
nav.toc .brand{font-weight:700;font-size:15px;letter-spacing:.2px;margin:0 0 2px}
nav.toc .tag{color:var(--muted);font-size:12px;margin:0 0 18px}
nav.toc a{display:block;color:var(--muted);font-size:13.5px;padding:5px 10px;border-radius:7px;
  border-left:2px solid transparent}
nav.toc a:hover{background:var(--surface);color:var(--ink);text-decoration:none}
nav.toc .grp{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--faint);
  margin:16px 10px 4px}
main{padding:40px 44px 120px;min-width:0}
.hero h1{font-size:34px;line-height:1.15;margin:.1em 0 .15em}
.hero .lede{font-size:18px;color:var(--muted);max-width:60ch;margin:0 0 18px}
.badges{display:flex;flex-wrap:wrap;gap:8px;margin:6px 0 8px}
.badge{background:var(--pill);color:var(--pill-ink);border-radius:20px;padding:3px 11px;
  font-size:12px;font-weight:600}
h2{font-size:24px;margin:52px 0 8px;padding-top:12px;border-top:1px solid var(--line)}
h2:first-of-type{border-top:none}
h3{font-size:17px;margin:26px 0 6px}
p{max-width:72ch}
.section-lede{color:var(--muted);max-width:72ch}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px;margin:16px 0}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px 18px}
.card h4{margin:0 0 6px;font-size:15px}
.card p{margin:0;font-size:14px;color:var(--muted);max-width:none}
.k{color:var(--accent-ink);font-weight:600}
.fig{background:#fff;border:1px solid var(--line);border-radius:12px;padding:18px;margin:16px 0;
  overflow:auto;text-align:center}
.fig svg{max-width:100%;height:auto}
.figcap{color:var(--muted);font-size:13px;margin:-6px 0 20px;text-align:center}
table{border-collapse:collapse;width:100%;margin:14px 0;font-size:14px;display:block;overflow-x:auto}
th,td{border-bottom:1px solid var(--line);padding:9px 12px;text-align:left;vertical-align:top}
th{color:var(--muted);font-weight:600;white-space:nowrap}
.callout{border:1px solid var(--line);border-left:4px solid var(--accent);background:var(--surface);
  border-radius:10px;padding:12px 16px;margin:16px 0}
.callout.good{border-left-color:var(--good)} .callout.warn{border-left-color:var(--warn)}
.callout p{margin:.3em 0;max-width:none}
.callout .t{font-weight:700;font-size:13px;text-transform:uppercase;letter-spacing:.05em;
  color:var(--muted);margin-bottom:2px}
ul.checks{list-style:none;padding:0}ul.checks li{padding:5px 0 5px 26px;position:relative;max-width:72ch}
ul.checks li::before{content:"✓";position:absolute;left:0;color:var(--good);font-weight:700}
ul.crosses li::before{content:"→";color:var(--accent)}
.foot{margin:60px 0 0;padding-top:16px;border-top:1px solid var(--line);color:var(--muted);font-size:13px}
.pilltype{background:var(--pill);color:var(--pill-ink);border-radius:6px;padding:1px 7px;
  font-size:12px;font-weight:600}
@media (max-width:820px){
  .layout{grid-template-columns:1fr}
  nav.toc{position:static;height:auto;border-right:none;border-bottom:1px solid var(--line)}
  nav.toc a{display:inline-block}
  main{padding:24px 18px 80px}
  .hero h1{font-size:27px}
}
"""

# (nav group, [(anchor, title)])
TOC = [
    ("Understand", [
        ("overview", "What it is"),
        ("why", "Why it exists"),
        ("concepts", "Core concepts"),
    ]),
    ("How it works", [
        ("integration", "How consumers integrate"),
        ("architecture", "Architecture & components"),
        ("flow", "End-to-end flow"),
        ("principles", "Design principles"),
    ]),
    ("Use it", [
        ("capabilities", "Capability reference"),
        ("getting-started", "Getting started"),
    ]),
    ("Decide", [
        ("decision", "Is this right for us?"),
        ("faq", "FAQ"),
        ("refs", "Further reading"),
    ]),
]


def toc_html() -> str:
    out = ['<nav class="toc"><p class="brand">semantic-fabric</p>'
           '<p class="tag">Platform guide</p>']
    for grp, items in TOC:
        out.append(f'<div class="grp">{grp}</div>')
        for anchor, title in items:
            out.append(f'<a href="#{anchor}">{title}</a>')
    out.append('</nav>')
    return "".join(out)


def card(title: str, body: str) -> str:
    return f'<div class="card"><h4>{title}</h4><p>{body}</p></div>'


# ---------------------------------------------------------------------------
# content
# ---------------------------------------------------------------------------

BODY = f"""
<section class="hero">
  <h1>The enterprise knowledge, context &amp; semantic layer</h1>
  <p class="lede">semantic-fabric turns a pile of documents — curated Markdown and dense
  PDFs alike — into one <span class="k">auditable knowledge graph</span> that agents and
  applications query for evidence, reasoning, and provenance, over REST and MCP.</p>
  <div class="badges">
    <span class="badge">Retrieval + GraphRAG</span>
    <span class="badge">LLM extraction</span>
    <span class="badge">Deterministic reasoning</span>
    <span class="badge">Provenance &amp; lineage</span>
    <span class="badge">Policy gate (SHACL)</span>
    <span class="badge">Runs on defaults · scales with real backends</span>
    <span class="badge">Durable across restarts</span>
  </div>
  <p class="section-lede">This guide is for three readers: leaders deciding whether the
  platform fits the business, engineers evaluating how it works, and new users getting
  started. Read top-to-bottom, or jump to <a href="#decision">Is this right for us?</a></p>
</section>

<h2 id="overview">What it is</h2>
<p>Most organisations already have the knowledge to answer their own questions — it's just
scattered across policy documents, product pages, PDFs and wikis, in formats a machine
can't reason over. <strong>semantic-fabric is the layer that makes that knowledge
machine-usable</strong>: it ingests the documents, builds a structured knowledge graph
from them, and serves precise, <em>cited</em>, <em>policy-checked</em> answers to any
agent or app that asks.</p>
<p>It is the machine-scale half of a two-part design. A lightweight front-end (for example
<a href="https://github.com/a-romero/skilled-agent">skilled-agent</a>, or any MCP-capable
agent or IDE) stays simple and talks to this service through one small contract. The heavy
lifting — parsing, embedding, graph building, reasoning, provenance — lives here, behind a
stable boundary, so it can evolve without touching every consumer.</p>
<div class="grid">
  {card("For the business", "One governed knowledge layer many teams and agents share — with answers that cite their sources and pass policy checks before they're returned.")}
  {card("For engineers", "A clean REST + MCP service; every capability has a dependency-free default and an opt-in production backend, selected by an environment variable.")}
  {card("For users", "Point it at a folder of PDFs/Markdown, ask a question, get ranked evidence with exact provenance — plus a visual report of everything it did.")}
</div>

<h2 id="why">Why it exists</h2>
<p class="section-lede">Plain document search and naive RAG (retrieval-augmented
generation) fall short in the enterprise on four fronts. semantic-fabric is built around
fixing each one.</p>
<table>
<thead><tr><th>The gap</th><th>What goes wrong</th><th>How the platform closes it</th></tr></thead>
<tbody>
<tr><td><strong>Dense, mixed formats</strong></td><td>Keyword search misses meaning; PDFs bury the answer in tables and charts.</td><td>Hybrid semantic + keyword retrieval, plus a real PDF layout parser (text, tables, figures) and vision captioning.</td></tr>
<tr><td><strong>Disconnected facts</strong></td><td>Search returns passages, not the relationships between things (who offers what, what excludes what).</td><td>An LLM builds a <span class="k">knowledge graph</span> at ingest; GraphRAG traverses it to pull in related material search alone would miss.</td></tr>
<tr><td><strong>Trust &amp; audit</strong></td><td>"The AI said so" is not acceptable for a regulated decision.</td><td>Every answer can be recorded as a <span class="k">decision</span> with W3C PROV-O lineage and a tamper-evident chain — "why did we conclude this, from what?".</td></tr>
<tr><td><strong>Correctness &amp; policy</strong></td><td>LLMs improvise; business rules must hold deterministically.</td><td>A deterministic layer: rule-based reasoning with an explanation trace, and a SHACL policy gate an answer must pass before it leaves the platform.</td></tr>
</tbody>
</table>
<div class="callout"><p class="t">The one-line thesis</p><p><strong>The LLM proposes; the
deterministic layer disposes.</strong> Language models are used where they shine
(extraction, phrasing) and fenced by graph, rules, provenance and policy where correctness
and auditability matter.</p></div>

<h2 id="concepts">Core concepts</h2>
<p class="section-lede">The vocabulary you'll see throughout the platform and this guide.</p>
<div class="grid">
  {card("Context / knowledge graph", "The structured heart of the platform: pages, extracted <b>entities</b> (products, orgs, terms) and <b>relations</b> (offers, excludes, is-a), plus the document hierarchy. Stored as RDF triples, queryable with SPARQL.")}
  {card("EvidenceUnit", "The single wire contract every answer is made of: <code>content, type, score, provenance, entities</code> (+ a legacy <code>path/title/summary</code>). One shape, so every consumer sees identical results.")}
  {card("Hybrid retrieval", "Two searches fused: <b>vector</b> (semantic similarity via embeddings) and <b>BM25</b> (keyword), combined with Reciprocal Rank Fusion — robust without tuning score scales.")}
  {card("GraphRAG", "Retrieval that follows the graph. From a starting page or entity it walks hierarchy, shared topics, shared entities and relations to surface connected evidence.")}
  {card("LLM extraction", "At ingest, a language model reads each page and returns typed entities and relations, validated against a schema. This is what turns prose into the graph.")}
  {card("Deterministic reasoning", "Rule-based (Datalog) inference over the graph's facts, returning a yes/no answer <b>with a proof trace</b> — repeatable and explainable, unlike an LLM guess.")}
  {card("Provenance &amp; lineage", "Decisions recorded as W3C <b>PROV-O</b> with a tamper-evident hash chain; <code>/decisions/&#123;id&#125;/chain</code> traces an answer back through its evidence to source.")}
  {card("SHACL policy gate", "A declarative check (required fields, min values, allowed values) that entity data must satisfy before an answer is released — the deterministic guardrail.")}
  {card("REST + MCP", "The same capabilities exposed two ways: plain HTTP for apps, and the Model Context Protocol for agents/IDEs (Claude Code, Cursor, …). No behaviour drift between them.")}
  {card("Pluggable backends", "Every capability has a dependency-free default and an optional production backend, chosen by an env var — so it runs anywhere and scales when you're ready.")}
  {card("Two KB namespaces", "<b>authored/</b> — human-curated Markdown, ingested but never overwritten. <b>generated/</b> — machine-produced summaries (e.g. PDF summary trees), a read-view of the semantic plane.")}
  {card("Durability", "With a SQLite sidecar and the RDF graph store enabled, the whole state — index, KB, graph, decision lineage — survives a restart; ask again with no re-ingest.")}
</div>

<h2 id="integration">How consumers integrate</h2>
<p class="section-lede">Front-ends stay lean. They speak to one service through one
contract, and fall back to their own local search if the service is unreachable — so
adopting the platform is an upgrade, never a hard dependency.</p>
{svg("integration.svg")}
<p class="figcap">Consumers → the <code>fabric-client</code> contract → REST/MCP → pluggable backends.</p>
<ul class="checks">
<li><strong>skilled-agent</strong> and other apps call over HTTP via the tiny
<code>fabric-client</code> package.</li>
<li><strong>Agents &amp; IDEs</strong> (Claude Code, Cursor, other MCP clients) use the
identical capabilities as MCP tools.</li>
<li><strong>Batch jobs</strong> (the demo driver, CI, scheduled ingests) push sources in
the same way.</li>
<li>Everyone exchanges the same <span class="k">EvidenceUnit</span>, so results are
consistent across every channel.</li>
</ul>

<h2 id="architecture">Architecture &amp; components</h2>
<p class="section-lede">Each capability sits behind an interface with a
<b>dependency-free default</b> and an <b>optional real backend</b>. Continuous
integration runs the defaults; the production backends are validated on a capable host.
This is why the platform installs and runs in seconds, yet scales to real infrastructure
without code changes.</p>
{svg("components.svg")}
<p class="figcap">Every module: its default backend and the production option it swaps in.</p>
<table>
<thead><tr><th>Component</th><th>What it does</th><th>Default</th><th>Production option</th></tr></thead>
<tbody>
<tr><td><strong>Ingestion</strong></td><td>Reads Markdown and PDFs (per-page text, tables, figures); captions figures.</td><td>Markdown + pre-parsed input</td><td>PyMuPDF layout parser · LiteLLM vision captions</td></tr>
<tr><td><strong>Extraction</strong></td><td>Turns page text into typed entities + relations (the graph).</td><td>off (no-op)</td><td>LiteLLM — any provider by model string</td></tr>
<tr><td><strong>Retrieval</strong></td><td>Hybrid vector + BM25 search, RRF-fused, with provenance.</td><td>in-memory + hashing embedder</td><td>Qdrant vector store · BGE-M3 embeddings</td></tr>
<tr><td><strong>Graph</strong></td><td>The knowledge graph + GraphRAG traversal; SPARQL-queryable.</td><td>in-memory</td><td>Oxigraph (persistent RDF, SPARQL)</td></tr>
<tr><td><strong>Reasoning</strong></td><td>Deterministic inference over facts / the graph, with a trace.</td><td>forward-chainer</td><td>semantica Datalog</td></tr>
<tr><td><strong>Provenance</strong></td><td>Records decisions + transitive lineage.</td><td>in-memory hash chain</td><td>semantica W3C PROV-O</td></tr>
<tr><td><strong>Ontology / policy</strong></td><td>Validates entity data against declared constraints.</td><td>simple constraints</td><td>pyshacl (SHACL)</td></tr>
<tr><td><strong>Knowledge base</strong></td><td>Serves authored + generated Markdown pages.</td><td>in-memory</td><td>SQLite sidecar (durable)</td></tr>
<tr><td><strong>Persistence</strong></td><td>Keeps index/KB/lineage across restarts.</td><td>process memory</td><td>SQLite (<code>FABRIC_DB</code>) + RDF store</td></tr>
</tbody>
</table>

<h2 id="flow">End-to-end flow</h2>
<p class="section-lede">Two phases: ingest a corpus once, then ask questions
repeatedly (including after a restart). Extraction during ingest runs concurrently for
throughput; graph writes are applied in order so results are deterministic.</p>
{svg("flow.svg")}
<p class="figcap">Ingest (parse · chunk · embed · extract · graph · persist) then ask
(retrieve · reason · record · gate).</p>
<h3>What happens on ingest</h3>
<p>Each document is parsed (PDFs into text/tables/figures), split into chunks, embedded,
and — if extraction is enabled — read by an LLM that returns typed entities and relations.
Those become graph edges; the document hierarchy and shared topics become edges too. Chunks
(with their vectors), KB pages and the graph are persisted so nothing needs re-doing later.</p>
<h3>What happens on a question</h3>
<p>Hybrid retrieval returns ranked <span class="k">EvidenceUnits</span>, each with the exact
locator (page/section, or PDF page + bounding box). GraphRAG can expand from the top hit to
related material. Reasoning can run business rules over the graph's own facts and return a
proof trace. The answer can be recorded as a decision with full PROV-O lineage, and checked
against SHACL policy before it's released.</p>

<h2 id="principles">Design principles</h2>
<div class="grid">
  {card("Contract-first boundary", "One versioned wire contract (EvidenceUnit) separates consumers from the engine, so the platform can change internally without breaking anyone.")}
  {card("Defaults that just run", "Every layer has a pure-Python default — no services, no credentials — so evaluation and CI are instant. Production backends are opt-in, not prerequisites.")}
  {card("LLM proposes, logic disposes", "Language models do extraction and phrasing; graph, rules, provenance and SHACL enforce correctness and auditability deterministically.")}
  {card("One semantic substrate", "The graph adheres to the W3C stack — RDF + SPARQL, with PROV-O provenance and SHACL — so knowledge, reasoning and audit share one queryable plane.")}
  {card("Provider-agnostic AI", "Extraction and captioning go through a gateway (LiteLLM); the model is a config string — Anthropic, OpenAI, a local model, or your own enterprise gateway.")}
  {card("Durable &amp; auditable", "Turn on persistence and the full state survives restarts; every consequential answer can carry a tamper-evident lineage back to source.")}
</div>

<h2 id="capabilities">Capability reference</h2>
<p class="section-lede">The same capabilities are available over REST and as MCP tools.</p>
<table>
<thead><tr><th>Capability</th><th>REST</th><th>MCP tool</th><th>Returns</th></tr></thead>
<tbody>
<tr><td>Hybrid retrieval</td><td><code>POST /search</code></td><td><code>search</code></td><td>ranked EvidenceUnits + provenance</td></tr>
<tr><td>Graph expansion</td><td><code>POST /graph/expand</code></td><td><code>graph_query</code></td><td>related pages via the graph</td></tr>
<tr><td>Whole-graph snapshot</td><td><code>GET /graph</code></td><td>—</td><td>entities + relations (for inspection/viz)</td></tr>
<tr><td>Ingestion</td><td><code>POST /ingest</code></td><td><code>ingest</code></td><td>job status + counts</td></tr>
<tr><td>LLM extraction</td><td><code>POST /extract</code></td><td><code>extract</code></td><td>typed entities + relations</td></tr>
<tr><td>Reasoning (+ over the graph)</td><td><code>POST /reason</code></td><td><code>reason</code></td><td>answer + rule trace</td></tr>
<tr><td>Decisions &amp; lineage</td><td><code>POST /decisions</code>, <code>GET /decisions/{{id}}/chain</code></td><td>—</td><td>decision id · PROV-O lineage</td></tr>
<tr><td>Policy gate</td><td><code>POST /validate</code></td><td>—</td><td>conforms + violations</td></tr>
<tr><td>Read / browse KB</td><td><code>GET /kb/{{ns}}/{{path}}</code>, <code>/kb/{{ns}}/tree</code></td><td><code>read_page</code></td><td>Markdown pages</td></tr>
</tbody>
</table>

<h2 id="getting-started">Getting started</h2>
<h3>Run it in two minutes (defaults, no credentials)</h3>
<pre><code>make install          # the client + dev deps
make run              # start the service on :8080  (terminal A)

# in terminal B — ingest a sample corpus and ask a question:
python demo/run_demo.py --source demo/sample_corpus \\
  --question "Is a Cash ISA tax-free, and who offers it?"
open demo/out/report.html</code></pre>
<p>The demo ingests a folder of Markdown/PDF, exercises every capability against your
question, and writes a self-contained visual report (corpus stats, the knowledge-graph
diagram, and the question → answer panel with evidence, reasoning, lineage and the policy
result).</p>

<h3>The full experience (real backends)</h3>
<p>Install the extras you want and set the selectors — each falls back to the default if
unavailable. A durable, LLM-powered configuration:</p>
<pre><code>pip install -e ".[prod,semantica,llm,pdf,graph]"

export EMBEDDING_MODEL=BAAI/bge-m3                 # real embeddings
export EXTRACTION_BACKEND=llm EXTRACTION_ON_INGEST=true
export EXTRACTION_MODEL=&lt;your gateway model&gt;        # + LLM_API_BASE / LLM_API_KEY
export EXTRACTION_CONCURRENCY=8                    # faster ingest at scale
export PDF_PARSER=pymupdf                          # real PDF layout parsing
export REASONING_BACKEND=semantica PROVENANCE_BACKEND=semantica ONTOLOGY_VALIDATOR=shacl
export GRAPH_STORE=rdf GRAPH_DB_PATH=./graph-oxigraph   # persistent RDF graph
export FABRIC_DB=./fabric.db                       # persist index + KB (+ lineage)
make run</code></pre>
<p>Point <code>--source</code> at your own folder (nested Markdown/PDF). Ingest once; then
ask any time — even after a restart — with <code>python demo/run_demo.py --no-ingest
--question "…"</code>. The step-by-step walkthrough, tuning for large corpora, and
troubleshooting live in <code>demo/RUNBOOK.md</code>.</p>
<div class="callout good"><p class="t">Data stays yours</p><p>The demo report is a local
file and ingestion runs against your own service; nothing is published anywhere. The LLM
gateway is whichever endpoint you configure (including an internal one).</p></div>

<h2 id="decision">Is this right for us?</h2>
<h3>Strong-fit signals</h3>
<ul class="checks">
<li>You have substantial knowledge in <strong>documents</strong> (policies, product
guides, PDFs) that people or agents repeatedly ask about.</li>
<li>Answers must be <strong>cited and auditable</strong> — you operate somewhere that
"show me why" matters (regulated, customer-facing, risk).</li>
<li>You want <strong>business rules and policy</strong> enforced deterministically, not
left to a model's discretion.</li>
<li>You're building <strong>more than one</strong> agent/app and want them to share one
governed knowledge layer instead of each re-implementing RAG.</li>
<li>You need to <strong>start small and scale</strong> — evaluate on a laptop, then move
to real vector/graph/LLM infrastructure without a rewrite.</li>
</ul>
<h3>What it augments or replaces</h3>
<ul class="checks crosses">
<li><strong>Augments</strong> existing agents/chatbots by giving them cited evidence,
graph context, and a policy gate.</li>
<li><strong>Replaces</strong> bespoke, per-app RAG pipelines with one shared, contract-
stable service.</li>
<li><strong>Complements</strong> your data platform — it reads documents and serves a
semantic layer; it isn't a data warehouse or a system of record.</li>
</ul>
<h3>Maturity &amp; honest status</h3>
<p>The platform is <strong>end-to-end and durable</strong>: ingestion (Markdown + real
PDF parsing + captions), hybrid retrieval, GraphRAG, LLM extraction into the graph,
reasoning over the graph, provenance + lineage, and the SHACL gate all work, on defaults
out of the box and on real backends on a capable host, with state that survives restarts.
CI runs the dependency-free defaults; a one-command on-env script validates the real
backends.</p>
<div class="callout warn"><p class="t">Known gaps &amp; where to look</p>
<p>Being candid, because that's what a platform decision needs:</p>
<p>• <strong>Deterministic SPARQL-rule inference</strong> is deferred — the pinned
semantica release ships that piece as an unimplemented stub, so reasoning-over-graph uses
Datalog instead (which works). • <strong>Provenance chain verification</strong> reported
a false negative on one real run and is under investigation. • <strong>Extraction
quality</strong> can be noisy on messy corpora (it captures some low-value entities) and
has a prompt/filter improvement queued. All are tracked, with reproduction and fix plans,
in <code>TODO.md</code>.</p></div>
<h3>Operating considerations</h3>
<ul class="checks crosses">
<li><strong>LLM cost/latency</strong> at ingest scale with a gateway — controlled by
concurrency and by turning extraction off for a fast structural pass.</li>
<li><strong>Model access</strong> — you supply the extraction/caption models (an internal
gateway works; captioning needs a vision-capable model).</li>
<li><strong>Infra</strong> — Qdrant and the RDF store are optional; the in-memory + SQLite
path needs no external services.</li>
</ul>

<h2 id="faq">FAQ</h2>
<h3>Do we have to send our data to a third-party LLM?</h3>
<p>No. The AI gateway is configurable — point it at an internal/enterprise gateway or a
local model. Retrieval, graph, reasoning, provenance and policy have non-LLM defaults; the
LLM is used for extraction and figure captioning, which you can route to infrastructure you
control (or disable).</p>
<h3>Can we adopt it incrementally?</h3>
<p>Yes. Consumers fall back to their own search when the service is absent, and every
backend is opt-in. Start with defaults on one team's corpus; add real embeddings, a graph
store, and durability when the value is proven.</p>
<h3>How is this different from plain RAG?</h3>
<p>RAG retrieves passages. semantic-fabric adds a knowledge <em>graph</em> (relationships,
not just passages), <em>deterministic</em> reasoning and policy, and <em>provenance</em> —
so answers are connected, checkable, and auditable, not just plausible.</p>
<h3>What does it cost to run?</h3>
<p>Nothing to evaluate — the defaults are pure Python. In production the costs are your
vector store, your graph store, and LLM calls at ingest (one-off per document, tunable).
Queries after ingest don't require an LLM unless you choose to add one downstream.</p>
<h3>Is our knowledge locked in?</h3>
<p>No. The graph is standard RDF (SPARQL-queryable and exportable), the KB is Markdown, and
the contract is open. Everything is inspectable via <code>GET /graph</code> and the KB
endpoints.</p>

<h2 id="refs">Further reading</h2>
<ul class="checks crosses">
<li><code>README.md</code> — technical overview with the architecture diagrams.</li>
<li><code>demo/RUNBOOK.md</code> — the hands-on, copy-paste end-to-end walkthrough.</li>
<li><code>VALIDATION.md</code> — how the real backends are validated on-env.</li>
<li><code>TODO.md</code> — deferred options and known gaps, with reproduction + plans.</li>
<li><code>contracts/</code> — the OpenAPI + EvidenceUnit schema (the boundary).</li>
</ul>

<p class="foot">semantic-fabric platform guide · generated from
<code>scripts/build_guide.py</code> · diagrams in <code>docs/diagrams/</code>. Regenerate
with <code>python scripts/build_guide.py</code>.</p>
"""


def build() -> str:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>semantic-fabric — platform guide</title>'
        f'<style>{CSS}</style></head><body>'
        f'<div class="layout">{toc_html()}<main>{BODY}</main></div>'
        '</body></html>'
    )


def main() -> None:
    out = ROOT / "docs" / "guide.html"
    out.write_text(build(), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
