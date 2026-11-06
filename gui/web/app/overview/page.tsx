"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import Modal from "@/components/Modal";
import ReferenceSelect from "@/components/ReferenceSelect";
import Tooltip, { useTooltip } from "@/components/Tooltip";
import {
  getOverview,
  type OverviewCharacter,
  type OverviewEpisode,
  type OverviewEvent,
  type OverviewResponse,
} from "@/lib/api";
import { PageTitle } from "@/lib/meta";
import { fromDayNumber, formatStamp } from "@/lib/stamp";
import { T } from "@/lib/text";
import {
  DEFAULT_VIEW,
  GAP_PX,
  ITEM_GAP,
  ITEM_HEIGHT,
  axisTicksOf,
  dayOf,
  savedView,
  scaleOf,
  timeSpan,
  zoomed,
  type Gap,
  type Scale,
  type Span,
  type View,
} from "@/lib/timelineAxis";

// 縮尺と詰め方・絞り込みを覚えておく localStorage のキー。話のタイムラインとは別に覚える
const VIEW_STORAGE_KEY = "overview-view";
const FILTER_STORAGE_KEY = "overview-filter";
// 話の列の筋の幅と、人物の列の幅(px)
const EPISODE_LANE_WIDTH = 160;
const CHARACTER_WIDTH = 56;
// 章の期間の前後に足す余白の選択肢(日)
const MARGINS = [0, 30, 90, 180];
// 出来事の点の大きさ。大きさ 1 の点の半径と、大きさ 1 ごとに足す半径・上限
const DOT_BASE = 3.5;
const DOT_STEP = 0.9;
const DOT_MAX = 13;
// 名前を点の脇に出す出来事の大きさの下限(小さな出来事は吹き出しで読む)
const LABEL_SIZE = 4;

type Filter = { people: "cast" | "involved"; origin: "all" | "ai" | "user"; minSize: number };
const DEFAULT_FILTER: Filter = { people: "involved", origin: "all", minSize: 0 };

function savedFilter(): Filter {
  try {
    const saved = JSON.parse(localStorage.getItem(FILTER_STORAGE_KEY) ?? "null");
    return {
      people: saved?.people === "cast" ? "cast" : "involved",
      origin: saved?.origin === "ai" || saved?.origin === "user" ? saved.origin : "all",
      minSize: Number.isFinite(saved?.minSize) ? Number(saved.minSize) : 0,
    };
  } catch {
    return DEFAULT_FILTER;
  }
}

type Placed = { episode: OverviewEpisode; y: number; height: number; lane: number };

/** 話の札を、重ならないよう筋に振り分ける(話のタイムラインと同じく、上から空いた筋に入れる) */
function pack(episodes: OverviewEpisode[], scale: Scale): { placed: Placed[]; lanes: number } {
  const laneEnds: number[] = [];
  const placed = episodes.map((episode) => {
    const start = dayOf(episode.start) ?? 0;
    const end = dayOf(episode.end);
    const y = scale.toY(start);
    const height = Math.max(ITEM_HEIGHT, end === null ? 0 : scale.toY(end) - y);
    let lane = laneEnds.findIndex((laneEnd) => laneEnd <= y);
    if (lane < 0) lane = laneEnds.length;
    laneEnds[lane] = y + height + ITEM_GAP;
    return { episode, y, height, lane };
  });
  return { placed, lanes: Math.max(1, laneEnds.length) };
}

const radius = (event: OverviewEvent) => Math.min(DOT_MAX, DOT_BASE + (event.size.total - 1) * DOT_STEP);

export default function OverviewPage() {
  const router = useRouter();
  const search = useSearchParams();
  const storyId = Number(search.get("story_id")) || null;
  const marginParam = Number(search.get("margin"));
  const margin = MARGINS.includes(marginParam) ? marginParam : 30;

  const [data, setData] = useState<OverviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<View>(DEFAULT_VIEW);
  const [filter, setFilter] = useState<Filter>(DEFAULT_FILTER);
  useEffect(() => {
    setView(savedView(VIEW_STORAGE_KEY));
    setFilter(savedFilter());
  }, []);
  const [box, setBox] = useState({ viewport: 0, head: 0 });
  const [screen, setScreen] = useState(0);
  const [selected, setSelected] = useState<OverviewEvent | null>(null);
  const [focus, setFocus] = useState<number | null>(null);
  const [showRelations, setShowRelations] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const scrolledFor = useRef<string | null>(null);
  const { tip, show, hide } = useTooltip();
  const zoomIn = zoomed(view, -1);
  const zoomOut = zoomed(view, 1);

  const remember = (key: string, value: unknown) => {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // 覚えられなくても、この画面の中では効く
    }
  };
  const changeView = (changes: Partial<View>) => {
    const next = { ...view, ...changes };
    setView(next);
    remember(VIEW_STORAGE_KEY, next);
  };
  const changeFilter = (changes: Partial<Filter>) => {
    const next = { ...filter, ...changes };
    setFilter(next);
    remember(FILTER_STORAGE_KEY, next);
  };
  const navigate = useCallback(
    (changes: Record<string, string | number | null>) => {
      const params = new URLSearchParams(search.toString());
      for (const [key, value] of Object.entries(changes)) {
        if (value === null || value === "") params.delete(key);
        else params.set(key, String(value));
      }
      router.replace(`/overview?${params}`);
    },
    [router, search],
  );

  useEffect(() => {
    if (storyId === null) return;
    let alive = true;
    setData(null);
    getOverview({ story_id: storyId, margin_days: margin })
      .then((result) => {
        if (!alive) return;
        setData(result);
        setError(null);
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [storyId, margin]);

  const scrollBoxRef = useCallback((element: HTMLDivElement | null) => {
    scrollRef.current = element;
    if (!element) return;
    const measure = () => {
      const head = element.querySelector<HTMLElement>(".timeline-head")?.offsetHeight ?? 0;
      setBox({ viewport: Math.max(0, element.clientHeight - head), head });
    };
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  // 絞り込んだ出来事と、列に出す人物
  const events = useMemo(
    () =>
      (data?.events ?? []).filter(
        (event) =>
          event.size.total >= filter.minSize &&
          (filter.origin === "all" ||
            (filter.origin === "ai" ? event.expansion_id !== null : event.expansion_id === null)),
      ),
    [data, filter],
  );
  const characters = useMemo(() => {
    const involved = new Set(events.flatMap((event) => event.character_ids));
    return (data?.characters ?? []).filter(
      (character) => character.in_cast || (filter.people === "involved" && involved.has(character.id)),
    );
  }, [data, events, filter.people]);
  const column = useMemo(() => new Map(characters.map((character, index) => [character.id, index])), [characters]);
  const names = useMemo(
    () => new Map((data?.characters ?? []).map((character) => [character.id, character.name ?? `#${character.id}`])),
    [data],
  );
  // 子を持つ出来事は、企て(親の出来事)として帯で描く
  const parentIds = useMemo(
    () => new Set((data?.events ?? []).map((event) => event.parent_event_id).filter((id) => id != null)),
    [data],
  );

  const spans: Span[] = useMemo(() => {
    const all: Span[] = [];
    for (const item of [...(data?.episodes ?? []), ...events]) {
      const start = dayOf(item.start);
      if (start !== null) all.push(timeSpan(start, dayOf(item.end)));
    }
    return all;
  }, [data, events]);
  const scale = useMemo(() => scaleOf(spans, null, view, box.viewport), [spans, view, box.viewport]);
  const ticks = useMemo(
    () => (scale ? axisTicksOf(scale, spans, view.squeeze, screen, box.viewport) : []),
    [scale, spans, view.squeeze, screen, box.viewport],
  );
  const chapter = useMemo(
    () => (scale && data ? pack(data.episodes.filter((episode) => episode.in_story), scale) : null),
    [scale, data],
  );
  const siblings = useMemo(
    () => (scale && data ? pack(data.episodes.filter((episode) => !episode.in_story), scale) : null),
    [scale, data],
  );

  // 読み込んだら、章の最初の話が画面の上の方に来るようにスクロールする
  useLayoutEffect(() => {
    const element = scrollRef.current;
    const first = data?.episodes.find((episode) => episode.in_story);
    const key = data ? `${data.story_id}:${margin}` : null;
    if (!element || !scale || !first || key === null || scrolledFor.current === key) return;
    scrolledFor.current = key;
    element.scrollTop = Math.max(0, scale.toY(dayOf(first.start) ?? 0) - box.viewport / 4);
  }, [data, scale, margin, box.viewport]);

  const onScroll = () => {
    const element = scrollRef.current;
    if (element && box.viewport > 0) setScreen(Math.floor(element.scrollTop / box.viewport));
  };

  const eventLines = (event: OverviewEvent) => [
    event.name,
    T.span(event.start, event.end) || event.start,
    event.location_name ?? "",
    T.overview.size(event.size.total),
    event.character_ids.map((id) => names.get(id)).join(", "),
  ];
  const gapLines = (g: Gap) => [
    T.overview.gap,
    `${formatStamp(fromDayNumber(g.from))} – ${formatStamp(fromDayNumber(g.to))}`,
  ];

  const renderEpisodes = (packed: { placed: Placed[]; lanes: number } | null, faint: boolean) =>
    packed && (
      <div className="timeline-col">
        <div className="timeline-track" style={{ width: packed.lanes * EPISODE_LANE_WIDTH, height: scale?.height }}>
          {packed.placed.map(({ episode, y, height, lane }) => (
            <Link
              key={episode.id}
              href={`/tables/episode/${episode.id}`}
              className={`timeline-item ${episode.end ? "" : "point"} ${faint ? "overview-faint" : ""}`}
              style={{ left: lane * EPISODE_LANE_WIDTH + 2, top: y, width: EPISODE_LANE_WIDTH - 4, height }}
              onMouseMove={(e) =>
                show(e, [episode.title ?? `#${episode.id}`, T.span(episode.start, episode.end) || episode.start,
                         episode.story_name ?? ""])
              }
              onMouseLeave={hide}
            >
              <span className="timeline-text">{episode.title ?? `#${episode.id}`}</span>
            </Link>
          ))}
        </div>
      </div>
    );

  const x = (characterId: number) => (column.get(characterId) ?? 0) * CHARACTER_WIDTH + CHARACTER_WIDTH / 2;

  const renderEvents = () => {
    if (!scale) return null;
    const width = characters.length * CHARACTER_WIDTH;
    const dimmed = (event: OverviewEvent) => focus !== null && !event.character_ids.includes(focus);
    return (
      <div className="overview-people" style={{ width, height: scale.height }}>
        {characters.map((character) => (
          <div
            key={character.id}
            className={`overview-lane ${focus === character.id ? "focused" : ""}`}
            style={{ left: (column.get(character.id) ?? 0) * CHARACTER_WIDTH, width: CHARACTER_WIDTH }}
          />
        ))}
        <svg className="overview-svg" width={width} height={scale.height}>
          {/* 企て(子を持つ出来事)は、動いた人物の列に始まりから終わりまでの帯で描く */}
          {events
            .filter((event) => parentIds.has(event.id))
            .map((event) => {
              const owner = event.actor_id ?? event.character_ids.find((id) => column.has(id));
              const start = dayOf(event.start);
              if (owner == null || !column.has(owner) || start === null) return null;
              const top = scale.toY(start);
              const end = dayOf(event.end);
              const bottom = end === null ? scale.height : scale.toY(end);
              return (
                <rect
                  key={`arc-${event.id}`}
                  className={`overview-arc ${dimmed(event) ? "dimmed" : ""}`}
                  x={x(owner) - CHARACTER_WIDTH / 2 + 6}
                  y={top}
                  width={CHARACTER_WIDTH - 12}
                  height={Math.max(4, bottom - top)}
                  rx={4}
                  onMouseMove={(e) => show(e, [T.overview.arc, ...eventLines(event)])}
                  onMouseLeave={hide}
                  onClick={() => setSelected(event)}
                />
              );
            })}
          {events.map((event) => {
            const start = dayOf(event.start);
            const ids = event.character_ids.filter((id) => column.has(id));
            if (start === null || ids.length === 0) return null;
            const y = scale.toY(start);
            const xs = ids.map(x);
            const r = radius(event);
            const ai = event.expansion_id !== null;
            const className = `overview-event ${ai ? "ai" : "user"} ${dimmed(event) ? "dimmed" : ""} ${selected?.id === event.id ? "selected" : ""}`;
            const right = Math.max(...xs);
            return (
              <g
                key={event.id}
                className={className}
                onMouseMove={(e) => show(e, eventLines(event))}
                onMouseLeave={hide}
                onClick={() => setSelected(event)}
              >
                {xs.length > 1 && (
                  <line x1={Math.min(...xs)} x2={right} y1={y} y2={y} strokeWidth={Math.max(1.5, r / 2.5)} />
                )}
                {/* 巻きこんだ相手へは、動いた人物から矢印を引く */}
                {event.actor_id !== null &&
                  column.has(event.actor_id) &&
                  event.invited_ids
                    .filter((id) => column.has(id))
                    .map((id) => (
                      <path
                        key={`invite-${id}`}
                        className="overview-invite"
                        d={`M${x(event.actor_id!)},${y - r - 2} Q${(x(event.actor_id!) + x(id)) / 2},${y - r - 16} ${x(id)},${y - r - 2}`}
                        markerEnd="url(#overview-arrow)"
                      />
                    ))}
                {ids.map((id) =>
                  id === event.actor_id ? (
                    <rect
                      key={id}
                      className="overview-actor"
                      x={x(id) - r}
                      y={y - r}
                      width={r * 2}
                      height={r * 2}
                      transform={`rotate(45 ${x(id)} ${y})`}
                    />
                  ) : (
                    <circle
                      key={id}
                      className={event.invited_ids.includes(id) ? "overview-invited" : "overview-dot"}
                      cx={x(id)}
                      cy={y}
                      r={r}
                    />
                  ),
                )}
                {(event.size.total >= LABEL_SIZE || selected?.id === event.id) && (
                  <text x={right + r + 4} y={y + 4} className="overview-label">
                    {event.name}
                  </text>
                )}
              </g>
            );
          })}
          <defs>
            <marker id="overview-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto">
              <path d="M0,0 L8,4 L0,8 z" />
            </marker>
          </defs>
        </svg>
      </div>
    );
  };

  const focused = focus === null ? null : (data?.characters.find((character) => character.id === focus) ?? null);
  const focusedRelations = focused
    ? (data?.relations ?? []).filter(
        (relation) => relation.character_1_id === focused.id || relation.character_2_id === focused.id,
      )
    : [];

  const head = (character: OverviewCharacter) => (
    <button
      type="button"
      key={character.id}
      className={`timeline-label overview-person ${focus === character.id ? "focused" : ""} ${character.in_cast ? "cast" : ""}`}
      title={`${character.name ?? ""} · ${T.overview.influence(character.influence)}${character.main_character ? ` · ${T.overview.main}` : ""}`}
      onClick={() => {
        setFocus(focus === character.id ? null : character.id);
        setShowRelations(focus !== character.id);
      }}
    >
      <span className="overview-name">{character.name ?? `#${character.id}`}</span>
      <span className="overview-influence">{character.influence}</span>
    </button>
  );

  const columns = [
    "var(--timeline-axis)",
    `${(chapter?.lanes ?? 1) * EPISODE_LANE_WIDTH}px`,
    ...(siblings && siblings.placed.length > 0 ? [`${siblings.lanes * EPISODE_LANE_WIDTH}px`] : []),
    `${Math.max(1, characters.length) * CHARACTER_WIDTH}px`,
  ];

  return (
    <div className="page-fill timeline-page overview-page">
      <PageTitle kind={T.overview.title} record={data?.story_name ?? null} />
      <div className="toolbar">
        <h1 style={{ margin: 0 }}>{T.overview.title}</h1>
        <div className="hint timeline-filter">
          {T.overview.story}
          <ReferenceSelect
            table="story"
            value={storyId}
            nullable
            onChange={(value) => navigate({ story_id: value })}
            title={T.overview.story}
          />
        </div>
        <label className="hint timeline-filter">
          {T.overview.margin}
          <select value={margin} onChange={(e) => navigate({ margin: Number(e.target.value) })}>
            {MARGINS.map((days) => (
              <option key={days} value={days}>
                {T.overview.marginDays(days)}
              </option>
            ))}
          </select>
        </label>
        <div className="hint timeline-filter">
          {T.timeline.scale}
          <button type="button" onClick={() => zoomIn && changeView(zoomIn)} disabled={!zoomIn} title={T.timeline.zoomIn}>
            −
          </button>
          <span className="timeline-zoom">{T.timeline.zoom(view)}</span>
          <button type="button" onClick={() => zoomOut && changeView(zoomOut)} title={T.timeline.zoomOut}>
            +
          </button>
        </div>
        <label className="hint timeline-filter">
          <input type="checkbox" checked={view.squeeze} onChange={(e) => changeView({ squeeze: e.target.checked })} />
          {T.timeline.squeeze}
        </label>
        <label className="hint timeline-filter">
          {T.overview.people}
          <select value={filter.people} onChange={(e) => changeFilter({ people: e.target.value as Filter["people"] })}>
            <option value="cast">{T.overview.castOnly}</option>
            <option value="involved">{T.overview.involved}</option>
          </select>
        </label>
        <label className="hint timeline-filter">
          {T.overview.origin}
          <select value={filter.origin} onChange={(e) => changeFilter({ origin: e.target.value as Filter["origin"] })}>
            <option value="all">{T.overview.originAll}</option>
            <option value="ai">{T.overview.originAi}</option>
            <option value="user">{T.overview.originUser}</option>
          </select>
        </label>
        <label className="hint timeline-filter">
          {T.overview.minSize}
          <input
            type="number"
            min={0}
            max={20}
            value={filter.minSize}
            style={{ width: "3.5rem" }}
            onChange={(e) => changeFilter({ minSize: Math.max(0, Number(e.target.value) || 0) })}
          />
        </label>
        {focus !== null && (
          <button type="button" onClick={() => setFocus(null)}>
            {T.overview.clearFocus}
          </button>
        )}
      </div>
      {data && (
        <div className="status info overview-status">
          {T.overview.period(data.since, data.until)} · {T.overview.legend}
        </div>
      )}
      {error && <div className="status error">{error}</div>}
      {storyId === null ? (
        <div className="status info">{T.overview.pickStory}</div>
      ) : !data ? (
        !error && <div className="status info">{T.loading}</div>
      ) : (
        <div className="timeline overview" style={{ "--timeline-head": `${box.head}px` } as CSSProperties}>
          <div className="timeline-scroll" ref={scrollBoxRef} onScroll={onScroll}>
            <div className="timeline-head overview-head" style={{ gridTemplateColumns: columns.join(" ") }}>
              <div className="timeline-corner" />
              <div className="timeline-label">{data.story_name ?? T.overview.episodes}</div>
              {siblings && siblings.placed.length > 0 && <div className="timeline-label">{T.overview.siblings}</div>}
              <div className="overview-people-head" style={{ gridTemplateColumns: `repeat(${characters.length}, ${CHARACTER_WIDTH}px)` }}>
                {characters.map(head)}
              </div>
            </div>
            <div className="timeline-body">
              <div className="timeline-lines">
                {scale?.gaps.map((g) => (
                  <div key={g.from} className="timeline-gap" style={{ top: g.y, height: GAP_PX }} />
                ))}
                {ticks.map((tick) => (
                  <div key={tick.at} className={`timeline-grid ${tick.major ? "major" : ""}`} style={{ top: scale?.toY(tick.at) }} />
                ))}
              </div>
              <div className="timeline-axis" style={{ height: scale?.height }}>
                {scale?.gaps.map((g) => (
                  <div
                    key={g.from}
                    className="timeline-gap"
                    style={{ top: g.y, height: GAP_PX }}
                    onMouseMove={(e) => show(e, gapLines(g))}
                    onMouseLeave={hide}
                  >
                    {T.timeline.skipped(g.to - g.from)}
                  </div>
                ))}
                {ticks.map((tick) => (
                  <div key={tick.at} className={`timeline-tick ${tick.major ? "major" : ""}`} style={{ top: scale?.toY(tick.at) }}>
                    {tick.label}
                  </div>
                ))}
              </div>
              {renderEpisodes(chapter, false)}
              {siblings && siblings.placed.length > 0 && renderEpisodes(siblings, true)}
              <div className="timeline-col">{renderEvents()}</div>
            </div>
          </div>
        </div>
      )}
      {selected && (
        <Modal
          title={selected.name}
          onClose={() => setSelected(null)}
          actions={
            <>
              <span className="spacer" />
              {selected.expansion_id !== null && (
                <Link href="/expansions">{T.overview.openExpansion(selected.expansion_id)}</Link>
              )}
              <Link href={`/tables/event/${selected.id}`}>{T.overview.openEvent}</Link>
              <button type="button" onClick={() => setSelected(null)}>
                {T.close}
              </button>
            </>
          }
        >
          <div className="timeline-sheet">
            {[
              T.span(selected.start, selected.end) || selected.start,
              selected.location_name,
              `${T.overview.size(selected.size.total)}: ${T.overview.sizeParts(selected.size)}`,
              selected.actor_id !== null && `${T.overview.actor}: ${names.get(selected.actor_id)}`,
              selected.invited_ids.length > 0 &&
                `${T.overview.invited}: ${selected.invited_ids.map((id) => names.get(id)).join(", ")}`,
              `${T.overview.participants}: ${selected.character_ids.map((id) => names.get(id)).join(", ")}`,
              selected.hidden && T.overview.hidden,
            ]
              .filter(Boolean)
              .join("\n")}
          </div>
          {selected.text && <div className="timeline-sheet">{selected.text}</div>}
          {selected.expansion_prompt && (
            <div className="field">
              <label>{T.overview.dialogue}</label>
              <div className="timeline-sheet">{selected.expansion_prompt}</div>
            </div>
          )}
          {selected.expansion_summary && (
            <div className="field">
              <label>{T.overview.summary}</label>
              <div className="timeline-sheet">{selected.expansion_summary}</div>
            </div>
          )}
        </Modal>
      )}
      {focused && showRelations && (
        <Modal title={T.overview.relationsOf(focused.name ?? `#${focused.id}`)} onClose={() => setShowRelations(false)}>
          <div className="timeline-sheet">
            {[
              `${T.overview.influence(focused.influence)}${focused.main_character ? ` · ${T.overview.main}` : ""}`,
              T.overview.eventsOf(events.filter((event) => event.character_ids.includes(focused.id)).length),
            ].join("\n")}
          </div>
          {focusedRelations.length === 0 ? (
            <div className="hint">{T.overview.noRelations}</div>
          ) : (
            <ul className="overview-relations">
              {focusedRelations.map((relation) => {
                const partner = relation.character_1_id === focused.id ? relation.character_2_id : relation.character_1_id;
                return (
                  <li key={relation.id}>
                    <button type="button" className="overview-partner" onClick={() => setFocus(partner)}>
                      {names.get(partner)}
                    </button>{" "}
                    {relation.relation} <span className="hint">{T.span(relation.start, relation.end)}</span>
                  </li>
                );
              })}
            </ul>
          )}
        </Modal>
      )}
      <Tooltip tip={tip} />
    </div>
  );
}
