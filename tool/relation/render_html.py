#!/usr/bin/env python3
from __future__ import annotations

import json

from tool.map.render_svg import COLORS

__all__ = ["render_html"]

_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>人物の相関</title>
<style>
  :root { --bg: #fdfcf8; --sea: #eef3f7; --ink: #222; --dim: #666; --line: #c8d0d8; --panel: #fff; }
  body { margin: 0; font-family: sans-serif; color: var(--ink); background: var(--bg); }
  header { display: flex; flex-wrap: wrap; gap: 12px 24px; align-items: center; padding: 10px 16px; border-bottom: 1px solid var(--line); }
  header h1 { font-size: 16px; margin: 0 16px 0 0; }
  .layers label { margin-right: 10px; white-space: nowrap; }
  .swatch { display: inline-block; width: 10px; height: 10px; margin-right: 3px; vertical-align: middle; }
  main { display: grid; grid-template-columns: 1fr 380px; height: calc(100vh - 56px); }
  #graph { overflow: auto; }
  svg { display: block; }
  aside { border-left: 1px solid var(--line); overflow: auto; padding: 12px; background: var(--panel); font-size: 13px; }
  aside h2 { font-size: 14px; margin: 0 0 6px; }
  aside h3 { font-size: 13px; margin: 12px 0 4px; color: var(--dim); }
  aside dl { margin: 0 0 12px; display: grid; grid-template-columns: 5em 1fr; gap: 2px 8px; }
  aside dt { color: var(--dim); }
  aside dd { margin: 0; }
  table { border-collapse: collapse; width: 100%; }
  th, td { text-align: left; padding: 3px 4px; border-bottom: 1px solid var(--line); vertical-align: top; }
  tr.row { cursor: pointer; }
  tr.row:hover { background: var(--sea); }
  .hint { color: var(--dim); }
  .text { white-space: pre-wrap; margin: 4px 0 8px; }
  .tip { position: fixed; pointer-events: none; background: var(--ink); color: #fff; padding: 6px 8px; font-size: 12px; border-radius: 3px; white-space: pre; display: none; max-width: 360px; }
  @media (max-width: 800px) { main { grid-template-columns: 1fr; grid-template-rows: 1fr 40vh; } aside { border-left: 0; border-top: 1px solid var(--line); } }
</style>
</head>
<body>
<header>
  <h1>人物の相関</h1>
  <div class="layers" id="layers"></div>
  <label class="hint">拡大 <input type="range" id="zoom" min="0.5" max="3" step="0.25" value="1"> <span id="zoomv">1×</span></label>
  <label class="hint" id="yearbox">年 <input type="number" id="year"> <span id="yearv"></span> <label><input type="checkbox" id="allyears" checked>全期間</label></label>
  <button id="reset">並べ直す</button>
</header>
<main>
  <div id="graph"></div>
  <aside id="side"></aside>
</main>
<div class="tip" id="tip"></div>
<script>
const DATA = __DATA__;
const COLORS = __COLORS__;
const R_NODE = 18, BASE = 720;
const state = { hidden: new Set(), selected: null, zoom: 1, pos: new Map(), drag: null, year: null };
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const byId = new Map(DATA.characters.map(c => [c.id, c]));
const nameOf = id => byId.get(id)?.name ?? `id=${id}`;
const kinds = [...new Set(DATA.characters.map(c => c.kind ?? ""))];
const colorOf = Object.fromEntries(kinds.map((k, i) => [k, COLORS[i % COLORS.length]]));
const inYear = (o, y) => y == null || ((o.start == null || o.start <= y) && (o.end == null || o.end > y));
const shownCharacters = () => DATA.characters.filter(c => !state.hidden.has(c.kind ?? "") && inYear(c, state.year));
const shownRelations = () => { const ids = new Set(shownCharacters().map(c => c.id));
  return DATA.relations.filter(r => ids.has(r.character_id_1) && ids.has(r.character_id_2) && inYear(r, state.year)); };
const spanText = o => (o.start == null && o.end == null) ? "" : `${o.start ?? ""}〜${o.end ?? ""}`;
const YEARS = [...DATA.relations, ...DATA.characters].flatMap(o => [o.start, o.end]).filter(y => y != null);
const YEAR_MIN = YEARS.length ? Math.min(...YEARS) : 0, YEAR_MAX = YEARS.length ? Math.max(...YEARS) : 0;
const firstLine = t => (t ?? "").split("\n").find(l => l.trim()) ?? "";

function layout() {
  // 円に並べてから、繋がりのある同士を寄せ、無い同士を離す簡単な力学配置。
  const nodes = DATA.characters, n = nodes.length, cx = BASE / 2, cy = BASE / 2, r = BASE / 2 - 80;
  const pos = new Map(nodes.map((c, i) => [c.id, { x: cx + r * Math.cos(2 * Math.PI * i / n - Math.PI / 2), y: cy + r * Math.sin(2 * Math.PI * i / n - Math.PI / 2) }]));
  const linked = new Set(DATA.relations.map(e => `${e.character_id_1}:${e.character_id_2}`));
  const isLinked = (a, b) => linked.has(`${a}:${b}`) || linked.has(`${b}:${a}`);
  for (let step = 0; step < 300; step++) {
    const force = new Map(nodes.map(c => [c.id, { x: 0, y: 0 }]));
    for (const a of nodes) for (const b of nodes) {
      if (a.id >= b.id) continue;
      const pa = pos.get(a.id), pb = pos.get(b.id);
      const dx = pb.x - pa.x, dy = pb.y - pa.y, d = Math.max(1, Math.hypot(dx, dy));
      let f = 20000 / (d * d);
      if (isLinked(a.id, b.id)) f -= (d - 160) * 0.05;
      force.get(a.id).x -= f * dx / d; force.get(a.id).y -= f * dy / d;
      force.get(b.id).x += f * dx / d; force.get(b.id).y += f * dy / d;
    }
    for (const c of nodes) {
      const p = pos.get(c.id), f = force.get(c.id);
      p.x += (cx - p.x) * 0.01 + Math.max(-8, Math.min(8, f.x));
      p.y += (cy - p.y) * 0.01 + Math.max(-8, Math.min(8, f.y));
      p.x = Math.min(BASE - 60, Math.max(60, p.x)); p.y = Math.min(BASE - 60, Math.max(60, p.y));
    }
  }
  state.pos = pos;
}

function renderLayers() {
  const box = document.getElementById("layers");
  box.innerHTML = kinds.map(k =>
    `<label><input type="checkbox" data-kind="${esc(k)}" ${state.hidden.has(k) ? "" : "checked"}>` +
    `<span class="swatch" style="background:${colorOf[k]}"></span>${esc(k || "(種別なし)")}</label>`).join("");
  box.onchange = e => { const k = e.target.dataset.kind; if (e.target.checked) state.hidden.delete(k); else state.hidden.add(k); render(); };
}

function edgePath(a, b, bend) {
  const dx = b.x - a.x, dy = b.y - a.y, d = Math.max(1, Math.hypot(dx, dy));
  const nx = -dy / d, ny = dx / d;
  const mx = (a.x + b.x) / 2 + nx * bend, my = (a.y + b.y) / 2 + ny * bend;
  const ex = b.x - dx / d * (R_NODE + 4) + (mx - b.x) * 0.0, ey = b.y - dy / d * (R_NODE + 4);
  return { d: `M${a.x},${a.y} Q${mx},${my} ${ex},${ey}`, lx: (a.x + 2 * mx + b.x) / 4, ly: (a.y + 2 * my + b.y) / 4 };
}

function renderGraph() {
  const z = state.zoom, W = BASE * z, H = BASE * z;
  const chars = shownCharacters(), rels = shownRelations();
  const sel = state.selected;
  const related = new Set();
  if (sel?.type === "character") for (const r of rels) if (r.character_id_1 === sel.id || r.character_id_2 === sel.id) related.add(r.id);
  let s = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" font-size="${11 * z}">`;
  s += `<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#555"/></marker>` +
       `<marker id="arrow-on" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#c0392b"/></marker></defs>`;
  s += `<rect width="${W}" height="${H}" fill="#fdfcf8"/>`;
  const pairCount = new Map();
  for (const r of rels) { const k = [r.character_id_1, r.character_id_2].sort((a, b) => a - b).join(":"); pairCount.set(k, (pairCount.get(k) ?? 0) + 1); }
  const seen = new Map();
  for (const r of rels) {
    const a = state.pos.get(r.character_id_1), b = state.pos.get(r.character_id_2);
    if (!a || !b) continue;
    const k = [r.character_id_1, r.character_id_2].sort((x, y) => x - y).join(":");
    const i = seen.get(k) ?? 0; seen.set(k, i + 1);
    const total = pairCount.get(k), bend = (i - (total - 1) / 2) * 40 * (r.character_id_1 < r.character_id_2 ? 1 : -1);
    const sa = { x: a.x * z, y: a.y * z }, sb = { x: b.x * z, y: b.y * z };
    const e = edgePath(sa, sb, bend * z);
    const on = sel?.type === "relation" ? sel.id === r.id : related.has(r.id);
    const dim = sel && !on;
    s += `<g class="edge" data-id="${r.id}" style="cursor:pointer" opacity="${dim ? 0.25 : 1}">`;
    s += `<path d="${e.d}" fill="none" stroke="transparent" stroke-width="12"/>`;
    s += `<path d="${e.d}" fill="none" stroke="${on ? "#c0392b" : "#555"}" stroke-width="${on ? 2.2 : 1.2}" marker-end="url(#${on ? "arrow-on" : "arrow"})"/>`;
    s += `<text x="${e.lx}" y="${e.ly}" text-anchor="middle" fill="${on ? "#c0392b" : "#333"}" stroke="#fdfcf8" stroke-width="3" paint-order="stroke" font-weight="${on ? "bold" : "normal"}">${esc(r.relation)}</text></g>`;
  }
  for (const c of chars) {
    const p = state.pos.get(c.id); if (!p) continue;
    const on = sel?.type === "character" && sel.id === c.id;
    const touched = sel?.type === "relation" && (sel.character_id_1 === c.id || sel.character_id_2 === c.id);
    s += `<g class="node" data-id="${c.id}" style="cursor:pointer">`;
    s += `<circle cx="${p.x * z}" cy="${p.y * z}" r="${R_NODE * z}" fill="${colorOf[c.kind ?? ""]}" stroke="${on || touched ? "#222" : "#fff"}" stroke-width="${on || touched ? 3 : 1.5}"/>`;
    s += `<text x="${p.x * z}" y="${(p.y + R_NODE + 14) * z}" text-anchor="middle" fill="#222" stroke="#fdfcf8" stroke-width="3" paint-order="stroke" font-size="${12 * z}" font-weight="${on ? "bold" : "normal"}">${esc(c.name)}</text></g>`;
  }
  s += "</svg>";
  const graph = document.getElementById("graph");
  graph.innerHTML = s;
  const tip = document.getElementById("tip");
  const showTip = (e, lines) => { tip.style.display = "block"; tip.style.left = (e.clientX + 14) + "px"; tip.style.top = (e.clientY + 14) + "px"; tip.textContent = lines.filter(Boolean).join("\n"); };
  graph.querySelectorAll(".node").forEach(g => {
    const c = byId.get(+g.dataset.id);
    g.onmousedown = e => { state.drag = { id: c.id, x: e.clientX, y: e.clientY, moved: false }; e.preventDefault(); };
    g.onmousemove = e => showTip(e, [`${c.name} (${c.kind ?? ""})`, c.sex ? `性別: ${c.sex}` : null,
      spanText(c) ? `期間: ${spanText(c)}` : null]);
    g.onmouseleave = () => { tip.style.display = "none"; };
  });
  graph.querySelectorAll(".edge").forEach(g => {
    const r = DATA.relations.find(q => q.id === +g.dataset.id);
    g.onclick = () => { state.selected = sel?.type === "relation" && sel.id === r.id ? null : { type: "relation", ...r }; render(); };
    g.onmousemove = e => showTip(e, [`${nameOf(r.character_id_1)} → ${nameOf(r.character_id_2)}: ${r.relation}`, spanText(r) ? `期間: ${spanText(r)}` : null, firstLine(r.text)]);
    g.onmouseleave = () => { tip.style.display = "none"; };
  });
}

document.addEventListener("mousemove", e => {
  const d = state.drag; if (!d) return;
  const p = state.pos.get(d.id);
  p.x += (e.clientX - d.x) / state.zoom; p.y += (e.clientY - d.y) / state.zoom; d.x = e.clientX; d.y = e.clientY; d.moved = true;
  renderGraph();
});
document.addEventListener("mouseup", () => {
  const d = state.drag; if (!d) return; state.drag = null;
  if (!d.moved) { state.selected = state.selected?.type === "character" && state.selected.id === d.id ? null : { type: "character", id: d.id }; }
  render();
});

function relationRow(r, from) {
  const other = from == null ? null : (r.character_id_1 === from ? r.character_id_2 : r.character_id_1);
  return `<tr class="row" data-id="${r.id}">` +
    (from == null ? `<td>${esc(nameOf(r.character_id_1))}</td><td>${esc(r.relation)} →</td><td>${esc(nameOf(r.character_id_2))}</td>`
                  : `<td>${r.character_id_1 === from ? "→" : "←"}</td><td>${esc(nameOf(other))}</td><td>${esc(r.relation)}</td>`) +
    `<td class="hint">${esc(spanText(r))}</td><td class="hint">${esc(firstLine(r.text))}</td></tr>`;
}

function renderSide() {
  const side = document.getElementById("side"), sel = state.selected, rels = shownRelations();
  const table = (rows, head) => `<table><tr>${head.map(h => `<th>${h}</th>`).join("")}</tr>${rows.join("")}</table>`;
  if (!sel) {
    side.innerHTML = `<p class="hint">人物をクリックするとその人物の関係を、矢印をクリックするとその関係の本文を出す。人物はドラッグで動かせる。</p>` +
      `<p class="hint">人物 ${shownCharacters().length} 件、関係 ${rels.length} 件${state.year == null ? "" : `(${state.year} 年に続いているもの)`}。矢印は character_id_1 → character_id_2 の向き。</p>` +
      (rels.length ? table(rels.map(r => relationRow(r, null)), ["主体", "関係", "相手", "期間", ""]) : "");
  } else if (sel.type === "character") {
    const c = byId.get(sel.id), mine = rels.filter(r => r.character_id_1 === sel.id || r.character_id_2 === sel.id);
    side.innerHTML = `<h2>${esc(c.name)} <span class="hint">(${esc(c.kind ?? "")})</span></h2>` +
      `<dl>` + (c.sex ? `<dt>性別</dt><dd>${esc(c.sex)}</dd>` : "") +
      (spanText(c) ? `<dt>期間</dt><dd>${esc(spanText(c))}</dd>` : "") +
      `<dt>記事</dt><dd><a href="${esc(c.link)}" target="_blank">GUI で開く</a></dd></dl>` +
      (mine.length ? table(mine.map(r => relationRow(r, sel.id)), ["", "相手", "関係", "期間", ""]) : `<p class="hint">関係は無い。</p>`);
  } else {
    side.innerHTML = `<h2>${esc(nameOf(sel.character_id_1))} → ${esc(nameOf(sel.character_id_2))}</h2>` +
      `<dl><dt>関係</dt><dd>${esc(sel.relation)}</dd>` + (spanText(sel) ? `<dt>期間</dt><dd>${esc(spanText(sel))}</dd>` : "") + `<dt>id</dt><dd>${sel.id}</dd></dl>` +
      `<div class="text">${esc(sel.text) || '<span class="hint">本文は無い。</span>'}</div>`;
  }
  side.querySelectorAll("tr.row").forEach(tr => { tr.onclick = () => { state.selected = { type: "relation", ...DATA.relations.find(r => r.id === +tr.dataset.id) }; render(); }; });
}

function render() { renderLayers(); renderGraph(); renderSide(); }
document.getElementById("zoom").oninput = e => { state.zoom = +e.target.value; document.getElementById("zoomv").textContent = state.zoom + "×"; render(); };
document.getElementById("reset").onclick = () => { layout(); render(); };
const yearInput = document.getElementById("year"), allYears = document.getElementById("allyears");
yearInput.min = YEAR_MIN; yearInput.max = YEAR_MAX; yearInput.value = YEAR_MIN;
const syncYear = () => { state.year = allYears.checked ? null : +yearInput.value;
  document.getElementById("yearv").textContent = allYears.checked ? "" : `${state.year} 年`; render(); };
yearInput.oninput = () => { allYears.checked = false; syncYear(); };
allYears.onchange = syncYear;
if (!YEARS.length) document.getElementById("yearbox").style.display = "none";
if (DATA.characters.length) { layout(); render(); } else document.getElementById("graph").innerHTML = '<p class="hint" style="padding:16px">人物が居ない。</p>';
</script>
</body>
</html>
"""


def render_html(data: dict) -> str:
    dump = lambda value: json.dumps(value, ensure_ascii=False).replace("</", "<\\/")
    return _TEMPLATE.replace("__DATA__", dump(data)).replace("__COLORS__", dump(list(COLORS)))
