"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import Marker from "@/components/MapMarker";
import NameId from "@/components/NameId";
import PageHelp from "@/components/PageHelp";
import Tooltip, { useTooltip } from "@/components/Tooltip";
import { getDetailMap, type DetailMapResponse, type MapLocation } from "@/lib/api";
import {
  altDiffText, altText, angular, bearing, bearingName, detailFrame, distanceKm, distanceText, locationLabels, MARGIN,
  outerRing, polygonCenter, scaleBar, type LonLat, type Polygon,
} from "@/lib/map";
import { PageTitle } from "@/lib/meta";
import { useOpenPage } from "@/lib/openPage";
import { T } from "@/lib/text";

type Point = MapLocation & { lon: number; lat: number };
type Shape = MapLocation & { polygon: Polygon };

const ROOT_COLOR = "#777";
// 開いた場所の輪郭を枠に入れる広さの上限(度)。町の輪郭は入れ、国や広い都市圏の輪郭は入れない
const ROOT_SHAPE_MAX_SPAN = 0.1;

const isPoint = (p: MapLocation): p is Point => p.lon != null && p.lat != null;
const isShape = (p: MapLocation): p is Shape => p.polygon != null;
const ringPoints = (p: Shape): LonLat[] => outerRing(p.polygon).map(([lon, lat]) => ({ lon, lat }));
const span = (ring: LonLat[]) =>
  Math.max(Math.max(...ring.map((q) => q.lon)) - Math.min(...ring.map((q) => q.lon)), Math.max(...ring.map((q) => q.lat)) - Math.min(...ring.map((q) => q.lat)));

export default function DetailMapPage() {
  const openPage = useOpenPage();
  const search = useSearchParams();
  const locationId = Number(search.get("location")) || null;
  // 場所の行から飛んできたとき。その場所を選んでおく
  const focus = Number(search.get("focus")) || null;
  const [data, setData] = useState<DetailMapResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<number | null>(null);
  const [zoom, setZoom] = useState(1);
  const { tip, show, hide } = useTooltip();

  useEffect(() => {
    if (locationId == null) return;
    getDetailMap(locationId)
      .then((result) => {
        setData(result);
        setSelected(focus);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [locationId, focus]);

  const root = data?.location ?? null;
  const places = useMemo(() => data?.places ?? [], [data]);
  const points = useMemo(() => places.filter(isPoint), [places]);
  const shapes = useMemo(() => places.filter(isShape), [places]);
  const rootPoint = root && isPoint(root) ? root : null;
  const rootShape = root && isShape(root) ? root : null;
  // 開いた場所の輪郭は国ほど広いことがあるので、詳細の場所が置ければ、狭い輪郭だけを枠に入れる
  const frame = useMemo(() => {
    const placed = [...points, ...shapes.flatMap(ringPoints)];
    if (rootPoint) placed.push(rootPoint);
    const rootRing = rootShape ? ringPoints(rootShape) : [];
    if (rootRing.length && (!placed.length || span(rootRing) <= ROOT_SHAPE_MAX_SPAN)) placed.push(...rootRing);
    return detailFrame(placed, zoom);
  }, [points, shapes, rootPoint, rootShape, zoom]);

  const graphRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = graphRef.current;
    const p = points.find((q) => q.id === selected);
    if (!el || !frame || !p) return;
    el.scrollTo({ left: frame.x(p.lon) - el.clientWidth / 2, top: frame.y(p.lat) - el.clientHeight / 2, behavior: "smooth" });
  }, [points, selected, frame]);

  if (locationId == null) return <div className="status info">{T.detailMap.noLocation}</div>;
  if (error) return <div className="status error">{error}</div>;
  if (!data || !root) return <div className="status info">{T.loading}</div>;

  const { categories, category_colors: colors, shape_opacity: opacity, bearings } = data;
  const order = (p: MapLocation) => categories.indexOf(p.category);
  const byOrder = (a: MapLocation, b: MapLocation) => order(a) - order(b) || a.id - b.id;
  const toggle = (name: string) => {
    const next = new Set(hidden);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    setHidden(next);
  };
  const radius = data.planet?.radius_km ?? null;
  const unplaced = places.filter((p) => !isPoint(p) && !isShape(p));
  const shown = points.filter((p) => !hidden.has(p.category));
  const chosen = selected === root.id ? root : places.find((p) => p.id === selected) ?? null;
  const chosenPoint = chosen && isPoint(chosen) ? chosen : null;
  const tipLines = (p: MapLocation) => [
    T.maps.nameKind(T.nameId(p.name, p.id), p.kind),
    T.maps.parent(p.parent_id == null ? null : T.nameId(p.parent_name, p.parent_id)),
    isPoint(p) ? T.maps.lonLatAlt(p.lon, p.lat, p.alt) : isShape(p) ? T.maps.polygonVertices(outerRing(p.polygon).length) : null,
    p.environment && T.maps.environment(p.environment),
    [p.sample_region, p.sample_culture, p.sample_era].filter(Boolean).join(" / "),
    (p.start || p.end) && T.maps.period(p.start, p.end),
  ];
  const detailLink = (p: MapLocation) =>
    p.id !== root.id &&
    p.detail_children > 0 && (
      <Link href={`/maps/detail?location=${p.id}`} className="button-link" title={T.detailMap.detailMapSub} onClick={(e) => e.stopPropagation()}>
        {T.detailMap.detailMap(p.detail_children)}
      </Link>
    );

  const rows = chosenPoint
    ? [...(rootPoint && chosenPoint !== rootPoint ? [rootPoint] : []), ...shown.filter((p) => p !== chosenPoint)]
        .map((p) => {
          const deg = angular(chosenPoint, p);
          return { p, deg, km: distanceKm(radius, deg), b: bearing(chosenPoint, p), diff: chosenPoint.alt != null && p.alt != null ? p.alt - chosenPoint.alt : null };
        })
        .sort((a, b) => a.deg - b.deg)
    : [];

  const children = new Map<number, MapLocation[]>();
  for (const p of places) {
    if (p.parent_id == null) continue;
    if (!children.has(p.parent_id)) children.set(p.parent_id, []);
    children.get(p.parent_id)!.push(p);
  }
  const tree = (parentId: number): ReactNode => {
    const items = children.get(parentId);
    if (!items?.length) return null;
    return (
      <ul className="tree">
        {items.map((p) => (
          <li key={p.id}>
            <div
              className={`detail-tree-item${selected === p.id ? " on" : ""}`}
              onClick={() => setSelected(selected === p.id ? null : p.id)}
              onDoubleClick={(e) => openPage(p.link, e)}
            >
              <span className="tree-name">
                <NameId name={p.name} id={p.id} />
              </span>
              <span className="tree-kind">{p.kind}</span>
              {!isPoint(p) && !isShape(p) && <span className="tree-meta">{T.detailMap.noCoordinates}</span>}
              {detailLink(p)}
            </div>
            {tree(p.id)}
          </li>
        ))}
      </ul>
    );
  };

  const overallHref = data.overall_id == null ? "/maps" : `/maps?location=${data.overall_id}`;
  const upId = root.detail && root.parent_id != null ? root.parent_id : null;

  return (
    <div className="page-fill viz">
      <PageTitle kind={T.detailMap.title} record={T.nameId(root.name, root.id)} />
      <div className="toolbar">
        <h1 style={{ margin: 0 }}>{T.detailMap.of(T.nameId(root.name, root.id))}</h1>
        <PageHelp page={T.detailMap.title} help={T.help.detailMap} />
        <button type="button" onClick={(e) => openPage(root.link, e)}>
          {T.openRecord}
        </button>
        {upId != null && (
          <Link href={`/maps/detail?location=${upId}&focus=${root.id}`} className="hint">
            {T.detailMap.up(T.nameId(root.parent_name, upId))}
          </Link>
        )}
        <Link href={overallHref} className="hint">
          {T.maps.fullMap}
        </Link>
        <span className="layers">
          {categories.map((name) => (
            <label key={name}>
              <input type="checkbox" checked={!hidden.has(name)} onChange={() => toggle(name)} />
              <svg width="12" height="12">
                <Marker category={name} x={6} y={6} r={5} color={colors[name]} />
              </svg>
              {name}
            </label>
          ))}
        </span>
        <label className="hint">
          {T.zoom} <input type="range" min="0.5" max="4" step="0.25" value={zoom} onChange={(e) => setZoom(Number(e.target.value))} /> {zoom}×
        </label>
      </div>
      {!places.length && <div className="status info">{T.detailMap.noneAtAll}</div>}
      {places.length > 0 && !points.length && !shapes.length && <div className="status info">{T.detailMap.nonePlaced}</div>}
      <div className="viz-body">
        <div className="viz-graph" ref={graphRef}>
          {frame && detailSvg()}
        </div>
        <aside className="viz-side">
          {chosen ? (
            <>
              <div className="viz-head">
                <h2>
                  <NameId name={chosen.name} id={chosen.id} />{" "}
                  <span className="hint">
                    ({chosen.kind} / {chosen.parent_id == null ? "-" : T.nameId(chosen.parent_name, chosen.parent_id)})
                  </span>
                </h2>
                <button type="button" className="primary" onClick={(e) => openPage(chosen.link, e)}>
                  {T.openRecord}
                </button>
              </div>
              {chosen.id !== root.id && chosen.detail_children > 0 && <p className="viz-jump">{detailLink(chosen)}</p>}
              <dl>
                <dt>{T.maps.coordinates}</dt>
                <dd>{chosenPoint ? T.maps.lonLatAlt(chosenPoint.lon, chosenPoint.lat, chosenPoint.alt) : isShape(chosen) ? T.maps.polygonVertices(outerRing(chosen.polygon).length) : T.detailMap.noCoordinates}</dd>
                {chosen.environment && (
                  <>
                    <dt>{T.maps.environmentDt}</dt>
                    <dd>{chosen.environment}</dd>
                  </>
                )}
                {(chosen.sample_region || chosen.sample_culture || chosen.sample_era) && (
                  <>
                    <dt>{T.detailMap.sample}</dt>
                    <dd>{[chosen.sample_region, chosen.sample_culture, chosen.sample_era].filter(Boolean).join(" / ")}</dd>
                  </>
                )}
              </dl>
              {rows.length > 0 && (
                <table>
                  <thead>
                    <tr>
                      <th>{T.maps.columns.location}</th>
                      <th>{T.maps.columns.bearing}</th>
                      <th>{T.maps.columns.distance}</th>
                      <th>{T.maps.columns.elevationDiff}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.p.id} className="row" onClick={() => setSelected(r.p.id)}>
                        <td>
                          <NameId name={r.p.name} id={r.p.id} />
                        </td>
                        {r.deg < 1e-6 ? (
                          <td colSpan={2}>{T.maps.sameCoordinates}</td>
                        ) : (
                          <>
                            <td>
                              {bearingName(bearings, r.b)}
                              <br />
                              <span className="hint">{Math.round(r.b)}°</span>
                            </td>
                            <td className="num">{distanceText(r.km, r.deg)}</td>
                          </>
                        )}
                        <td>{altDiffText(r.diff)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          ) : (
            <p className="hint" title={T.detailMap.hintClick}>
              {T.detailMap.counts(points.length, shapes.length, unplaced.length)} {T.detailMap.hintClick}
            </p>
          )}
          {places.length > 0 && (
            <>
              <h2 className="detail-tree-head">{T.detailMap.places}</h2>
              {tree(root.id)}
            </>
          )}
        </aside>
      </div>
      <Tooltip tip={tip} />
    </div>
  );

  function detailSvg() {
    if (!frame || !root) return null;
    const X = frame.x, Y = frame.y;
    // 枠の端の点の名は枠の外へはみ出すので、右に名の幅ほどの余白を取る
    const W = MARGIN.left + frame.width + 160;
    const H = MARGIN.top + frame.height + MARGIN.bottom;
    // 同じ経緯度に重なる点は印を大きくし、ラベルを下へ積む
    const groups = new Map<string, Point[]>();
    for (const p of [...shown].sort(byOrder)) {
      const k = `${p.lon},${p.lat}`;
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k)!.push(p);
    }
    const drawn: [Point, number, number, number][] = [];
    for (const members of groups.values()) members.forEach((p, i) => drawn.push([p, X(p.lon), Y(p.lat), i]));
    const labeled: [MapLocation, number, number, number][] = rootPoint ? [[rootPoint, X(rootPoint.lon), Y(rootPoint.lat), 0], ...drawn] : drawn;
    const labels = locationLabels(labeled.map(([p, x, y, i]) => [x, y + 12 * i, T.nameId(p.name, p.id) + altText(p.alt)]));
    const pointIds = new Set(points.map((p) => p.id));
    const bar = scaleBar(frame, radius);
    const barX = X(frame.lonMin) + 14, barY = Y(frame.latMin) - 16;
    const barLabel = bar.meters == null ? T.detailMap.scaleDeg(bar.degrees) : bar.meters >= 1000 ? T.detailMap.scaleKm(bar.meters / 1000) : T.detailMap.scaleM(bar.meters);
    return (
      <svg xmlns="http://www.w3.org/2000/svg" width={W} height={H} fontSize={11}>
        <defs>
          <clipPath id="detail-plot">
            <rect x={X(frame.lonMin)} y={Y(frame.latMax)} width={frame.width} height={frame.height} />
          </clipPath>
        </defs>
        <rect width={W} height={H} fill="#fdfcf8" />
        <rect x={X(frame.lonMin)} y={Y(frame.latMax)} width={frame.width} height={frame.height} fill="#eef3f7" stroke="#999" />
        <text x={MARGIN.left} y={24} fontSize={18} fontWeight="bold">{T.nameId(root.name, root.id)}</text>
        <text x={MARGIN.left + 40 + T.nameId(root.name, root.id).length * 18} y={24} fill="#555">
          {data?.planet ? `${T.nameId(data.planet.name, data.planet.id)} / ` : ""}
          {radius ? T.maps.radius(radius) : T.detailMap.scaleUnknown}
        </text>
        {/* 開いた場所の輪郭は枠より広いことがあるので、面だけを枠で切る。点は枠の中にあり、名は枠の外へはみ出してよい */}
        <g clipPath="url(#detail-plot)">
          {rootShape && (
            <path
              d={rootShape.polygon.coordinates.map((ring) => ring.map(([lon, lat], i) => `${i ? "L" : "M"}${X(lon)},${Y(lat)}`).join(" ") + " Z").join(" ")}
              fill="none"
              stroke={ROOT_COLOR}
              strokeWidth={1.5}
              strokeDasharray="6 4"
              fillRule="evenodd"
            />
          )}
          {shapes
            .filter((p) => !hidden.has(p.category))
            .sort(byOrder)
            .map((p) => {
              const color = colors[p.category];
              const d = p.polygon.coordinates.map((ring) => ring.map(([lon, lat], i) => `${i ? "L" : "M"}${X(lon)},${Y(lat)}`).join(" ") + " Z").join(" ");
              const [cx, cy] = polygonCenter(p.polygon);
              return (
                <g
                  key={`shape${p.id}`}
                  style={{ cursor: "pointer" }}
                  onClick={() => setSelected(selected === p.id ? null : p.id)}
                  onDoubleClick={(e) => openPage(p.link, e)}
                  onMouseMove={(e) => show(e, tipLines(p))}
                  onMouseLeave={hide}
                >
                  <path d={d} fill={color} fillOpacity={selected === p.id ? 0.45 : opacity[p.category]} fillRule="evenodd" stroke={color} strokeWidth={selected === p.id ? 2.5 : 1.2} strokeLinejoin="round" />
                  {!pointIds.has(p.id) && (
                    <text x={X(cx)} y={Y(cy)} textAnchor="middle" fontSize={13} fontWeight="bold" fill={color} fillOpacity={0.8} pointerEvents="none">
                      {T.nameId(p.name, p.id)}
                    </text>
                  )}
                </g>
              );
            })}
        </g>
        <g>
          {chosenPoint &&
            rows.map(({ p }) => (
              <line key={`ray${p.id}`} x1={X(chosenPoint.lon)} y1={Y(chosenPoint.lat)} x2={X(p.lon)} y2={Y(p.lat)} stroke="#333" strokeWidth={0.5} strokeDasharray="3 3" />
            ))}
          {labeled.map(([p, x, y, i], n) => {
            const isRoot = p.id === root.id;
            const color = isRoot ? ROOT_COLOR : colors[p.category];
            const sel = selected === p.id;
            const [lx, ly, anchor] = labels[n];
            return (
              <g
                key={`pt${p.id}`}
                style={{ cursor: "pointer" }}
                onClick={() => setSelected(sel ? null : p.id)}
                onDoubleClick={(e) => openPage(p.link, e)}
                onMouseMove={(e) => show(e, tipLines(p))}
                onMouseLeave={hide}
              >
                <Marker category={p.category} x={x} y={y} r={(sel ? 7 : isRoot ? 6 : 4) + 2 * i} color={color} strokeWidth={sel ? 2.5 : 1} />
                <text x={lx} y={ly} textAnchor={anchor} fill={color} stroke="#fdfcf8" strokeWidth={3} paintOrder="stroke" fontWeight={sel || isRoot ? "bold" : "normal"}>
                  {T.nameId(p.name, p.id)}
                  {altText(p.alt)}
                </text>
              </g>
            );
          })}
        </g>
        <g pointerEvents="none">
          <line x1={barX} y1={barY} x2={barX + bar.px} y2={barY} stroke="#333" strokeWidth={2} />
          <line x1={barX} y1={barY - 5} x2={barX} y2={barY + 5} stroke="#333" strokeWidth={1.5} />
          <line x1={barX + bar.px} y1={barY - 5} x2={barX + bar.px} y2={barY + 5} stroke="#333" strokeWidth={1.5} />
          <text x={barX + bar.px / 2} y={barY - 8} textAnchor="middle" fill="#333" stroke="#eef3f7" strokeWidth={3} paintOrder="stroke">
            {barLabel}
          </text>
        </g>
      </svg>
    );
  }
}
