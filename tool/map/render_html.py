#!/usr/bin/env python3
from __future__ import annotations

import json

from tool.map.category import CATEGORIES, CATEGORY_COLORS, SHAPE_OPACITY
from tool.map.geometry import BEARINGS

__all__ = ["render_html"]

_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>場所の地図</title>
<style>
  :root { --bg: #fdfcf8; --sea: #eef3f7; --ink: #222; --dim: #666; --line: #c8d0d8; --panel: #fff; }
  body { margin: 0; font-family: sans-serif; color: var(--ink); background: var(--bg); }
  header { display: flex; flex-wrap: wrap; gap: 12px 24px; align-items: center; padding: 10px 16px; border-bottom: 1px solid var(--line); }
  header h1 { font-size: 16px; margin: 0 16px 0 0; }
  .tabs button { margin-right: 4px; padding: 4px 10px; border: 1px solid var(--line); background: var(--panel); cursor: pointer; }
  .tabs button.on { background: var(--ink); color: #fff; }
  .layers label { margin-right: 10px; white-space: nowrap; }
  .swatch { display: inline-block; width: 10px; height: 10px; margin-right: 3px; vertical-align: middle; }
  main { display: grid; grid-template-columns: 1fr 340px; height: calc(100vh - 56px); }
  #map { overflow: auto; }
  svg { display: block; }
  aside { border-left: 1px solid var(--line); overflow: auto; padding: 12px; background: var(--panel); font-size: 13px; }
  aside h2 { font-size: 14px; margin: 0 0 6px; }
  aside dl { margin: 0 0 12px; display: grid; grid-template-columns: 5em 1fr; gap: 2px 8px; }
  aside dt { color: var(--dim); }
  aside dd { margin: 0; }
  table { border-collapse: collapse; width: 100%; }
  th, td { text-align: left; padding: 3px 4px; border-bottom: 1px solid var(--line); }
  td.num { text-align: right; }
  td, th { white-space: nowrap; }
  td:first-child { white-space: normal; }
  tr.row { cursor: pointer; }
  tr.row:hover { background: var(--sea); }
  .hint { color: var(--dim); }
  .tip { position: fixed; pointer-events: none; background: var(--ink); color: #fff; padding: 6px 8px; font-size: 12px; border-radius: 3px; white-space: pre; display: none; }
  @media (max-width: 800px) { main { grid-template-columns: 1fr; grid-template-rows: 1fr 40vh; } aside { border-left: 0; border-top: 1px solid var(--line); } }
</style>
</head>
<body>
<header>
  <h1>場所の地図</h1>
  <div class="tabs" id="tabs"></div>
  <div class="layers" id="layers"></div>
  <label class="hint">拡大 <input type="range" id="zoom" min="0.5" max="4" step="0.25" value="1"> <span id="zoomv">1×</span></label>
</header>
<main>
  <div id="map"></div>
  <aside id="side"><p class="hint">点をクリックすると、そこから見た他の場所の距離と方角を出す。</p></aside>
</main>
<div class="tip" id="tip"></div>
<script>
const PLANETS = __PLANETS__;
const CATEGORIES = __CATEGORIES__;
const CATEGORY_COLORS = __CATEGORY_COLORS__;
const SHAPE_OPACITY = __SHAPE_OPACITY__;
const BEARINGS = __BEARINGS__;
const ML = 60, MT = 40, MR = 20, MB = 30, PAD = 10, GRID = 10, MIN_SCALE = 6, TARGET_WIDTH = 1400;
const state = { planet: 0, hidden: new Set(), origin: null, zoom: 1 };

const outerRing = poly => { const r = poly.coordinates[0]; return r.length > 1 && r[0][0] === r[r.length - 1][0] && r[0][1] === r[r.length - 1][1] ? r.slice(0, -1) : r; };
function fitFrame(points, shapes = []) {
  const fl = (v, s) => Math.floor(v / s) * s, ce = (v, s) => -fl(-v, s);
  const lons = points.map(p => p.lon), lats = points.map(p => p.lat);
  for (const sh of shapes) for (const [lon, lat] of outerRing(sh.polygon)) { lons.push(lon); lats.push(lat); }
  if (!lons.length) return { lonMin: -180, lonMax: 180, latMin: -90, latMax: 90, scale: MIN_SCALE / 2 };
  const f = { lonMin: Math.max(-180, fl(Math.min(...lons) - PAD, GRID)), lonMax: Math.min(180, ce(Math.max(...lons) + PAD, GRID)),
              latMin: Math.max(-90, fl(Math.min(...lats) - PAD, GRID)), latMax: Math.min(90, ce(Math.max(...lats) + PAD, GRID)) };
  f.scale = Math.max(MIN_SCALE, TARGET_WIDTH / (f.lonMax - f.lonMin)) * state.zoom;
  const span = Math.max(f.lonMax - f.lonMin, f.latMax - f.latMin);
  f.step = span > 180 ? 30 : span > 60 ? 10 : 5;
  f.x = lon => ML + (lon - f.lonMin) * f.scale;
  f.y = lat => MT + (f.latMax - lat) * f.scale;
  return f;
}
const textWidth = (t, px = 11) => [...t].reduce((w, ch) => w + (ch.codePointAt(0) > 0x2E7F ? px : px * 0.55), 0);
const CANDIDATES = [["start", 8, 4], ["end", -8, 4], ["middle", 0, -9], ["middle", 0, 15],
                    ["start", 8, -8], ["start", 8, 16], ["end", -8, -8], ["end", -8, 16]];
const overlaps = (a, b) => !(a[2] <= b[0] || b[2] <= a[0] || a[3] <= b[1] || b[3] <= a[1]);
function placeLabels(items, px = 11) {
  const placed = [];
  return items.map(([x, y, text]) => {
    const w = textWidth(text, px), h = px + 2;
    for (const [anchor, dx, dy] of CANDIDATES) {
      const lx = x + dx - (anchor === "end" ? w : anchor === "middle" ? w / 2 : 0);
      const box = [lx, y + dy - h, lx + w, y + dy];
      if (!placed.some(o => overlaps(box, o))) { placed.push(box); return [x + dx, y + dy, anchor]; }
    }
    placed.push([x + 8, y + 4 - h, x + 8 + w, y + 4]); return [x + 8, y + 4, "start"];
  });
}
const rad = d => d * Math.PI / 180;
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

function angular(a, b) {
  const p1 = rad(a.lat), p2 = rad(b.lat), dl = rad(b.lon - a.lon);
  const h = Math.sin((p2 - p1) / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * Math.asin(Math.min(1, Math.sqrt(h))) * 180 / Math.PI;
}
function bearing(a, b) {
  const p1 = rad(a.lat), p2 = rad(b.lat), dl = rad(b.lon - a.lon);
  const x = Math.sin(dl) * Math.cos(p2);
  const y = Math.cos(p1) * Math.sin(p2) - Math.sin(p1) * Math.cos(p2) * Math.cos(dl);
  return (Math.atan2(x, y) * 180 / Math.PI + 360) % 360;
}
const bearingName = d => BEARINGS[Math.floor((d + 11.25) / 22.5) % 16];
function distanceText(km, deg) {
  if (km == null) return `約${deg.toFixed(1)}度`;
  return km < 100 ? `約${Math.round(km).toLocaleString()} km` : `約${(Math.round(km / 10) * 10).toLocaleString()} km`;
}
function altText(alt) { return alt == null ? "" : ` (${alt >= 0 ? "+" : ""}${Math.round(alt).toLocaleString()} m)`; }
function altDiffText(d) {
  if (d == null) return "高低差は不明";
  if (Math.abs(d) < 1) return "同じ高さ";
  return `${d > 0 ? "上" : "下"}へ ${Math.round(Math.abs(d)).toLocaleString()} m`;
}

function renderTabs() {
  const tabs = document.getElementById("tabs");
  tabs.innerHTML = PLANETS.map((pl, i) =>
    `<button class="${i === state.planet ? "on" : ""}" data-i="${i}">${esc(pl.planet.name)}</button>`).join("");
  tabs.onclick = e => { const b = e.target.closest("button"); if (!b) return;
    state.planet = +b.dataset.i; state.hidden.clear(); state.origin = null; render(); };
}

function renderLayers() {
  const box = document.getElementById("layers");
  box.innerHTML = CATEGORIES.map(name =>
    `<label><input type="checkbox" data-name="${esc(name)}" ${state.hidden.has(name) ? "" : "checked"}>` +
    `<svg width="12" height="12" style="display:inline-block;vertical-align:middle;margin-right:3px">${marker(name, 6, 6, 5, CATEGORY_COLORS[name], "")}</svg>${esc(name)}</label>`).join("");
  box.onchange = e => { const n = e.target.dataset.name; if (e.target.checked) state.hidden.delete(n); else state.hidden.add(n); render(); };
}

function marker(category, x, y, r, color, extra) {
  const attrs = `fill="${color}" stroke="#fff" ${extra}`;
  if (category === "国") return `<circle cx="${x}" cy="${y}" r="${r}" ${attrs}/>`;
  if (category === "都市") return `<rect x="${x - r}" y="${y - r}" width="${2 * r}" height="${2 * r}" ${attrs}/>`;
  if (category === "自然") return `<path d="M${x},${y - r * 1.2} L${x + r * 1.1},${y + r * .8} L${x - r * 1.1},${y + r * .8} Z" ${attrs}/>`;
  return `<path d="M${x},${y - r} L${x + r},${y} L${x},${y + r} L${x - r},${y} Z" ${attrs}/>`;
}

function shapePath(f, poly) {
  return poly.coordinates.map(ring => ring.map(([lon, lat], i) => `${i ? "L" : "M"}${f.x(lon)},${f.y(lat)}`).join(" ") + " Z").join(" ");
}

function renderMap(planet, points, shapes) {
  const f = fitFrame(points, shapes), X = f.x, Y = f.y;
  const W = ML + (f.lonMax - f.lonMin) * f.scale + MR, H = MT + (f.latMax - f.latMin) * f.scale + MB;
  let s = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" font-size="11">`;
  s += `<rect width="${W}" height="${H}" fill="#fdfcf8"/>`;
  s += `<rect x="${X(f.lonMin)}" y="${Y(f.latMax)}" width="${(f.lonMax - f.lonMin) * f.scale}" height="${(f.latMax - f.latMin) * f.scale}" fill="#eef3f7" stroke="#999"/>`;
  for (let lon = f.lonMin; lon <= f.lonMax; lon += f.step) {
    s += `<line x1="${X(lon)}" y1="${Y(f.latMax)}" x2="${X(lon)}" y2="${Y(f.latMin)}" stroke="${lon ? "#c8d0d8" : "#666"}" stroke-width="${lon ? .6 : 1.2}"/>`;
    s += `<text x="${X(lon)}" y="${Y(f.latMin) + 14}" text-anchor="middle" fill="#555">${lon}°</text>`;
  }
  for (let lat = f.latMin; lat <= f.latMax; lat += f.step) {
    s += `<line x1="${X(f.lonMin)}" y1="${Y(lat)}" x2="${X(f.lonMax)}" y2="${Y(lat)}" stroke="${lat ? "#c8d0d8" : "#666"}" stroke-width="${lat ? .6 : 1.2}"/>`;
    s += `<text x="${X(f.lonMin) - 6}" y="${Y(lat) + 4}" text-anchor="end" fill="#555">${lat}°</text>`;
  }
  const r = planet.radius_km;
  s += `<text x="${ML}" y="24" font-size="18" font-weight="bold">${esc(planet.name)}</text>`;
  s += `<text x="${ML + 40 + planet.name.length * 18}" y="24" fill="#555">${r ? `半径 約${Math.round(r).toLocaleString()} km、緯度1度 ≒ ${Math.round(r * Math.PI / 180).toLocaleString()} km` : "半径は不明(area が無い)"}</text>`;

  const pointIds = new Set(points.map(p => p.id));
  const order = p => CATEGORIES.indexOf(p.category);
  for (const p of shapes.filter(p => !state.hidden.has(p.category)).sort((a, b) => order(a) - order(b) || a.id - b.id)) {
    const color = CATEGORY_COLORS[p.category];
    s += `<g class="shape" data-id="${p.id}"><path d="${shapePath(f, p.polygon)}" fill="${color}" fill-opacity="${SHAPE_OPACITY[p.category]}" fill-rule="evenodd" stroke="${color}" stroke-width="1.2" stroke-linejoin="round"/>`;
    if (!pointIds.has(p.id)) {
      const ring = outerRing(p.polygon), cx = ring.reduce((a, q) => a + q[0], 0) / ring.length, cy = ring.reduce((a, q) => a + q[1], 0) / ring.length;
      s += `<text x="${X(cx)}" y="${Y(cy)}" text-anchor="middle" font-size="13" font-weight="bold" fill="${color}" fill-opacity=".7" pointer-events="none">${esc(p.name)}</text>`;
    }
    s += "</g>";
  }

  const shown = points.filter(p => !state.hidden.has(p.category));
  const origin = shown.find(p => p.id === state.origin) ?? null;
  if (origin) for (const p of shown) if (p !== origin)
    s += `<line x1="${X(origin.lon)}" y1="${Y(origin.lat)}" x2="${X(p.lon)}" y2="${Y(p.lat)}" stroke="#333" stroke-width=".5" stroke-dasharray="3 3"/>`;

  const groups = new Map();
  for (const p of [...shown].sort((a, b) => order(a) - order(b) || a.id - b.id)) {
    const k = `${p.lon},${p.lat}`; if (!groups.has(k)) groups.set(k, []); groups.get(k).push(p);
  }
  const drawn = [];
  for (const members of groups.values()) members.forEach((p, i) => drawn.push([p, X(p.lon), Y(p.lat), i]));
  const labels = placeLabels(drawn.map(([p, x, y, i]) => [x, y + 12 * i, p.name + altText(p.alt)]));
  drawn.forEach(([p, x, y, i], n) => {
    const [lx, ly, anchor] = labels[n], color = CATEGORY_COLORS[p.category];
    const sel = origin && origin.id === p.id;
    s += `<g class="pt" data-id="${p.id}" style="cursor:pointer">`;
    s += marker(p.category, x, y, (sel ? 7 : 4) + 2 * i, color, `stroke-width="${sel ? 2.5 : 1}"`);
    s += `<text x="${lx}" y="${ly}" text-anchor="${anchor}" fill="${color}" stroke="#fdfcf8" stroke-width="3" paint-order="stroke" font-weight="${sel ? "bold" : "normal"}">${esc(p.name)}${esc(altText(p.alt))}</text></g>`;
  });
  s += "</svg>";
  const map = document.getElementById("map");
  map.innerHTML = s;
  const tip = document.getElementById("tip");
  map.querySelectorAll(".shape").forEach(g => {
    const p = shapes.find(q => q.id === +g.dataset.id);
    g.onmousemove = e => { tip.style.display = "block"; tip.style.left = (e.clientX + 14) + "px"; tip.style.top = (e.clientY + 14) + "px";
      tip.textContent = [`${p.name} (${p.kind ?? ""})`, `親: ${p.parent_name ?? "-"}`, `輪郭 ${outerRing(p.polygon).length} 頂点`,
        p.environment ? `環境: ${p.environment}` : null].filter(Boolean).join("\n"); };
    g.onmouseleave = () => { tip.style.display = "none"; };
  });
  map.querySelectorAll(".pt").forEach(g => {
    const p = points.find(q => q.id === +g.dataset.id);
    g.onclick = () => { state.origin = state.origin === p.id ? null : p.id; render(); };
    g.onmousemove = e => { tip.style.display = "block"; tip.style.left = (e.clientX + 14) + "px"; tip.style.top = (e.clientY + 14) + "px";
      tip.textContent = [`${p.name} (${p.kind ?? ""})`, `親: ${p.parent_name ?? "-"}`, `lon ${p.lon} / lat ${p.lat} / alt ${p.alt ?? "-"}`,
        p.environment ? `環境: ${p.environment}` : null,
        [p.sample_region, p.sample_culture, p.sample_era].filter(Boolean).join(" / ") || null,
        (p.start || p.end) ? `期間: ${p.start ?? ""} 〜 ${p.end ?? ""}` : null].filter(Boolean).join("\n"); };
    g.onmouseleave = () => { tip.style.display = "none"; };
  });
}

function renderSide(planet, points, shapes) {
  const side = document.getElementById("side");
  const origin = points.find(p => p.id === state.origin);
  if (!origin) { side.innerHTML = `<p class="hint">点をクリックすると、そこから見た他の場所の距離と方角を出す。</p>` +
    `<p class="hint">経緯度を持つ場所 ${points.length} 件、輪郭(polygon)を持つ場所 ${shapes.length} 件。輪郭は薄い面として敷く。</p>`; return; }
  const rows = points.filter(p => p !== origin && !state.hidden.has(p.category)).map(p => {
    const deg = angular(origin, p), km = planet.radius_km ? rad(deg) * planet.radius_km : null, b = bearing(origin, p);
    const diff = (origin.alt != null && p.alt != null) ? p.alt - origin.alt : null;
    return { p, deg, km, b, diff };
  }).sort((a, b) => a.deg - b.deg);
  side.innerHTML = `<h2>${esc(origin.name)} <span class="hint">(${esc(origin.kind)} / ${esc(origin.parent_name ?? "-")})</span></h2>` +
    `<dl><dt>座標</dt><dd>lon ${origin.lon} / lat ${origin.lat} / alt ${origin.alt ?? "-"}</dd>` +
    (origin.environment ? `<dt>環境</dt><dd>${esc(origin.environment)}</dd>` : "") +
    `<dt>記事</dt><dd><a href="${esc(origin.link)}" target="_blank">GUI で開く</a></dd></dl>` +
    `<table><tr><th>場所</th><th>方角</th><th>距離</th><th>高低差</th></tr>` +
    rows.map(r => `<tr class="row" data-id="${r.p.id}"><td>${esc(r.p.name)}<br><span class="hint">${esc(r.p.parent_name ?? "")}</span></td>` +
      (r.deg < 0.01 ? `<td colspan="2">同じ経緯度</td>` : `<td>${bearingName(r.b)}<br><span class="hint">${Math.round(r.b)}°</span></td><td class="num">${distanceText(r.km, r.deg)}</td>`) + `<td>${altDiffText(r.diff)}</td></tr>`).join("") +
    `</table>`;
  side.querySelectorAll("tr.row").forEach(tr => { tr.onclick = () => { state.origin = +tr.dataset.id; render(); }; });
}

function render() {
  const { planet, points, shapes } = PLANETS[state.planet];
  renderTabs(); renderLayers(); renderMap(planet, points, shapes); renderSide(planet, points, shapes);
}
document.getElementById("zoom").oninput = e => { state.zoom = +e.target.value; document.getElementById("zoomv").textContent = state.zoom + "×"; render(); };
if (PLANETS.length) render(); else document.getElementById("map").innerHTML = '<p class="hint" style="padding:16px">経緯度も輪郭も持つ場所が無い。</p>';
</script>
</body>
</html>
"""


def render_html(planets: list[dict]) -> str:
    dump = lambda value: json.dumps(value, ensure_ascii=False).replace("</", "<\\/")
    return (_TEMPLATE
            .replace("__PLANETS__", dump(planets))
            .replace("__CATEGORIES__", dump(list(CATEGORIES)))
            .replace("__CATEGORY_COLORS__", dump(CATEGORY_COLORS))
            .replace("__SHAPE_OPACITY__", dump(SHAPE_OPACITY))
            .replace("__BEARINGS__", dump(list(BEARINGS))))
