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
  type MouseEvent,
} from "react";
import EpisodeFields, { addEpisode, type EpisodeDraft } from "@/components/EpisodeFields";
import Modal from "@/components/Modal";
import { newEpisodeUrl } from "@/components/NewEpisodeModal";
import ReferenceSelect, { invalidateOptions } from "@/components/ReferenceSelect";
import Tooltip, { useTooltip } from "@/components/Tooltip";
import {
  getOverview,
  getRecord,
  updateEpisodes,
  type OverviewCharacter,
  type OverviewEpisode,
  type OverviewEvent,
  type OverviewResponse,
} from "@/lib/api";
import { PageTitle } from "@/lib/meta";
import { inNewTab, useOpenPage, type OpenModifiers } from "@/lib/openPage";
import { trackSaving, useSaveShortcut } from "@/lib/saving";
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
  snapDay,
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

// 左の枠で直している話。id が null なら、空いた所を押して足す話。saved は db の値(足す話は null)、draft は書きかけ(読み込むまで null)
type EpisodePanel = { id: number | null; label: string; saved: EpisodeDraft | null; draft: EpisodeDraft | null };

const draftOf = (record: Record<string, unknown>): EpisodeDraft => ({
  start: (record.start as string | null) ?? null,
  end: (record.end as string | null) ?? null,
  title: String(record.title ?? ""),
  plot: String(record.plot_text ?? ""),
});

/** 話の期間(日)。一点の話と、日の途中に始まる・終わる話は、その日をまるごと含める */
function periodOf(draft: EpisodeDraft | null): { from: number; to: number } | null {
  const start = dayOf(draft?.start);
  if (start === null) return null;
  const end = dayOf(draft?.end) ?? start;
  const from = Math.floor(start);
  return { from, to: Math.max(Math.ceil(end), from + 1) };
}

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
  const [episodePanel, setEpisodePanel] = useState<EpisodePanel | null>(null);
  const [savingEpisode, setSavingEpisode] = useState(false);
  const [panelError, setPanelError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const openPage = useOpenPage();
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

  const draft = episodePanel?.draft ?? null;
  const saved = episodePanel?.saved ?? null;
  const timeChanged = !!draft && (saved === null || draft.start !== saved.start || draft.end !== saved.end);
  const titleChanged = !!draft && draft.title !== (saved?.title ?? "");
  const plotChanged = !!draft && draft.plot !== (saved?.plot ?? "");
  // 足す話は、押した所から入れた時刻だけなら書きかけに数えない
  const dirty =
    episodePanel !== null &&
    (titleChanged || plotChanged || (episodePanel.id !== null && timeChanged));
  const canSave =
    !!draft && !savingEpisode && !!draft.start && (episodePanel?.id === null || dirty);

  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  /** 左の枠の話を閉じる。書きかけがあれば捨ててよいかを尋ね、捨てないなら false */
  const closeEpisode = () => {
    if (dirty && !window.confirm(T.overview.confirmDiscardEpisode)) return false;
    setEpisodePanel(null);
    setPanelError(null);
    return true;
  };

  /** 押した話を左の枠で開く。時刻・タイトル・プロットは開くときに引く(見取り図の応答にプロットは無い) */
  const openEpisode = (episode: OverviewEpisode) => {
    if (episodePanel?.id === episode.id || !closeEpisode()) return;
    setMessage(null);
    setEpisodePanel({ id: episode.id, label: T.nameId(episode.title, episode.id), saved: null, draft: null });
    getRecord("episode", episode.id)
      .then((r) => {
        const loaded = draftOf(r.record);
        setEpisodePanel((p) => (p?.id === episode.id ? { ...p, saved: loaded, draft: loaded } : p));
      })
      .catch((e) => setPanelError(e instanceof Error ? e.message : String(e)));
  };

  /** 話の列の空いた所を押したら、その時刻で選んだ作品に足す話を左の枠に出す */
  const onTrackClick = (e: MouseEvent<HTMLDivElement>) => {
    if (!scale || storyId === null || !closeEpisode()) return;
    setMessage(null);
    const day = snapDay(scale.fromY(e.clientY - e.currentTarget.getBoundingClientRect().top), scale.pxPerDay);
    setEpisodePanel({
      id: null,
      label: T.timeline.newEpisode,
      saved: null,
      draft: { start: formatStamp(fromDayNumber(day)), end: null, title: "", plot: "" },
    });
  };

  /** 別のページへ移る(Ctrl(⌘)を押しながらなら別タブで開き、書きかけは残る) */
  const leaveTo = (url: string, e?: OpenModifiers) => {
    if (!inNewTab(e) && dirty && !window.confirm(T.overview.confirmDiscardEpisode)) return;
    openPage(url, e);
  };

  /** 左の枠の話を保存する(足す話なら選んだ作品に足す)。直した話は変えた欄だけを渡し、時刻はどちらかを変えたら両方を渡す */
  const saveEpisode = async () => {
    if (!episodePanel || !draft || storyId === null || !canSave) return;
    const sent = draft;
    const reread = () => getOverview({ story_id: storyId, margin_days: margin });
    setSavingEpisode(true);
    setPanelError(null);
    setMessage(null);
    try {
      if (episodePanel.id === null) {
        const [created, fresh] = await trackSaving(
          addEpisode({ story_id: storyId }, sent).then(async (created) => [created, await reread()] as const),
        );
        invalidateOptions("episode");
        setData(fresh);
        const id = Number(created.record.id);
        const loaded = draftOf(created.record);
        const label = T.nameId(loaded.title, id);
        // 足したあとも同じ枠で続けて直せるよう、足した話を開いたことにする
        setEpisodePanel((p) => ({ id, label, saved: loaded, draft: p?.draft ?? loaded }));
        setMessage(T.overview.added(label));
      } else {
        const id = episodePanel.id;
        const fresh = await trackSaving(
          updateEpisodes([
            {
              id,
              ...(titleChanged ? { title: sent.title } : {}),
              ...(plotChanged ? { plot_text: sent.plot } : {}),
              ...(timeChanged ? { start: sent.start, end: sent.end } : {}),
            },
          ]).then(reread),
        );
        if (titleChanged) invalidateOptions("episode");
        setData(fresh);
        const label = T.nameId(sent.title, id);
        setEpisodePanel((p) => (p?.id === id ? { ...p, label, saved: sent } : p));
        setMessage(T.timeline.saved(label));
      }
    } catch (e) {
      setPanelError(e instanceof Error ? e.message : String(e));
    } finally {
      setSavingEpisode(false);
    }
  };

  useSaveShortcut(() => void saveEpisode(), canSave);

  // 左の枠の話の期間と、その期間に重なる出来事(絞り込みは出来事の点と同じ)
  const period = periodOf(draft);
  const periodEvents = period
    ? events.filter((event) => {
        const start = dayOf(event.start);
        if (start === null) return false;
        return start < period.to && (dayOf(event.end) ?? start) >= period.from;
      })
    : [];

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
        {/* 足す話は選んだ作品に入れるので、空いた所を押して足せるのは章の列だけ */}
        <div
          className={`timeline-track ${faint ? "overview-readonly" : ""}`}
          style={{ width: packed.lanes * EPISODE_LANE_WIDTH, height: scale?.height }}
          onClick={faint ? undefined : onTrackClick}
        >
          {packed.placed.map(({ episode, y, height, lane }) => (
            <Link
              key={episode.id}
              href={`/tables/episode/${episode.id}`}
              className={`timeline-item ${episode.end ? "" : "point"} ${faint ? "overview-faint" : ""} ${episodePanel?.id === episode.id ? "selected" : ""}`}
              style={{ left: lane * EPISODE_LANE_WIDTH + 2, top: y, width: EPISODE_LANE_WIDTH - 4, height }}
              onClick={(e) => {
                e.stopPropagation();
                // Ctrl(⌘)を押しながらなら、リンクのまま別タブで話のページを開く
                if (inNewTab(e)) return;
                e.preventDefault();
                openEpisode(episode);
              }}
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

  /** 押した出来事の詳細 */
  const renderEvent = (event: OverviewEvent) => (
    <section className="overview-panel-section">
      <div className="overview-panel-head">
        <h2>{event.name}</h2>
        <button type="button" className="ghost" title={T.close} onClick={() => setSelected(null)}>
          ×
        </button>
      </div>
      <div className="timeline-sheet">
        {[
          T.span(event.start, event.end) || event.start,
          event.location_name,
          `${T.overview.size(event.size.total)}: ${T.overview.sizeParts(event.size)}`,
          event.actor_id !== null && `${T.overview.actor}: ${names.get(event.actor_id)}`,
          event.invited_ids.length > 0 &&
            `${T.overview.invited}: ${event.invited_ids.map((id) => names.get(id)).join(", ")}`,
          `${T.overview.participants}: ${event.character_ids.map((id) => names.get(id)).join(", ")}`,
          event.hidden && T.overview.hidden,
        ]
          .filter(Boolean)
          .join("\n")}
      </div>
      {event.text && <div className="timeline-sheet">{event.text}</div>}
      {event.expansion_prompt && (
        <div className="field">
          <label>{T.overview.dialogue}</label>
          <div className="timeline-sheet">{event.expansion_prompt}</div>
        </div>
      )}
      {event.expansion_summary && (
        <div className="field">
          <label>{T.overview.summary}</label>
          <div className="timeline-sheet">{event.expansion_summary}</div>
        </div>
      )}
      <div className="overview-panel-actions">
        {event.expansion_id !== null && (
          <button type="button" onClick={(e) => leaveTo("/expansions", e)}>
            {T.overview.openExpansion(event.expansion_id)}
          </button>
        )}
        <button type="button" onClick={(e) => leaveTo(`/tables/event/${event.id}`, e)}>
          {T.overview.openEvent}
        </button>
      </div>
    </section>
  );

  /** 左の枠。開いた話の欄と、その期間の出来事(押した出来事があればその詳細)を出す。どちらも無ければ出さない */
  const renderPanel = () => {
    if (!episodePanel && !selected) return null;
    return (
      <aside className="overview-panel">
        {episodePanel && (
          <section className="overview-panel-section">
            <div className="overview-panel-head">
              <h2>{episodePanel.label}</h2>
              <button type="button" className="ghost" title={T.close} onClick={closeEpisode} disabled={savingEpisode}>
                ×
              </button>
            </div>
            {panelError && <div className="status error">{panelError}</div>}
            {episodePanel.id === null && (
              <div className="hint">{T.timeline.newEpisodeIn(data?.story_name ?? T.nameId(null, storyId))}</div>
            )}
            {draft ? (
              <EpisodeFields
                value={draft}
                onChange={(next) => setEpisodePanel((p) => (p ? { ...p, draft: next } : p))}
                disabled={savingEpisode}
                onSave={canSave ? () => void saveEpisode() : undefined}
              />
            ) : (
              !panelError && <div className="status info">{T.loading}</div>
            )}
            <div className="overview-panel-actions">
              <button
                type="button"
                disabled={!draft || savingEpisode}
                onClick={(e) =>
                  episodePanel.id === null
                    ? draft && leaveTo(newEpisodeUrl({ story_id: storyId }, draft), e)
                    : leaveTo(`/tables/episode/${episodePanel.id}`, e)
                }
              >
                {episodePanel.id === null ? T.timeline.openForm : T.openRecord}
              </button>
              <span className="spacer" />
              <button type="button" className="primary" disabled={!canSave} onClick={() => void saveEpisode()}>
                {episodePanel.id === null ? T.timeline.addEpisode : T.record.save}
              </button>
            </div>
          </section>
        )}
        {selected
          ? renderEvent(selected)
          : episodePanel &&
            period && (
              <section className="overview-panel-section">
                <div className="overview-panel-head">
                  <h2>{T.overview.eventsInPeriod(periodEvents.length)}</h2>
                </div>
                {periodEvents.length === 0 ? (
                  <div className="hint">{T.overview.noEventsInPeriod}</div>
                ) : (
                  <ul className="overview-period-events">
                    {periodEvents.map((event) => (
                      <li key={event.id}>
                        <button
                          type="button"
                          className="overview-partner"
                          onClick={() => {
                            // 押すと一覧が詳細に替わり、ボタンから外れたことにならないので、吹き出しはここで消す
                            hide();
                            setSelected(event);
                          }}
                          onMouseMove={(e) => show(e, eventLines(event))}
                          onMouseLeave={hide}
                        >
                          {event.name}
                        </button>{" "}
                        <span className="hint">
                          {T.span(event.start, event.end) || event.start}
                          {event.character_ids.length > 0 &&
                            ` · ${event.character_ids.map((id) => names.get(id)).join(", ")}`}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            )}
      </aside>
    );
  };

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
            onChange={(value) => {
              if (!closeEpisode()) return;
              setSelected(null);
              setMessage(null);
              navigate({ story_id: value });
            }}
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
      {message && !error && <div className="status ok">{message}</div>}
      {storyId === null ? (
        <div className="status info">{T.overview.pickStory}</div>
      ) : !data ? (
        !error && <div className="status info">{T.loading}</div>
      ) : (
        <div className="overview-split">
        {renderPanel()}
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
                {/* 左の枠で開いた話の期間を、人物の列まで横切る帯で示す */}
                {scale && period && (
                  <div
                    className="overview-period"
                    style={{
                      top: scale.toY(period.from),
                      height: Math.max(2, scale.toY(period.to) - scale.toY(period.from)),
                    }}
                  />
                )}
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
        </div>
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
