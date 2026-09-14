/* fabric-explorer SPA — browse the fabric's content. Talks only to same-origin /api/*. */
(() => {
  "use strict";
  const main = document.getElementById("main");
  const statusEl = document.getElementById("status");
  const cache = {};

  // ---- helpers -----------------------------------------------------------
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const short = (s, n) => { s = String(s ?? ""); return s.length > n ? s.slice(0, n - 1) + "…" : s; };

  async function api(path, opts) {
    const r = await fetch("/api/" + path, opts);
    if (!r.ok) throw new Error("HTTP " + r.status + " on " + path + ": " + (await r.text()).slice(0, 200));
    return r.json();
  }
  const apiGet = (p) => api(p);
  const apiPost = (p, body) => api(p, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });

  async function graph() {
    if (!cache.graph) {
      cache.graph = await apiGet("graph");
      const deg = {};
      for (const r of cache.graph.relations || []) { deg[r.subject] = (deg[r.subject] || 0) + 1; deg[r.object] = (deg[r.object] || 0) + 1; }
      cache.deg = deg;
      cache.entByName = Object.fromEntries((cache.graph.entities || []).map((e) => [e.name, e]));
    }
    return cache.graph;
  }
  async function tree(ns) {
    cache.tree = cache.tree || {};
    if (!cache.tree[ns]) { try { cache.tree[ns] = await apiGet(`kb/${ns}/tree`); } catch { cache.tree[ns] = { pages: [] }; } }
    return cache.tree[ns];
  }

  // ---- tiny markdown renderer -------------------------------------------
  function md(src) {
    const lines = String(src || "").replace(/\r/g, "").split("\n");
    let html = "", i = 0, listType = null;
    const closeList = () => { if (listType) { html += `</${listType}>`; listType = null; } };
    const inline = (t) => esc(t)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>")
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    while (i < lines.length) {
      let ln = lines[i];
      if (/^```/.test(ln)) { closeList(); i++; let code = ""; while (i < lines.length && !/^```/.test(lines[i])) { code += lines[i] + "\n"; i++; } i++; html += `<pre><code>${esc(code)}</code></pre>`; continue; }
      const h = ln.match(/^(#{1,6})\s+(.*)$/);
      if (h) { closeList(); html += `<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`; i++; continue; }
      const ul = ln.match(/^\s*[-*]\s+(.*)$/), ol = ln.match(/^\s*\d+\.\s+(.*)$/);
      if (ul || ol) { const t = ul ? "ul" : "ol"; if (listType !== t) { closeList(); html += `<${t}>`; listType = t; } html += `<li>${inline((ul || ol)[1])}</li>`; i++; continue; }
      if (ln.trim() === "") { closeList(); i++; continue; }
      closeList(); html += `<p>${inline(ln)}</p>`; i++;
    }
    closeList();
    return html;
  }

  // ---- views -------------------------------------------------------------
  async function viewOverview() {
    main.innerHTML = `<h1>Overview</h1><p class="lede">A snapshot of everything ingested into the fabric.</p><div id="ov"><div class="empty">Loading…</div></div>`;
    const ov = document.getElementById("ov");
    try {
      const g = await graph();
      const [a, gen] = await Promise.all([tree("authored"), tree("generated")]);
      const c = g.counts || {};
      const tiles = [
        ["Authored pages", a.count ?? (a.pages || []).length],
        ["Generated pages", gen.count ?? (gen.pages || []).length],
        ["Entities", c.entities ?? (g.entities || []).length],
        ["Relations", c.relations ?? (g.relations || []).length],
        ["Graph pages", c.pages ?? (g.pages || []).length],
      ];
      const topEnt = [...(g.entities || [])].sort((x, y) => (cache.deg[y.name] || 0) - (cache.deg[x.name] || 0)).slice(0, 14);
      const predCount = {};
      for (const r of g.relations || []) predCount[r.predicate] = (predCount[r.predicate] || 0) + 1;
      const topPred = Object.entries(predCount).sort((a, b) => b[1] - a[1]).slice(0, 14);
      const sections = {};
      for (const p of g.pages || []) { const s = p.section || (p.path || "").split("/")[0]; if (s) sections[s] = (sections[s] || 0) + 1; }
      ov.innerHTML = `
        <div class="tiles">${tiles.map(([l, n]) => `<div class="tile"><div class="n">${(n || 0).toLocaleString()}</div><div class="l">${esc(l)}</div></div>`).join("")}</div>
        <div class="grid2">
          <div class="card"><h3>Most-connected entities</h3>${topEnt.length ? topEnt.map((e) => `<span class="chip"><a data-ent="${esc(e.name)}">${esc(short(e.name, 40))}</a> <span class="tag">${esc(e.type)}</span> · ${cache.deg[e.name] || 0}</span>`).join("") : '<p class="muted small">No entities yet — enable EXTRACTION_ON_INGEST and re-ingest.</p>'}</div>
          <div class="card"><h3>Top relation types</h3>${topPred.length ? topPred.map(([p, n]) => `<span class="chip"><span class="pred mono">${esc(p)}</span> · ${n}</span>`).join("") : '<p class="muted small">None.</p>'}</div>
        </div>
        <div class="card"><h3>Sections</h3>${Object.keys(sections).length ? Object.entries(sections).sort((a, b) => b[1] - a[1]).map(([s, n]) => `<span class="chip">${esc(s)} · ${n}</span>`).join("") : '<p class="muted small">No pages.</p>'}</div>`;
      ov.querySelectorAll("[data-ent]").forEach((a) => a.onclick = () => { location.hash = "graph"; pendingEntity = a.getAttribute("data-ent"); });
    } catch (e) { ov.innerHTML = `<div class="err">${esc(e.message)}</div>`; }
  }

  async function viewKB() {
    main.innerHTML = `<h1>Knowledge base</h1>
      <div class="row"><select id="ns"><option value="authored">authored</option><option value="generated">generated</option></select>
      <input id="kbq" placeholder="filter pages…" style="flex:1;min-width:180px"><span class="muted small" id="kbcount"></span></div>
      <div class="grid2" style="margin-top:12px"><div class="list" id="kblist"></div><div id="kbdoc"><div class="empty">Select a page to read it.</div></div></div>`;
    const nsSel = document.getElementById("ns"), q = document.getElementById("kbq");
    const listEl = document.getElementById("kblist"), countEl = document.getElementById("kbcount");
    async function renderList() {
      const ns = nsSel.value; const t = await tree(ns); const filter = q.value.toLowerCase();
      const pages = (t.pages || []).filter((p) => p.toLowerCase().includes(filter));
      countEl.textContent = `${pages.length} / ${(t.pages || []).length} pages`;
      listEl.innerHTML = pages.slice(0, 500).map((p) => `<div class="item" data-p="${esc(p)}"><div class="t">${esc(short(p.split("/").pop(), 60))}</div><div class="p">${esc(p)}</div></div>`).join("") || '<div class="empty">No pages.</div>';
      listEl.querySelectorAll(".item").forEach((it) => it.onclick = () => openPage(ns, it.getAttribute("data-p"), it));
    }
    async function openPage(ns, path, itemEl) {
      listEl.querySelectorAll(".item").forEach((x) => x.classList.remove("active")); if (itemEl) itemEl.classList.add("active");
      const doc = document.getElementById("kbdoc"); doc.innerHTML = `<div class="empty">Loading…</div>`;
      try {
        const page = await apiGet(`kb/${ns}/${path}`);
        const fm = page.frontmatter && Object.keys(page.frontmatter).length ? `<div class="fm">${Object.entries(page.frontmatter).map(([k, v]) => `<b>${esc(k)}:</b> ${esc(Array.isArray(v) ? v.join(", ") : v)}`).join(" &nbsp;·&nbsp; ")}</div>` : "";
        doc.innerHTML = `<div class="doc"><div class="row small muted" style="margin-bottom:8px"><span class="pill">${esc(ns)}</span> <span class="mono">${esc(path)}</span></div>${fm}${md(page.body)}</div>`;
      } catch (e) { doc.innerHTML = `<div class="err">${esc(e.message)}</div>`; }
    }
    window._openPage = openPage;
    nsSel.onchange = renderList; q.oninput = renderList; await renderList();
    if (pendingPage) { const { ns, path } = pendingPage; pendingPage = null; nsSel.value = ns; await renderList(); openPage(ns, path); }
  }

  let graphTab = "entities", graphQuery = "", graphSort = "degree";
  async function viewGraph() {
    main.innerHTML = `<h1>Knowledge graph</h1><p class="lede">The entities and relations extracted from the corpus.</p>
      <div class="row"><button id="tabE" class="pill">Entities</button><button id="tabR" class="tag">Relations</button>
      <input id="gq" placeholder="filter…" style="flex:1;min-width:180px" value="${esc(graphQuery)}"><span class="muted small" id="gcount"></span></div>
      <div class="grid2" style="margin-top:12px"><div id="gleft"></div><div id="gright"><div class="empty">Select a row for detail.</div></div></div>`;
    const gq = document.getElementById("gq");
    document.getElementById("tabE").onclick = () => { graphTab = "entities"; render(); };
    document.getElementById("tabR").onclick = () => { graphTab = "relations"; render(); };
    gq.oninput = () => { graphQuery = gq.value; render(); };
    async function render() {
      const g = await graph();
      document.getElementById("tabE").className = graphTab === "entities" ? "pill" : "tag";
      document.getElementById("tabR").className = graphTab === "relations" ? "pill" : "tag";
      const left = document.getElementById("gleft"), count = document.getElementById("gcount");
      const f = graphQuery.toLowerCase();
      if (graphTab === "entities") {
        let ents = (g.entities || []).map((e) => ({ ...e, degree: cache.deg[e.name] || 0 }))
          .filter((e) => e.name.toLowerCase().includes(f) || (e.type || "").toLowerCase().includes(f));
        ents.sort((a, b) => graphSort === "name" ? a.name.localeCompare(b.name) : b.degree - a.degree);
        count.textContent = `${ents.length.toLocaleString()} / ${(g.entities || []).length.toLocaleString()} entities`;
        const rows = ents.slice(0, 300).map((e) => `<tr data-ent="${esc(e.name)}"><td>${esc(short(e.name, 46))}</td><td><span class="tag">${esc(e.type)}</span></td><td class="num">${e.degree}</td><td class="num">${(e.pages || []).length}</td></tr>`).join("");
        left.innerHTML = `<div class="tablewrap"><table><thead><tr><th data-s="name">Entity</th><th>Type</th><th data-s="degree">Degree</th><th>Pages</th></tr></thead><tbody>${rows || '<tr><td colspan="4" class="empty">No entities.</td></tr>'}</tbody></table></div>`;
        left.querySelectorAll("th[data-s]").forEach((th) => th.onclick = () => { graphSort = th.getAttribute("data-s"); render(); });
        left.querySelectorAll("tr[data-ent]").forEach((tr) => tr.onclick = () => entityDetail(tr.getAttribute("data-ent")));
      } else {
        let rels = (g.relations || []).filter((r) => r.subject.toLowerCase().includes(f) || r.object.toLowerCase().includes(f) || r.predicate.toLowerCase().includes(f));
        count.textContent = `${rels.length.toLocaleString()} / ${(g.relations || []).length.toLocaleString()} relations`;
        const rows = rels.slice(0, 400).map((r) => `<tr><td><a data-ent="${esc(r.subject)}">${esc(short(r.subject, 34))}</a></td><td class="mono" style="color:var(--accent-ink)">${esc(r.predicate)}</td><td><a data-ent="${esc(r.object)}">${esc(short(r.object, 34))}</a></td></tr>`).join("");
        left.innerHTML = `<div class="tablewrap"><table><thead><tr><th>Subject</th><th>Predicate</th><th>Object</th></tr></thead><tbody>${rows || '<tr><td colspan="3" class="empty">No relations.</td></tr>'}</tbody></table></div>`;
        left.querySelectorAll("a[data-ent]").forEach((a) => a.onclick = () => entityDetail(a.getAttribute("data-ent")));
      }
    }
    async function entityDetail(name) {
      const g = await graph(); const e = cache.entByName[name] || { name, type: "Unknown", pages: [] };
      const rels = (g.relations || []).filter((r) => r.subject === name || r.object === name);
      const right = document.getElementById("gright");
      const pagesHtml = (e.pages || []).length ? (e.pages || []).map((p) => `<a data-page="${esc(p)}">${esc(p)}</a>`).join("<br>") : '<span class="muted">—</span>';
      const relsHtml = rels.slice(0, 60).map((r) => r.subject === name
        ? `<div class="rel">${esc(short(name, 22))} <span class="pred mono">${esc(r.predicate)}</span> <a data-ent="${esc(r.object)}">${esc(short(r.object, 30))}</a></div>`
        : `<div class="rel"><a data-ent="${esc(r.subject)}">${esc(short(r.subject, 30))}</a> <span class="pred mono">${esc(r.predicate)}</span> ${esc(short(name, 22))}</div>`).join("") || '<span class="muted">No relations.</span>';
      right.innerHTML = `<div class="detail"><h3>${esc(name)}</h3>
        <div class="kv"><b>Type</b><span>${esc(e.type)}</span><b>Degree</b><span>${cache.deg[name] || 0}</span></div>
        ${neighborhoodSVG(name, rels)}
        <h3>Relations</h3>${relsHtml}
        <h3>Mentioned on</h3><div class="small mono">${pagesHtml}</div></div>`;
      right.querySelectorAll("a[data-ent]").forEach((a) => a.onclick = () => entityDetail(a.getAttribute("data-ent")));
      right.querySelectorAll("a[data-page]").forEach((a) => a.onclick = () => { pendingPage = { ns: "authored", path: a.getAttribute("data-page") }; location.hash = "kb"; });
    }
    render();
    if (pendingEntity) { const n = pendingEntity; pendingEntity = null; entityDetail(n); }
  }

  function neighborhoodSVG(name, rels) {
    const neigh = []; const seen = new Set();
    for (const r of rels) { const other = r.subject === name ? r.object : r.subject; if (!seen.has(other) && other !== name) { seen.add(other); neigh.push({ other, pred: r.predicate }); } if (neigh.length >= 10) break; }
    if (!neigh.length) return "";
    const W = 340, H = 220, cx = W / 2, cy = H / 2, R = 78;
    let edges = "", nodes = "";
    neigh.forEach((nn, i) => {
      const ang = -Math.PI / 2 + (2 * Math.PI * i) / neigh.length;
      const x = cx + R * Math.cos(ang), y = cy + R * Math.sin(ang);
      edges += `<line class="edge" x1="${cx}" y1="${cy}" x2="${x.toFixed(0)}" y2="${y.toFixed(0)}"><title>${esc(nn.pred)}</title></line>`;
      const anchor = x >= cx ? "start" : "end", dx = x >= cx ? 8 : -8;
      nodes += `<circle class="node" cx="${x.toFixed(0)}" cy="${y.toFixed(0)}" r="5" fill="var(--s2)"><title>${esc(nn.other)}</title></circle>`;
      nodes += `<text x="${(x + dx).toFixed(0)}" y="${(y + 3).toFixed(0)}" text-anchor="${anchor}">${esc(short(nn.other, 16))}</text>`;
    });
    nodes += `<circle class="node" cx="${cx}" cy="${cy}" r="7" fill="var(--s1)"/><text x="${cx}" y="${cy - 11}" text-anchor="middle">${esc(short(name, 18))}</text>`;
    return `<svg class="ngraph" viewBox="0 0 ${W} ${H}">${edges}${nodes}</svg>`;
  }

  async function viewSearch() {
    main.innerHTML = `<h1>Search</h1><p class="lede">Hybrid retrieval (vector + BM25) over the ingested corpus.</p>
      <div class="row"><input id="sq" placeholder="ask something…" style="flex:1;min-width:220px" autofocus>
      <select id="sk"><option>5</option><option>10</option><option>20</option></select><button id="sgo" class="pill" style="padding:8px 16px">Search</button></div>
      <div id="sres" style="margin-top:14px"></div>`;
    const sq = document.getElementById("sq"), sk = document.getElementById("sk"), res = document.getElementById("sres");
    async function run() {
      const query = sq.value.trim(); if (!query) return;
      res.innerHTML = `<div class="empty">Searching…</div>`;
      try {
        const r = await apiPost("search", { query, top_k: parseInt(sk.value, 10) });
        const units = r.units || [];
        if (!units.length) { res.innerHTML = `<div class="err">No results. If the graph has data but search is empty, the retrieval index may not be loaded — start the fabric with FABRIC_DB set and re-ingest once.</div>`; return; }
        res.innerHTML = units.map((u) => {
          const prov = u.provenance || {};
          return `<div class="result"><div class="top"><span class="pill">${esc(u.type)}</span><strong>${esc(u.title || u.path)}</strong><span class="spacer"></span><span class="score">${(u.score ?? "").toString()}</span></div>
            <div class="content">${esc(short(u.content || u.summary || "", 400))}</div>
            <div class="prov">${esc(u.path)} ${prov.locator ? "· " + esc(prov.locator) : ""} <a data-page="${esc(u.path)}">open page ↗</a></div></div>`;
        }).join("");
        res.querySelectorAll("a[data-page]").forEach((a) => a.onclick = () => { pendingPage = { ns: "authored", path: a.getAttribute("data-page") }; location.hash = "kb"; });
      } catch (e) { res.innerHTML = `<div class="err">${esc(e.message)}</div>`; }
    }
    document.getElementById("sgo").onclick = run; sq.onkeydown = (e) => { if (e.key === "Enter") run(); };
  }

  // ---- router + boot -----------------------------------------------------
  let pendingEntity = null, pendingPage = null;
  const views = { overview: viewOverview, kb: viewKB, graph: viewGraph, search: viewSearch };
  function route() {
    const v = (location.hash.replace("#", "") || "overview");
    document.querySelectorAll("nav.side a").forEach((a) => a.classList.toggle("active", a.getAttribute("data-view") === v));
    (views[v] || viewOverview)();
  }
  document.querySelectorAll("nav.side a").forEach((a) => a.onclick = () => { location.hash = a.getAttribute("data-view"); });
  window.addEventListener("hashchange", route);

  (async () => {
    try { const h = await apiGet("health"); statusEl.innerHTML = `fabric <span class="ok">● connected</span><br>contract ${esc(h.contract_version || "?")}`; }
    catch (e) { statusEl.innerHTML = `fabric <span class="bad">● unreachable</span><br>${esc(short(e.message, 60))}`; }
    route();
  })();
})();
