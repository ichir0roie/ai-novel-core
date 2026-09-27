"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Tooltip, { useTooltip } from "@/components/Tooltip";
import { getRelations, type Relation, type RelationCharacter, type RelationsResponse } from "@/lib/api";
import { PageTitle } from "@/lib/meta";
import { openInNewTab } from "@/lib/nav";
import { T } from "@/lib/text";

const R_NODE = 18;
const BASE = 720;

type Pos = { x: number; y: number };
type Positions = Record<number, Pos>;
type Selected = { type: "character"; id: number } | { type: "relation"; id: number } | null;
type Span = { start?: number | null; end?: number | null };

const spanText = (o: Span) => T.span(o.start, o.end);
const inYear = (o: Span, y: number | null) => y == null || ((o.start == null || o.start <= y) && (o.end == null || o.end > y));
const firstLine = (t: string | null | undefined) => (t ?? "").split("\n").find((l) => l.trim()) ?? "";

/** 円に並べてから、繋がりのある同士を寄せ、無い同士を離す簡単な力学配置。 */
function layout(characters: RelationCharacter[], relations: Relation[]): Positions {
  const n = characters.length, cx = BASE / 2, cy = BASE / 2, r = BASE / 2 - 80;
  const pos: Positions = {};
  characters.forEach((c, i) => {
    pos[c.id] = { x: cx + r * Math.cos((2 * Math.PI * i) / n - Math.PI / 2), y: cy + r * Math.sin((2 * Math.PI * i) / n - Math.PI / 2) };
  });
  const linked = new Set(relations.map((e) => `${e.character_id_1}:${e.character_id_2}`));
  const isLinked = (a: number, b: number) => linked.has(`${a}:${b}`) || linked.has(`${b}:${a}`);
  for (let step = 0; step < 300; step++) {
    const force: Positions = {};
    for (const c of characters) force[c.id] = { x: 0, y: 0 };
    for (const a of characters)
      for (const b of characters) {
        if (a.id >= b.id) continue;
        const pa = pos[a.id], pb = pos[b.id];
        const dx = pb.x - pa.x, dy = pb.y - pa.y, d = Math.max(1, Math.hypot(dx, dy));
        let f = 20000 / (d * d);
        if (isLinked(a.id, b.id)) f -= (d - 160) * 0.05;
        force[a.id].x -= (f * dx) / d;
        force[a.id].y -= (f * dy) / d;
        force[b.id].x += (f * dx) / d;
        force[b.id].y += (f * dy) / d;
      }
    for (const c of characters) {
      const p = pos[c.id], f = force[c.id];
      p.x += (cx - p.x) * 0.01 + Math.max(-8, Math.min(8, f.x));
      p.y += (cy - p.y) * 0.01 + Math.max(-8, Math.min(8, f.y));
      p.x = Math.min(BASE - 60, Math.max(60, p.x));
      p.y = Math.min(BASE - 60, Math.max(60, p.y));
    }
  }
  return pos;
}

/** 一人の人物に絞る。その人物と、関係で直接つながる相手、その間の関係だけを残す。 */
function scopeTo(data: RelationsResponse, focus: number): RelationsResponse {
  const relations = data.relations.filter((r) => r.character_id_1 === focus || r.character_id_2 === focus);
  const ids = new Set([focus, ...relations.flatMap((r) => [r.character_id_1, r.character_id_2])]);
  return { ...data, characters: data.characters.filter((c) => ids.has(c.id)), relations };
}

function edgePath(a: Pos, b: Pos, bend: number) {
  const dx = b.x - a.x, dy = b.y - a.y, d = Math.max(1, Math.hypot(dx, dy));
  const nx = -dy / d, ny = dx / d;
  const mx = (a.x + b.x) / 2 + nx * bend, my = (a.y + b.y) / 2 + ny * bend;
  const ex = b.x - (dx / d) * (R_NODE + 4), ey = b.y - (dy / d) * (R_NODE + 4);
  return { d: `M${a.x},${a.y} Q${mx},${my} ${ex},${ey}`, lx: (a.x + 2 * mx + b.x) / 4, ly: (a.y + 2 * my + b.y) / 4 };
}

export default function RelationsPage() {
  const search = useSearchParams();
  // 人物の詳細から飛んできたとき。その人物に関わる関係だけを描く
  const focus = Number(search.get("character")) || null;
  const [data, setData] = useState<RelationsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<Selected>(null);
  const [zoom, setZoom] = useState(1);
  const [pos, setPos] = useState<Positions>({});
  const [year, setYear] = useState<number | null>(null);
  const [yearInput, setYearInput] = useState(0);
  const drag = useRef<{ id: number; x: number; y: number; moved: boolean } | null>(null);
  const { tip, show, hide } = useTooltip();

  useEffect(() => {
    getRelations()
      .then((all) => {
        const result = focus == null ? all : scopeTo(all, focus);
        setData(result);
        setPos(layout(result.characters, result.relations));
        setSelected(focus == null ? null : { type: "character", id: focus });
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [focus]);

  const years = useMemo(() => (data ? [...data.relations, ...data.characters].flatMap((o) => [o.start, o.end]).filter((y): y is number => y != null) : []), [data]);
  const yearMin = years.length ? Math.min(...years) : 0;
  const yearMax = years.length ? Math.max(...years) : 0;
  useEffect(() => setYearInput(yearMin), [yearMin]);

  const onMouseMove = useCallback(
    (e: globalThis.MouseEvent) => {
      const d = drag.current;
      if (!d) return;
      setPos((prev) => ({ ...prev, [d.id]: { x: prev[d.id].x + (e.clientX - d.x) / zoom, y: prev[d.id].y + (e.clientY - d.y) / zoom } }));
      d.x = e.clientX;
      d.y = e.clientY;
      d.moved = true;
    },
    [zoom],
  );
  const onMouseUp = useCallback(() => {
    const d = drag.current;
    if (!d) return;
    drag.current = null;
    if (!d.moved) setSelected((s) => (s?.type === "character" && s.id === d.id ? null : { type: "character", id: d.id }));
  }, []);
  useEffect(() => {
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
    return () => {
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    };
  }, [onMouseMove, onMouseUp]);

  const focusName = focus == null ? null : data?.characters.find((c) => c.id === focus)?.name ?? T.relations.unknownId(focus);

  if (error) return <div className="status error">{error}</div>;
  if (!data) return <div className="status info">{T.loading}</div>;

  const byId = new Map(data.characters.map((c) => [c.id, c]));
  const nameOf = (id: number) => byId.get(id)?.name ?? `id=${id}`;
  const kinds = [...new Set(data.characters.map((c) => c.kind ?? ""))];
  const colorOf = Object.fromEntries(kinds.map((k, i) => [k, data.colors[i % data.colors.length]]));
  const chars = data.characters.filter((c) => !hidden.has(c.kind ?? "") && inYear(c, year));
  const shownIds = new Set(chars.map((c) => c.id));
  const rels = data.relations.filter((r) => shownIds.has(r.character_id_1) && shownIds.has(r.character_id_2) && inYear(r, year));
  const selectedRelation = selected?.type === "relation" ? data.relations.find((r) => r.id === selected.id) ?? null : null;
  const related = new Set<number>();
  if (selected?.type === "character") for (const r of rels) if (r.character_id_1 === selected.id || r.character_id_2 === selected.id) related.add(r.id);

  const toggle = (k: string) => {
    const next = new Set(hidden);
    if (next.has(k)) next.delete(k);
    else next.add(k);
    setHidden(next);
  };
  const pickRelation = (r: Relation) => setSelected((s) => (s?.type === "relation" && s.id === r.id ? null : { type: "relation", id: r.id }));

  const z = zoom, W = BASE * z, H = BASE * z;
  const pairKey = (r: Relation) => [r.character_id_1, r.character_id_2].sort((a, b) => a - b).join(":");
  const pairCount = new Map<string, number>();
  for (const r of rels) pairCount.set(pairKey(r), (pairCount.get(pairKey(r)) ?? 0) + 1);
  const seen = new Map<string, number>();

  const relationRow = (r: Relation, from: number | null) => {
    const other = from == null ? null : r.character_id_1 === from ? r.character_id_2 : r.character_id_1;
    return (
      <tr key={r.id} className="row" onClick={() => setSelected({ type: "relation", id: r.id })}>
        {from == null ? (
          <>
            <td>{nameOf(r.character_id_1)}</td>
            <td>{r.relation} →</td>
            <td>{nameOf(r.character_id_2)}</td>
          </>
        ) : (
          <>
            <td>{r.character_id_1 === from ? "→" : "←"}</td>
            <td>{nameOf(other!)}</td>
            <td>{r.relation}</td>
          </>
        )}
        <td className="hint">{spanText(r)}</td>
        <td className="hint">{firstLine(r.text)}</td>
      </tr>
    );
  };

  const side = () => {
    if (!selected) {
      return (
        <>
          <p className="hint">{T.relations.hintClick}</p>
          <p className="hint">
            {T.relations.hintCounts(chars.length, rels.length, year)}
          </p>
          {rels.length > 0 && (
            <table>
              <thead>
                <tr>
                  <th>{T.relations.columns.subject}</th>
                  <th>{T.relations.columns.relation}</th>
                  <th>{T.relations.columns.target}</th>
                  <th>{T.relations.columns.period}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {rels.map((r) => relationRow(r, null))}
              </tbody>
            </table>
          )}
        </>
      );
    }
    if (selected.type === "character") {
      const c = byId.get(selected.id);
      if (!c) return null;
      const mine = rels.filter((r) => r.character_id_1 === c.id || r.character_id_2 === c.id);
      return (
        <>
          <div className="viz-head">
            <h2>
              {c.name} <span className="hint">({c.kind ?? ""})</span>
            </h2>
            <button type="button" className="primary" onClick={() => openInNewTab(c.link)}>
              {T.openRecord}
            </button>
          </div>
          <dl>
            {c.sex && (
              <>
                <dt>{T.relations.sex}</dt>
                <dd>{c.sex}</dd>
              </>
            )}
            {spanText(c) && (
              <>
                <dt>{T.relations.period}</dt>
                <dd>{spanText(c)}</dd>
              </>
            )}
          </dl>
          {mine.length ? (
            <table>
              <thead>
                <tr>
                  <th></th>
                  <th>{T.relations.columns.target}</th>
                  <th>{T.relations.columns.relation}</th>
                  <th>{T.relations.columns.period}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {mine.map((r) => relationRow(r, c.id))}
              </tbody>
            </table>
          ) : (
            <p className="hint">{T.relations.noRelations}</p>
          )}
        </>
      );
    }
    if (!selectedRelation) return null;
    const r = selectedRelation;
    return (
      <>
        <div className="viz-head">
          <h2>
            {nameOf(r.character_id_1)} → {nameOf(r.character_id_2)}
          </h2>
          <button type="button" className="primary" onClick={() => openInNewTab(`/tables/character_relation/${r.id}`)}>
            {T.openRecord}
          </button>
        </div>
        <dl>
          <dt>{T.relations.relation}</dt>
          <dd>{r.relation}</dd>
          {spanText(r) && (
            <>
              <dt>{T.relations.period}</dt>
              <dd>{spanText(r)}</dd>
            </>
          )}
        </dl>
        <div className="text">{r.text || <span className="hint">{T.relations.noText}</span>}</div>
      </>
    );
  };

  return (
    <div className="page-fill viz">
      <PageTitle kind={T.relations.title} record={focusName} />
      <div className="toolbar">
        <h1 style={{ margin: 0 }}>{focus == null ? T.relations.title : T.relations.of(byId.get(focus)?.name ?? T.relations.unknownId(focus))}</h1>
        {focus != null && (
          <Link href="/relations" target="_blank" rel="noopener noreferrer" className="hint">
            {T.relations.fullGraph}
          </Link>
        )}
        <span className="layers">
          {kinds.map((k) => (
            <label key={k}>
              <input type="checkbox" checked={!hidden.has(k)} onChange={() => toggle(k)} />
              <span className="swatch" style={{ background: colorOf[k] }} />
              {k || T.relations.noKind}
            </label>
          ))}
        </span>
        <label className="hint">
          {T.zoom} <input type="range" min="0.5" max="3" step="0.25" value={zoom} onChange={(e) => setZoom(Number(e.target.value))} /> {zoom}×
        </label>
        {years.length > 0 && (
          <label className="hint">
            {T.relations.year}{" "}
            <input
              type="number"
              min={yearMin}
              max={yearMax}
              value={yearInput}
              style={{ width: "7em" }}
              onChange={(e) => {
                setYearInput(Number(e.target.value));
                setYear(Number(e.target.value));
              }}
            />{" "}
            <label>
              <input type="checkbox" checked={year == null} onChange={(e) => setYear(e.target.checked ? null : yearInput)} />
              {T.relations.allTime}
            </label>
          </label>
        )}
        <button type="button" onClick={() => setPos(layout(data.characters, data.relations))}>
          {T.relations.relayout}
        </button>
      </div>
      {data.characters.length === 0 ? (
        <div className="status info">{focus == null ? T.relations.noCharacters : T.relations.noCharacter(focus)}</div>
      ) : (
        <div className="viz-body">
          <div className="viz-graph">
            <svg xmlns="http://www.w3.org/2000/svg" width={W} height={H} fontSize={11 * z}>
              <defs>
                <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
                  <path d="M0,0 L10,5 L0,10 z" fill="#555" />
                </marker>
                <marker id="arrow-on" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
                  <path d="M0,0 L10,5 L0,10 z" fill="#c0392b" />
                </marker>
              </defs>
              <rect width={W} height={H} fill="#fdfcf8" />
              {rels.map((r) => {
                const a = pos[r.character_id_1], b = pos[r.character_id_2];
                if (!a || !b) return null;
                const k = pairKey(r);
                const i = seen.get(k) ?? 0;
                seen.set(k, i + 1);
                const total = pairCount.get(k) ?? 1;
                const bend = (i - (total - 1) / 2) * 40 * (r.character_id_1 < r.character_id_2 ? 1 : -1);
                const e = edgePath({ x: a.x * z, y: a.y * z }, { x: b.x * z, y: b.y * z }, bend * z);
                const on = selected?.type === "relation" ? selected.id === r.id : related.has(r.id);
                const dim = selected && !on;
                return (
                  <g
                    key={`rel${r.id}`}
                    style={{ cursor: "pointer" }}
                    opacity={dim ? 0.25 : 1}
                    onClick={() => pickRelation(r)}
                    onDoubleClick={() => openInNewTab(`/tables/character_relation/${r.id}`)}
                    onMouseMove={(ev) => show(ev, [T.relations.arrow(nameOf(r.character_id_1), nameOf(r.character_id_2), r.relation), spanText(r) && T.relations.periodOf(spanText(r)), firstLine(r.text)])}
                    onMouseLeave={hide}
                  >
                    <path d={e.d} fill="none" stroke="transparent" strokeWidth={12} />
                    <path d={e.d} fill="none" stroke={on ? "#c0392b" : "#555"} strokeWidth={on ? 2.2 : 1.2} markerEnd={`url(#${on ? "arrow-on" : "arrow"})`} />
                    <text x={e.lx} y={e.ly} textAnchor="middle" fill={on ? "#c0392b" : "#333"} stroke="#fdfcf8" strokeWidth={3} paintOrder="stroke" fontWeight={on ? "bold" : "normal"}>
                      {r.relation}
                    </text>
                  </g>
                );
              })}
              {chars.map((c) => {
                const p = pos[c.id];
                if (!p) return null;
                const on = selected?.type === "character" && selected.id === c.id;
                const touched = selectedRelation != null && (selectedRelation.character_id_1 === c.id || selectedRelation.character_id_2 === c.id);
                return (
                  <g
                    key={`chr${c.id}`}
                    style={{ cursor: "pointer" }}
                    onMouseDown={(ev) => {
                      drag.current = { id: c.id, x: ev.clientX, y: ev.clientY, moved: false };
                      ev.preventDefault();
                    }}
                    onDoubleClick={() => openInNewTab(c.link)}
                    onMouseMove={(ev) => show(ev, [T.relations.nameKind(c.name, c.kind), c.sex && T.relations.sexOf(c.sex), spanText(c) && T.relations.periodOf(spanText(c))])}
                    onMouseLeave={hide}
                  >
                    <circle cx={p.x * z} cy={p.y * z} r={R_NODE * z} fill={colorOf[c.kind ?? ""]} stroke={on || touched ? "#222" : "#fff"} strokeWidth={on || touched ? 3 : 1.5} />
                    <text x={p.x * z} y={(p.y + R_NODE + 14) * z} textAnchor="middle" fill="#222" stroke="#fdfcf8" strokeWidth={3} paintOrder="stroke" fontSize={12 * z} fontWeight={on ? "bold" : "normal"}>
                      {c.name}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>
          <aside className="viz-side">{side()}</aside>
        </div>
      )}
      <Tooltip tip={tip} />
    </div>
  );
}
