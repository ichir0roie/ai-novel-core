"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import NameId from "@/components/NameId";
import Tooltip, { useTooltip } from "@/components/Tooltip";
import { getMaps, getStoryRoute, type MapLocation, type MapsResponse, type StoryRoute } from "@/lib/api";
import { PageTitle } from "@/lib/meta";
import { useOpenPage } from "@/lib/nav";
import {
  altDiffText, altText, angular, bearing, bearingName, distanceKm, distanceText, fitFrame, MARGIN, outerRing,
  locationLabels, polygonCenter, textWidth, type Box, type Polygon,
} from "@/lib/map";
import { badgeText, legPath, ROUTE_COLOR, routeLegs, routeVisits, type Visit } from "@/lib/storyRoute";
import { T } from "@/lib/text";

type Point = MapLocation & { lon: number; lat: number };
type Shape = MapLocation & { polygon: Polygon };
type PlacedVisit = Visit & { lon: number; lat: number };

function Marker({ category, x, y, r, color, strokeWidth = 1 }: { category: string; x: number; y: number; r: number; color: string; strokeWidth?: number }) {
  const common = { fill: color, stroke: "#fff", strokeWidth };
  if (category === "国") return <circle cx={x} cy={y} r={r} {...common} />;
  if (category === "都市") return <rect x={x - r} y={y - r} width={2 * r} height={2 * r} {...common} />;
  if (category === "自然") return <path d={`M${x},${y - r * 1.2} L${x + r * 1.1},${y + r * 0.8} L${x - r * 1.1},${y + r * 0.8} Z`} {...common} />;
  return <path d={`M${x},${y - r} L${x + r},${y} L${x},${y + r} L${x - r},${y} Z`} {...common} />;
}

export default function MapsPage() {
  const openPage = useOpenPage();
  const search = useSearchParams();
  // 場所の詳細から飛んできたとき。その場所の星を選び、その場所を中心に置いて描く
  const focus = Number(search.get("location")) || null;
  // 作品から飛んできたとき。話の場所を作品の中の順に結んで描く
  const storyId = Number(search.get("story")) || null;
  // 話から飛んできたとき。作品の道筋の中でその話の立ち寄りを選んでおく
  const episodeId = Number(search.get("episode")) || null;
  const [data, setData] = useState<MapsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [planetIndex, setPlanetIndex] = useState(0);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [origin, setOrigin] = useState<number | null>(null);
  const [zoom, setZoom] = useState(1);
  const [route, setRoute] = useState<StoryRoute | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const { tip, show, hide } = useTooltip();

  useEffect(() => {
    Promise.all([getMaps(), storyId == null ? null : getStoryRoute(storyId)])
      .then(([result, story]) => {
        setData(result);
        setRoute(story);
        if (story) {
          const visit = episodeId == null ? undefined : routeVisits(story.stops).find((v) => v.stops.some((stop) => stop.episode_id === episodeId));
          if (visit) setSelected(visit.n);
          // 選んだ話の星、無ければ話の場所が一番多く立つ星から見せる
          const counts = new Map<number, number>();
          for (const stop of story.stops) if (stop.planet_id != null) counts.set(stop.planet_id, (counts.get(stop.planet_id) ?? 0) + 1);
          const best = visit?.planetId ?? [...counts].sort((a, b) => b[1] - a[1])[0]?.[0];
          const index = result.planets.findIndex((pl) => pl.planet.id === best);
          if (index >= 0) setPlanetIndex(index);
          return;
        }
        if (focus == null) return;
        const index = result.planets.findIndex((pl) => [...pl.points, ...pl.shapes].some((p) => p.id === focus));
        if (index < 0) return;
        setPlanetIndex(index);
        if (result.planets[index].points.some((p) => p.id === focus)) setOrigin(focus);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [focus, storyId, episodeId]);

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
  const focusLocation = focus == null ? null : [...points, ...shapes].find((p) => p.id === focus) ?? null;
  const visits = useMemo(() => (route ? routeVisits(route.stops) : []), [route]);
  const planetId = entry?.planet.id ?? null;
  const here = useMemo(
    () => visits.filter((v): v is PlacedVisit => v.planetId === planetId && v.lon != null && v.lat != null),
    [visits, planetId],
  );
  // 作品の道筋を描くときは、道筋の場所が収まる枠にする
  const frame = useMemo(
    () => (here.length ? fitFrame(here.map((v) => ({ lon: v.lon, lat: v.lat })), [], zoom) : fitFrame(points, shapes, zoom, center)),
    [here, points, shapes, zoom, center],
  );
  // 選んだ立ち寄り(無ければ最初の立ち寄り)が見えるよう、図をスクロールする
  const graphRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = graphRef.current;
    const v = here.find((h) => h.n === selected) ?? here[0];
    if (!el || !v) return;
    el.scrollTo({ left: frame.x(v.lon) - el.clientWidth / 2, top: frame.y(v.lat) - el.clientHeight / 2, behavior: "smooth" });
  }, [here, selected, frame]);
  // 選んだ立ち寄りの行が見えるよう、横の一覧もスクロールする
  const sideRef = useRef<HTMLElement>(null);
  useEffect(() => {
    sideRef.current?.querySelector("tr.on")?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selected, route]);

  if (error) return <div className="status error">{error}</div>;
  if (!data) return <div className="status info">{T.loading}</div>;

  const { categories, category_colors: colors, shape_opacity: opacity, bearings } = data;
  const order = (p: MapLocation) => categories.indexOf(p.category);
  const byOrder = (a: MapLocation, b: MapLocation) => order(a) - order(b) || a.id - b.id;
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
  // 道筋の札は、同じ経緯度に立つ立ち寄りを一枚にまとめて印の上に立てる
  const badges = new Map<string, { x: number; y: number; visits: PlacedVisit[] }>();
  for (const v of here) {
    const k = `${v.lon},${v.lat}`;
    if (!badges.has(k)) badges.set(k, { x: X(v.lon), y: Y(v.lat), visits: [] });
    badges.get(k)!.visits.push(v);
  }
  const badgeBox = (b: { x: number; y: number; visits: Visit[] }): Box => {
    const w = textWidth(badgeText(b.visits.map((v) => v.n))) + 12;
    return [b.x - w / 2, b.y - 27, b.x + w / 2, b.y - 11];
  };
  const routeIds = new Set(here.map((v) => v.placedId));
  // 道筋を描くときは、道筋の場所だけに名を出す
  const labeled = route ? drawn.filter(([p]) => routeIds.has(p.id)) : drawn;
  const labelPositions = locationLabels(
    labeled.map(([p, x, y, i]) => [x, y + 12 * i, T.nameId(p.name, p.id) + altText(p.alt)]),
    11,
    [...badges.values()].map(badgeBox),
  );
  const labelOf = new Map(labeled.map(([p], n) => [p.id, labelPositions[n]]));
  const shownIds = new Set(shown.map((p) => p.id));
  const legs = routeLegs(visits).filter((leg) => leg.from.planetId === planetId && leg.to.planetId === planetId);
  const selectVisit = (v: Visit) => {
    if (v.planetId != null && v.planetId !== planetId) {
      const index = data.planets.findIndex((pl) => pl.planet.id === v.planetId);
      if (index >= 0) setPlanetIndex(index);
    }
    setSelected(selected === v.n ? null : v.n);
  };
  // 札を押すたびに、その場所の立ち寄りを順に選ぶ
  const cycleBadge = (ns: number[]) => {
    const i = selected == null ? -1 : ns.indexOf(selected);
    setSelected(i < 0 ? ns[0] : i + 1 < ns.length ? ns[i + 1] : null);
  };
  const planetName = (id: number) => {
    const pl = data.planets.find((p) => p.planet.id === id)?.planet;
    return pl ? T.nameId(pl.name, pl.id) : T.nameId(null, id);
  };
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
      <PageTitle
        kind={T.maps.title}
        record={route ? T.nameId(route.story_name, route.story_id) : focusLocation && T.nameId(focusLocation.name, focusLocation.id)}
      />
      <div className="toolbar">
        <h1 style={{ margin: 0 }}>
          {route
            ? T.maps.routeOf(T.nameId(route.story_name, route.story_id))
            : focusLocation ? T.maps.centeredOn(T.nameId(focusLocation.name, focusLocation.id)) : T.maps.title}
        </h1>
        {route && (
          <Link href="/maps" className="hint">
            {T.maps.fullMap}
          </Link>
        )}
        {!route && focus != null && (
          <>
            {focusLocation && (
              <button type="button" onClick={() => openPage(focusLocation.link)}>
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
                <NameId name={pl.planet.name} id={pl.planet.id} />
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
      {route && !route.stops.some((stop) => stop.placed_id != null) && <div className="status info">{T.maps.routeNone}</div>}
      {!route && focus != null && !focusLocation && (
        <div className="status info">
          {T.maps.cannotPlace(focus)}<Link href={`/tables/location/${focus}`}>{T.openRecord}</Link>
        </div>
      )}
      {!entry ? (
        <div className="status info">{T.maps.nonePlaceable}</div>
      ) : (
        <div className="viz-body">
          <div className="viz-graph" ref={graphRef}>
            <svg xmlns="http://www.w3.org/2000/svg" width={W} height={H} fontSize={11}>
              <defs>
                <clipPath id="plot">
                  <rect x={X(frame.lonMin)} y={Y(frame.latMax)} width={(frame.lonMax - frame.lonMin) * frame.scale} height={(frame.latMax - frame.latMin) * frame.scale} />
                </clipPath>
                <marker id="route-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto">
                  <path d="M0,0 L10,5 L0,10 Z" fill={ROUTE_COLOR} />
                </marker>
              </defs>
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
              <text x={MARGIN.left} y={24} fontSize={18} fontWeight="bold">{T.nameId(entry.planet.name, entry.planet.id)}</text>
              <text x={MARGIN.left + 40 + T.nameId(entry.planet.name, entry.planet.id).length * 18} y={24} fill="#555">
                {radius ? T.maps.radius(radius) : T.maps.radiusUnknown}
              </text>
              {/* 道筋の枠は場所の全部を収めないので、枠の外へはみ出す輪郭・印を切る */}
              <g clipPath={route ? "url(#plot)" : undefined}>
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
                        onMouseMove={(e) => show(e, [T.maps.nameKind(T.nameId(p.name, p.id), p.kind), T.maps.parent(p.parent_id == null ? null : T.nameId(p.parent_name, p.parent_id)), T.maps.polygonVertices(outerRing(p.polygon).length), p.environment && T.maps.environment(p.environment)])}
                        onMouseLeave={hide}
                      >
                        <path d={d} fill={color} fillOpacity={opacity[p.category]} fillRule="evenodd" stroke={color} strokeWidth={1.2} strokeLinejoin="round" />
                        {!pointIds.has(p.id) && (
                          <text x={X(cx)} y={Y(cy)} textAnchor="middle" fontSize={13} fontWeight="bold" fill={color} fillOpacity={0.7} pointerEvents="none">
                            {T.nameId(p.name, p.id)}
                          </text>
                        )}
                      </g>
                    );
                  })}
                {originPoint &&
                  shown
                    .filter((p) => p !== originPoint)
                    .map((p) => <line key={`ray${p.id}`} x1={X(originPoint.lon)} y1={Y(originPoint.lat)} x2={X(p.lon)} y2={Y(p.lat)} stroke="#333" strokeWidth={0.5} strokeDasharray="3 3" />)}
                {legs.map(({ from, to, gap }) => {
                  const x1 = X(from.lon!), y1 = Y(from.lat!), x2 = X(to.lon!), y2 = Y(to.lat!);
                  if (Math.hypot(x2 - x1, y2 - y1) < 1) return null;
                  const on = selected === from.n || selected === to.n;
                  return (
                    <path
                      key={`leg${from.n}`}
                      d={legPath(x1, y1, x2, y2, 7, 9)}
                      fill="none"
                      stroke={ROUTE_COLOR}
                      strokeWidth={on ? 3.5 : 2}
                      strokeOpacity={selected == null || on ? 0.9 : 0.35}
                      strokeDasharray={gap ? "6 4" : undefined}
                      markerEnd="url(#route-arrow)"
                    />
                  );
                })}
                {drawn.map(([p, x, y, i]) => {
                  const label = labelOf.get(p.id);
                  const color = colors[p.category];
                  const sel = origin === p.id;
                  return (
                    <g
                      key={`pt${p.id}`}
                      style={{ cursor: "pointer" }}
                      opacity={route && !routeIds.has(p.id) ? 0.3 : 1}
                      onClick={() => !route && setOrigin(origin === p.id ? null : p.id)}
                      onDoubleClick={() => openPage(p.link)}
                      onMouseMove={(e) =>
                        show(e, [
                          T.maps.nameKind(T.nameId(p.name, p.id), p.kind),
                          T.maps.parent(p.parent_id == null ? null : T.nameId(p.parent_name, p.parent_id)),
                          T.maps.lonLatAlt(p.lon, p.lat, p.alt),
                          p.environment && T.maps.environment(p.environment),
                          [p.sample_region, p.sample_culture, p.sample_era].filter(Boolean).join(" / "),
                          (p.start || p.end) && T.maps.period(p.start, p.end),
                        ])
                      }
                      onMouseLeave={hide}
                    >
                      <Marker category={p.category} x={x} y={y} r={(sel ? 7 : 4) + 2 * i} color={color} strokeWidth={sel ? 2.5 : 1} />
                      {label && (
                        <text x={label[0]} y={label[1]} textAnchor={label[2]} fill={color} stroke="#fdfcf8" strokeWidth={3} paintOrder="stroke" fontWeight={sel ? "bold" : "normal"}>
                          {T.nameId(p.name, p.id)}
                          {altText(p.alt)}
                        </text>
                      )}
                    </g>
                  );
                })}
                {[...badges.entries()].map(([k, b]) => {
                  const ns = b.visits.map((v) => v.n);
                  const [bx0, by0, bx1, by1] = badgeBox(b);
                  const on = selected != null && ns.includes(selected);
                  return (
                    <g
                      key={`badge${k}`}
                      style={{ cursor: "pointer" }}
                      onClick={() => cycleBadge(ns)}
                      onMouseMove={(e) =>
                        show(e, b.visits.flatMap((v) => v.stops.map((stop) => `${v.n}. ${T.nameId(stop.title, stop.episode_id)}${stop.start ? `  ${stop.start}` : ""}`)))
                      }
                      onMouseLeave={hide}
                    >
                      {!b.visits.some((v) => v.placedId != null && shownIds.has(v.placedId)) && <circle cx={b.x} cy={b.y} r={4} fill={ROUTE_COLOR} stroke="#fff" />}
                      <line x1={b.x} y1={by1} x2={b.x} y2={b.y - 4} stroke={ROUTE_COLOR} strokeWidth={1.5} />
                      <rect x={bx0} y={by0} width={bx1 - bx0} height={by1 - by0} rx={8} fill={on ? ROUTE_COLOR : "#fff"} stroke={ROUTE_COLOR} strokeWidth={1.5} />
                      <text x={b.x} y={by1 - 4} textAnchor="middle" fontWeight="bold" fill={on ? "#fff" : ROUTE_COLOR}>
                        {badgeText(ns)}
                      </text>
                    </g>
                  );
                })}
              </g>
            </svg>
          </div>
          <aside className="viz-side" ref={sideRef}>
            {route ? (
              <>
                <div className="viz-head">
                  <h2>
                    <NameId name={route.story_name} id={route.story_id} />
                  </h2>
                  <button type="button" className="primary" onClick={(e) => openPage(`/tables/story/${route.story_id}`, e)}>
                    {T.openRecord}
                  </button>
                </div>
                <p className="hint">{T.maps.routeCounts(route.stops.filter((stop) => stop.placed_id != null).length, route.stops.length)}</p>
                <table>
                  <thead>
                    <tr>
                      <th>{T.maps.columns.order}</th>
                      <th>{T.maps.columns.episode}</th>
                      <th>{T.maps.columns.location}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visits.flatMap((v) =>
                      v.stops.map((stop, i) => (
                        <tr key={stop.episode_id} className={selected === v.n ? "row on" : "row"} onClick={() => selectVisit(v)}>
                          <td className="num">{i === 0 ? v.n : ""}</td>
                          <td>
                            <Link href={`/tables/episode/${stop.episode_id}`} onClick={(e) => e.stopPropagation()}>
                              <NameId name={stop.title} id={stop.episode_id} />
                            </Link>
                            <br />
                            <span className="hint">{stop.start ?? "-"}</span>
                          </td>
                          <td>
                            {stop.location_id == null ? (
                              <span className="hint">{T.maps.routeNoLocation}</span>
                            ) : (
                              <NameId name={stop.location_name} id={stop.location_id} />
                            )}
                            {stop.location_id != null && stop.placed_id == null && (
                              <>
                                <br />
                                <span className="hint">{T.maps.routeUnplaced}</span>
                              </>
                            )}
                            {stop.placed_id != null && stop.placed_id !== stop.location_id && (
                              <>
                                <br />
                                <span className="hint">{T.maps.routePlacedAt(T.nameId(stop.placed_name, stop.placed_id))}</span>
                              </>
                            )}
                            {stop.planet_id != null && stop.planet_id !== planetId && (
                              <>
                                <br />
                                <span className="hint">{T.maps.routeOtherPlanet(planetName(stop.planet_id))}</span>
                              </>
                            )}
                          </td>
                        </tr>
                      )),
                    )}
                  </tbody>
                </table>
              </>
            ) : !originPoint ? (
              <>
                <p className="hint" title={T.maps.hintClick}>
                  {T.maps.hintCounts(points.length, shapes.length)}
                </p>
              </>
            ) : (
              <>
                <div className="viz-head">
                  <h2>
                    <NameId name={originPoint.name} id={originPoint.id} />{" "}
                    <span className="hint">
                      ({originPoint.kind} / {originPoint.parent_id == null ? "-" : T.nameId(originPoint.parent_name, originPoint.parent_id)})
                    </span>
                  </h2>
                  <button type="button" className="primary" onClick={() => openPage(originPoint.link)}>
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
                          <NameId name={r.p.name} id={r.p.id} />
                          <br />
                          <span className="hint">{r.p.parent_id == null ? "" : T.nameId(r.p.parent_name, r.p.parent_id)}</span>
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
