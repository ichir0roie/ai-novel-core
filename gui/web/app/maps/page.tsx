"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import Tooltip, { useTooltip } from "@/components/Tooltip";
import { getMaps, type MapPlace, type MapsResponse } from "@/lib/api";
import { PageTitle } from "@/lib/meta";
import {
  altDiffText, altText, angular, bearing, bearingName, distanceKm, distanceText, fitFrame, MARGIN, outerRing,
  placeLabels, polygonCenter, type Polygon,
} from "@/lib/map";
import { T } from "@/lib/text";

type Point = MapPlace & { lon: number; lat: number };
type Shape = MapPlace & { polygon: Polygon };

function Marker({ category, x, y, r, color, strokeWidth = 1 }: { category: string; x: number; y: number; r: number; color: string; strokeWidth?: number }) {
  const common = { fill: color, stroke: "#fff", strokeWidth };
  if (category === "国") return <circle cx={x} cy={y} r={r} {...common} />;
  if (category === "都市") return <rect x={x - r} y={y - r} width={2 * r} height={2 * r} {...common} />;
  if (category === "自然") return <path d={`M${x},${y - r * 1.2} L${x + r * 1.1},${y + r * 0.8} L${x - r * 1.1},${y + r * 0.8} Z`} {...common} />;
  return <path d={`M${x},${y - r} L${x + r},${y} L${x},${y + r} L${x - r},${y} Z`} {...common} />;
}

export default function MapsPage() {
  const router = useRouter();
  const search = useSearchParams();
  // 場所の詳細から飛んできたとき。その場所の星を選び、その場所を中心に置いて描く
  const focus = Number(search.get("location")) || null;
  const [data, setData] = useState<MapsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [planetIndex, setPlanetIndex] = useState(0);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [origin, setOrigin] = useState<number | null>(null);
  const [zoom, setZoom] = useState(1);
  const { tip, show, hide } = useTooltip();

  useEffect(() => {
    getMaps()
      .then((result) => {
        setData(result);
        if (focus == null) return;
        const index = result.planets.findIndex((pl) => [...pl.points, ...pl.shapes].some((p) => p.id === focus));
        if (index < 0) return;
        setPlanetIndex(index);
        if (result.planets[index].points.some((p) => p.id === focus)) setOrigin(focus);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [focus]);

  const entry = data?.planets[planetIndex] ?? null;
  const points = useMemo(() => (entry?.points ?? []).filter((p): p is Point => p.lon != null && p.lat != null), [entry]);
  const shapes = useMemo(() => (entry?.shapes ?? []).filter((p): p is Shape => p.polygon != null), [entry]);
  // 中心に置く場所。経緯度があればそれ、輪郭だけなら輪郭の重心
  const center = useMemo(() => {
    if (focus == null) return null;
    const point = points.find((p) => p.id === focus);
    if (point) return { lon: point.lon, lat: point.lat };
    const shape = shapes.find((p) => p.id === focus);
    if (!shape) return null;
    const [lon, lat] = polygonCenter(shape.polygon);
    return { lon, lat };
  }, [focus, points, shapes]);
  const focusPlace = focus == null ? null : [...points, ...shapes].find((p) => p.id === focus) ?? null;
  const frame = useMemo(() => fitFrame(points, shapes, zoom, center), [points, shapes, zoom, center]);

  if (error) return <div className="status error">{error}</div>;
  if (!data) return <div className="status info">{T.loading}</div>;

  const { categories, category_colors: colors, shape_opacity: opacity, bearings } = data;
  const order = (p: MapPlace) => categories.indexOf(p.category);
  const byOrder = (a: MapPlace, b: MapPlace) => order(a) - order(b) || a.id - b.id;
  const selectPlanet = (i: number) => {
    setPlanetIndex(i);
    setHidden(new Set());
    setOrigin(null);
  };
  const toggle = (name: string) => {
    const next = new Set(hidden);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    setHidden(next);
  };

  const X = frame.x, Y = frame.y;
  const W = MARGIN.left + (frame.lonMax - frame.lonMin) * frame.scale + MARGIN.right;
  const H = MARGIN.top + (frame.latMax - frame.latMin) * frame.scale + MARGIN.bottom;
  const lons: number[] = [], lats: number[] = [];
  for (let lon = frame.lonMin; lon <= frame.lonMax; lon += frame.step) lons.push(lon);
  for (let lat = frame.latMin; lat <= frame.latMax; lat += frame.step) lats.push(lat);
  const pointIds = new Set(points.map((p) => p.id));
  const shown = points.filter((p) => !hidden.has(p.category));
  const originPoint = shown.find((p) => p.id === origin) ?? null;
  // 同じ経緯度に重なる点は印を大きくし、ラベルを下へ積む
  const groups = new Map<string, Point[]>();
  for (const p of [...shown].sort(byOrder)) {
    const k = `${p.lon},${p.lat}`;
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k)!.push(p);
  }
  const drawn: [Point, number, number, number][] = [];
  for (const members of groups.values()) members.forEach((p, i) => drawn.push([p, X(p.lon), Y(p.lat), i]));
  const labels = placeLabels(drawn.map(([p, x, y, i]) => [x, y + 12 * i, (p.name ?? "") + altText(p.alt)]));
  const radius = entry?.planet.radius_km ?? null;

  const rows = originPoint
    ? shown
        .filter((p) => p !== originPoint)
        .map((p) => {
          const deg = angular(originPoint, p);
          return { p, deg, km: distanceKm(radius, deg), b: bearing(originPoint, p), diff: originPoint.alt != null && p.alt != null ? p.alt - originPoint.alt : null };
        })
        .sort((a, b) => a.deg - b.deg)
    : [];

  return (
    <div className="page-fill viz">
      <PageTitle kind={T.maps.title} record={focusPlace?.name} />
      <div className="toolbar">
        <h1 style={{ margin: 0 }}>{focusPlace ? T.maps.centeredOn(focusPlace.name ?? "") : T.maps.title}</h1>
        {focus != null && (
          <>
            {focusPlace && (
              <button type="button" onClick={() => router.push(focusPlace.link)}>
                {T.openRecord}
              </button>
            )}
            <Link href="/maps" className="hint">
              {T.maps.fullMap}
            </Link>
          </>
        )}
        {data.planets.length > 1 && (
          <span className="segment">
            {data.planets.map((pl, i) => (
              <button key={pl.planet.id} type="button" className={i === planetIndex ? "on" : ""} onClick={() => selectPlanet(i)}>
                {pl.planet.name}
              </button>
            ))}
          </span>
        )}
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
      {focus != null && !focusPlace && (
        <div className="status info">
          {T.maps.cannotPlace(focus)}<Link href={`/tables/location/${focus}`}>{T.openRecord}</Link>
        </div>
      )}
      {!entry ? (
        <div className="status info">{T.maps.nonePlaceable}</div>
      ) : (
        <div className="viz-body">
          <div className="viz-graph">
            <svg xmlns="http://www.w3.org/2000/svg" width={W} height={H} fontSize={11}>
              <rect width={W} height={H} fill="#fdfcf8" />
              <rect x={X(frame.lonMin)} y={Y(frame.latMax)} width={(frame.lonMax - frame.lonMin) * frame.scale} height={(frame.latMax - frame.latMin) * frame.scale} fill="#eef3f7" stroke="#999" />
              {lons.map((lon) => (
                <g key={`lon${lon}`}>
                  <line x1={X(lon)} y1={Y(frame.latMax)} x2={X(lon)} y2={Y(frame.latMin)} stroke={lon ? "#c8d0d8" : "#666"} strokeWidth={lon ? 0.6 : 1.2} />
                  <text x={X(lon)} y={Y(frame.latMin) + 14} textAnchor="middle" fill="#555">{lon}°</text>
                </g>
              ))}
              {lats.map((lat) => (
                <g key={`lat${lat}`}>
                  <line x1={X(frame.lonMin)} y1={Y(lat)} x2={X(frame.lonMax)} y2={Y(lat)} stroke={lat ? "#c8d0d8" : "#666"} strokeWidth={lat ? 0.6 : 1.2} />
                  <text x={X(frame.lonMin) - 6} y={Y(lat) + 4} textAnchor="end" fill="#555">{lat}°</text>
                </g>
              ))}
              <text x={MARGIN.left} y={24} fontSize={18} fontWeight="bold">{entry.planet.name}</text>
              <text x={MARGIN.left + 40 + (entry.planet.name?.length ?? 0) * 18} y={24} fill="#555">
                {radius ? T.maps.radius(radius) : T.maps.radiusUnknown}
              </text>
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
                      onMouseMove={(e) => show(e, [T.maps.nameKind(p.name, p.kind), T.maps.parent(p.parent_name), T.maps.polygonVertices(outerRing(p.polygon).length), p.environment && T.maps.environment(p.environment)])}
                      onMouseLeave={hide}
                    >
                      <path d={d} fill={color} fillOpacity={opacity[p.category]} fillRule="evenodd" stroke={color} strokeWidth={1.2} strokeLinejoin="round" />
                      {!pointIds.has(p.id) && (
                        <text x={X(cx)} y={Y(cy)} textAnchor="middle" fontSize={13} fontWeight="bold" fill={color} fillOpacity={0.7} pointerEvents="none">
                          {p.name}
                        </text>
                      )}
                    </g>
                  );
                })}
              {originPoint &&
                shown
                  .filter((p) => p !== originPoint)
                  .map((p) => <line key={`ray${p.id}`} x1={X(originPoint.lon)} y1={Y(originPoint.lat)} x2={X(p.lon)} y2={Y(p.lat)} stroke="#333" strokeWidth={0.5} strokeDasharray="3 3" />)}
              {drawn.map(([p, x, y, i], n) => {
                const [lx, ly, anchor] = labels[n];
                const color = colors[p.category];
                const sel = origin === p.id;
                return (
                  <g
                    key={`pt${p.id}`}
                    style={{ cursor: "pointer" }}
                    onClick={() => setOrigin(origin === p.id ? null : p.id)}
                    onDoubleClick={() => router.push(p.link)}
                    onMouseMove={(e) =>
                      show(e, [
                        T.maps.nameKind(p.name, p.kind),
                        T.maps.parent(p.parent_name),
                        T.maps.lonLatAlt(p.lon, p.lat, p.alt),
                        p.environment && T.maps.environment(p.environment),
                        [p.sample_region, p.sample_culture, p.sample_era].filter(Boolean).join(" / "),
                        (p.start || p.end) && T.maps.period(p.start, p.end),
                      ])
                    }
                    onMouseLeave={hide}
                  >
                    <Marker category={p.category} x={x} y={y} r={(sel ? 7 : 4) + 2 * i} color={color} strokeWidth={sel ? 2.5 : 1} />
                    <text x={lx} y={ly} textAnchor={anchor} fill={color} stroke="#fdfcf8" strokeWidth={3} paintOrder="stroke" fontWeight={sel ? "bold" : "normal"}>
                      {p.name}
                      {altText(p.alt)}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>
          <aside className="viz-side">
            {!originPoint ? (
              <>
                <p className="hint">{T.maps.hintClick}</p>
                <p className="hint">
                  {T.maps.hintCounts(points.length, shapes.length)}
                </p>
              </>
            ) : (
              <>
                <div className="viz-head">
                  <h2>
                    {originPoint.name} <span className="hint">({originPoint.kind} / {originPoint.parent_name ?? "-"})</span>
                  </h2>
                  <button type="button" className="primary" onClick={() => router.push(originPoint.link)}>
                    {T.openRecord}
                  </button>
                </div>
                <dl>
                  <dt>{T.maps.coordinates}</dt>
                  <dd>{T.maps.lonLatAlt(originPoint.lon, originPoint.lat, originPoint.alt)}</dd>
                  {originPoint.environment && (
                    <>
                      <dt>{T.maps.environmentDt}</dt>
                      <dd>{originPoint.environment}</dd>
                    </>
                  )}
                </dl>
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
                      <tr key={r.p.id} className="row" onClick={() => setOrigin(r.p.id)}>
                        <td>
                          {r.p.name}
                          <br />
                          <span className="hint">{r.p.parent_name ?? ""}</span>
                        </td>
                        {r.deg < 0.01 ? (
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
              </>
            )}
          </aside>
        </div>
      )}
      <Tooltip tip={tip} />
    </div>
  );
}
