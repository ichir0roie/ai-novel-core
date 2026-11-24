"use client";

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
  type PointerEvent,
} from "react";
import EpisodeFields, { addEpisode, type EpisodeDraft } from "@/components/EpisodeFields";
import ImportanceField from "@/components/ImportanceField";
import Modal from "@/components/Modal";
import NewEventModal from "@/components/NewEventModal";
import OpenableText from "@/components/OpenableText";
import { newEpisodeUrl } from "@/components/NewEpisodeModal";
import ReferenceSelect, { invalidateOptions } from "@/components/ReferenceSelect";
import Tooltip, { useTooltip } from "@/components/Tooltip";
import {
  getOverview,
  getRecord,
  updateEpisodes,
  updateEpisodesAndEvents,
  updateRecord,
  deleteEventWithChildren,
  listAllRecords,
  type OverviewEpisode,
  type OverviewEvent,
  type OverviewResponse,
  type Rec,
} from "@/lib/api";
import { PageTitle } from "@/lib/meta";
import { inNewTab, openInNewTab, useOpenPage, type OpenModifiers } from "@/lib/openPage";
import { trackSaving, useSaveShortcut } from "@/lib/saving";
import { CalendarProvider, convertForWrite, useStoryScope } from "@/lib/scope";
import { fromDayNumber, formatStamp, shiftDays, type Calendar } from "@/lib/stamp";
import PageHelp from "@/components/PageHelp";
import { T } from "@/lib/text";
import {
  DEFAULT_VIEW,
  DRAG_THRESHOLD,
  GAP_PX,
  ITEM_GAP,
  ITEM_HEIGHT,
  axisTicksOf,
  dayOf,
  dragSteps,
  savedView,
  scaleOf,
  skipUnits,
  snapDay,
  spanDays,
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
// 話の列の筋の幅(px)
const EPISODE_LANE_WIDTH = 160;
// 出来事の列の筋の幅と、筋の左右の余白(px)。札は筋の幅から余白を引いた幅で、余白に親子を結ぶ線を通す
const EVENT_LANE_WIDTH = 150;
const EVENT_LANE_PAD = 8;
// 出来事の札を描くとき上下に空ける幅(px)。続けて置いた札どうしが接して見えないようにし、その間に親子の線を通せるようにする
const EVENT_MARGIN = 2;
// 画面に見えている期間の前後この画面数ぶんまでは、読んである状態を保つ。足りなければ、前後この画面数ぶんまでを読み足す
const KEEP_SCREENS = 1;
const LOAD_SCREENS = 2;

type Filter = { origin: "all" | "ai" | "user"; minSize: number };
const DEFAULT_FILTER: Filter = { origin: "all", minSize: 0 };

function savedFilter(): Filter {
  try {
    const saved = JSON.parse(localStorage.getItem(FILTER_STORAGE_KEY) ?? "null");
    return {
      origin: saved?.origin === "ai" || saved?.origin === "user" ? saved.origin : "all",
      minSize: Number.isFinite(saved?.minSize) ? Number(saved.minSize) : 0,
    };
  } catch {
    return DEFAULT_FILTER;
  }
}

type Placed = { episode: OverviewEpisode; y: number; height: number; lane: number };
type Packed = { placed: Placed[]; lanes: number };
type TimeRange = { start: string; end: string | null };
// 掴んだ札。mode は、move が札ごと動かす、start・end が上端・下端を動かして期間を変える。
// out・in は出来事の札の右・左の丸点から線を引く(out は落とした先を子に、in は落とした先を親にする。札は動かさない)。
// over は重ねた先の出来事、blocked は重ねても結べない出来事(結ぶと親子が輪になる)
type DragMode = "move" | "start" | "end" | "out" | "in";
type Drag = {
  kind: "episode" | "event";
  id: number;
  mode: DragMode;
  startX: number;
  startY: number;
  dx: number;
  dy: number;
  over: number | null;
  blocked: Set<number>;
};
const isWire = (mode: DragMode) => mode === "out" || mode === "in";
// 押した親子の線と、押した所(出来事の列の中の位置)
type PickedLink = { parent: number; child: number; x: number; y: number };
// 溜めた変更。札を動かす・親子を結ぶ・外すたびには書かず、ここに溜めて保存のボタンでまとめて書く。
// 値は変えたあとの値で、db の値に戻したら外す。parent は undefined なら親を変えていない、null なら親を外す
type EventChange = { range?: TimeRange; parent?: number | null };
type Pending = { episodes: Map<number, TimeRange>; events: Map<number, EventChange> };
const NO_PENDING: Pending = { episodes: new Map(), events: new Map() };
const sameRange = (a: TimeRange, b: TimeRange) => a.start === b.start && a.end === b.end;

/** 話の札を、重ならないよう筋に振り分ける(話のタイムラインと同じく、上から空いた筋に入れる) */
function pack(episodes: OverviewEpisode[], scale: Scale, calendar: Calendar | null): Packed {
  const laneEnds: number[] = [];
  const placed = episodes.map((episode) => {
    const start = dayOf(episode.start, calendar) ?? 0;
    const end = dayOf(episode.end, calendar);
    const y = scale.toY(start);
    const height = Math.max(ITEM_HEIGHT, end === null ? 0 : scale.toY(end) - y);
    let lane = laneEnds.findIndex((laneEnd) => laneEnd <= y);
    if (lane < 0) lane = laneEnds.length;
    laneEnds[lane] = y + height + ITEM_GAP;
    return { episode, y, height, lane };
  });
  return { placed, lanes: Math.max(1, laneEnds.length) };
}

/**
 * 話を書く欄を、話の作品の暦の桁に直す。見取り図はどの話も選んだ章の暦で出すが、
 * 入口は話ごとにその作品の暦で時刻を読む(同じ時期のほかの作品が別の暦を持つとき)
 */
function toStoryCalendar(form: Rec, storyId: number, calendar: Calendar | null): Promise<Rec> {
  return convertForWrite(form, ["start", "end"], calendar, { story_id: storyId });
}

/** 読み足した期間の応答を、読んであった応答に足す。話・出来事・名前は id で一つにまとめ、後に読んだ方を取る */
function mergeOverview(a: OverviewResponse, b: OverviewResponse, calendar: Calendar | null): OverviewResponse {
  const byId = <T extends { id: number }>(x: T[], y: T[]) => [...new Map([...x, ...y].map((one) => [one.id, one])).values()];
  const day = (stamp: string) => dayOf(stamp, calendar) ?? 0;
  return {
    ...b,
    since: day(a.since) <= day(b.since) ? a.since : b.since,
    until: day(a.until) >= day(b.until) ? a.until : b.until,
    episodes: byId(a.episodes, b.episodes),
    events: byId(a.events, b.events),
    characters: byId(a.characters, b.characters),
  };
}

type PlacedEvent = { event: OverviewEvent; y: number; height: number; lane: number };
// 札が取る上端・下端(px)。終わりと次の始まりが同じ時刻の札は、同じ筋に隙間なく続けて置く(描くときに上下を EVENT_MARGIN ずつ空ける)
type Cell = { event: OverviewEvent; lane: number; top: number; bottom: number };

const collides = (a: Cell[], b: Cell[]) =>
  a.some((x) => b.some((y) => x.lane === y.lane && x.top < y.bottom && y.top < x.bottom));
const shiftCells = (cells: Cell[], by: number) => cells.map((cell) => ({ ...cell, lane: cell.lane + by }));

/**
 * 出来事の札を筋に振り分ける。親子のある出来事は家族(根と子孫)を一かたまりで組み、子は親のすぐ右の筋に置く。
 * 子の筋がすでに埋まっていれば、子の下の家族ごと右へずらし、親子が必ず隣り合うようにする。
 * 家族と親子の無い出来事(札一枚の家族)を、根の重視度の大きい順(同じなら時刻の早い順)に、空いた一番左の筋から置く。
 * 家族の中の子も同じ順に組むので、重視度の大きい出来事ほど左に寄る。家族の札が並んでいるあいだは、
 * その左端から右端までの筋を家族のものとし、ほかの家族・出来事を間に挟まない。時期が重ならなければ左端の筋に戻る
 */
function packEvents(
  events: OverviewEvent[],
  scale: Scale,
  calendar: Calendar | null,
): { placed: PlacedEvent[]; lanes: number } {
  const startOf = (event: OverviewEvent) => dayOf(event.start, calendar) ?? 0;
  const timed = events
    .filter((event) => dayOf(event.start, calendar) !== null)
    .sort((a, b) => b.importance - a.importance || startOf(a) - startOf(b) || a.id - b.id);
  const ids = new Set(timed.map((event) => event.id));
  const children = new Map<number, OverviewEvent[]>();
  for (const event of timed)
    if (event.parent_event_id != null && ids.has(event.parent_event_id))
      children.set(event.parent_event_id, [...(children.get(event.parent_event_id) ?? []), event]);
  const isRoot = (event: OverviewEvent) => event.parent_event_id == null || !ids.has(event.parent_event_id);
  const seen = new Set<number>();
  /** 根を筋 0 に置いた家族の札。子の家族は、組み終えた札と重ならない一番左(親の右の筋から)へずらして足す */
  const family = (event: OverviewEvent): Cell[] => {
    seen.add(event.id);
    const top = scale.toY(startOf(event));
    const end = dayOf(event.end, calendar);
    const height = Math.max(ITEM_HEIGHT, end === null ? 0 : scale.toY(end) - top);
    const cells: Cell[] = [{ event, lane: 0, top, bottom: top + height }];
    for (const child of children.get(event.id) ?? []) {
      if (seen.has(child.id)) continue;
      const sub = family(child);
      let by = 1;
      while (collides(shiftCells(sub, by), cells)) by++;
      cells.push(...shiftCells(sub, by));
    }
    return cells;
  };
  /** 札が、その時期に並んでいる家族の札の左端から右端までの筋に入るか(同じ筋で重なるときも入る) */
  const inside = (cell: Cell, group: Cell[]) => {
    const lanes = group.filter((other) => other.top < cell.bottom && cell.top < other.bottom).map((other) => other.lane);
    return lanes.length > 0 && Math.min(...lanes) <= cell.lane && cell.lane <= Math.max(...lanes);
  };
  const clash = (a: Cell[], b: Cell[]) => a.some((cell) => inside(cell, b)) || b.some((cell) => inside(cell, a));
  // 置いた家族(親子の無い出来事は札一枚の家族)
  const groups: Cell[][] = [];
  const put = (event: OverviewEvent) => {
    const cells = family(event);
    // 時期の重なる家族だけと比べる(札どうしの比べ合いは、出来事が多いと重くなる)
    const top = Math.min(...cells.map((cell) => cell.top));
    const bottom = Math.max(...cells.map((cell) => cell.bottom));
    const near = groups.filter((group) => group.some((cell) => cell.top < bottom && top < cell.bottom));
    let by = 0;
    while (near.some((group) => clash(shiftCells(cells, by), group))) by++;
    groups.push(shiftCells(cells, by));
  };
  for (const event of timed) if (isRoot(event)) put(event);
  // 親をたどると輪になる出来事は根から届かないので、残りを根として置く
  for (const event of timed) if (!seen.has(event.id)) put(event);
  const placed = groups.flat().map(({ event, lane, top, bottom }) => ({ event, lane, y: top, height: bottom - top }));
  return { placed, lanes: Math.max(1, ...placed.map((one) => one.lane + 1)) };
}

// 左の枠で書いている話。id が null なら、空いた所を押して足す話(足したあとは足した話の id)。saved は db の値(足す話は null)
type EpisodePanel = { id: number | null; label: string; saved: EpisodeDraft | null; draft: EpisodeDraft };

const draftOf = (record: Record<string, unknown>): EpisodeDraft => ({
  start: (record.start as string | null) ?? null,
  end: (record.end as string | null) ?? null,
  title: String(record.title ?? ""),
  plot: String(record.plot_text ?? ""),
});

// 押した話のモーダル。loaded は開くときに引いたタイトル・プロット(見取り図の応答にプロットは無い。引くまで null)
type Viewing = { episode: OverviewEpisode; loaded: { title: string; plot: string } | null };

/** 話の期間(日)。一点の話と、日の途中に始まる・終わる話は、その日をまるごと含める */
function periodOf(draft: EpisodeDraft | null, calendar: Calendar | null): { from: number; to: number } | null {
  const start = dayOf(draft?.start, calendar);
  if (start === null) return null;
  const end = dayOf(draft?.end, calendar) ?? start;
  const from = Math.floor(start);
  return { from, to: Math.max(Math.ceil(end), from + 1) };
}

export default function OverviewPage() {
  const router = useRouter();
  const search = useSearchParams();
  const storyId = Number(search.get("story_id")) || null;
  // 時刻は選んだ章の暦で数える。API も同じ暦で時刻を出す
  const scope = useStoryScope(storyId);
  const calendar = scope?.calendar ?? null;

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
  // 押した出来事のモーダルと、書きかけの名前・本文(開いたときの値が saved)
  const [selected, setSelected] = useState<OverviewEvent | null>(null);
  const [eventForm, setEventForm] = useState<{ name: string; text: string; importance: number } | null>(null);
  const [savingEvent, setSavingEvent] = useState(false);
  const [eventError, setEventError] = useState<string | null>(null);
  const [episodePanel, setEpisodePanel] = useState<EpisodePanel | null>(null);
  const [savingEpisode, setSavingEpisode] = useState(false);
  const [panelError, setPanelError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [drag, setDrag] = useState<Drag | null>(null);
  const [pending, setPending] = useState<Pending>(NO_PENDING);
  const [applying, setApplying] = useState(false);
  const pendingCount = pending.episodes.size + pending.events.size;
  const [link, setLink] = useState<PickedLink | null>(null);
  // 押した話のモーダルと、書きかけの時刻・タイトル・プロット
  const [viewing, setViewing] = useState<Viewing | null>(null);
  const [edit, setEdit] = useState<EpisodeDraft | null>(null);
  const [savingEdit, setSavingEdit] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  // 出来事の列の空いた所を押して足す出来事の、押した時刻
  const [addingEvent, setAddingEvent] = useState<{ start: string } | null>(null);
  const openPage = useOpenPage();
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const scrolledFor = useRef<number | null>(null);
  // 読み足している最中か。スクロールのたびに重ねて読まないようにする
  const loadingMore = useRef(false);
  // 読み足す前に画面の上端にあった時刻。読み足して軸が伸びても、同じ時刻を上端に置き直す
  const keepDay = useRef<number | null>(null);
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
    setPending(NO_PENDING);
    getOverview({ story_id: storyId })
      .then((result) => {
        if (!alive) return;
        setData(result);
        setError(null);
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [storyId]);

  /** 読んである期間を読み直す */
  const reread = () => getOverview({ story_id: storyId!, since: data?.since, until: data?.until });

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

  // 作品の名前。話の吹き出しと、出来事を足す作品に出す
  const storyNames = useMemo(() => {
    const map = new Map<number, string>();
    if (data) map.set(data.story_id, data.story_name ?? T.nameId(null, data.story_id));
    for (const episode of data?.episodes ?? [])
      if (!map.has(episode.story_id)) map.set(episode.story_id, episode.story_name ?? T.nameId(null, episode.story_id));
    return map;
  }, [data]);
  const storyLabel = (id: number) => storyNames.get(id) ?? T.nameId(null, id);

  // 溜めた変更を当てた話と出来事。札の置き場所も、親子・子孫のたどり方も、この値で決める
  const shown = useMemo(() => {
    if (!data) return null;
    return {
      episodes: data.episodes.map((episode) => ({ ...episode, ...pending.episodes.get(episode.id) })),
      events: data.events.map((event) => {
        const change = pending.events.get(event.id);
        if (!change) return event;
        return { ...event, ...change.range, ...(change.parent !== undefined ? { parent_event_id: change.parent } : {}) };
      }),
    };
  }, [data, pending]);
  const episodes = useMemo(() => shown?.episodes ?? [], [shown]);

  // 絞り込んだ出来事
  const events = useMemo(
    () =>
      (shown?.events ?? []).filter(
        (event) =>
          event.size.total >= filter.minSize &&
          (filter.origin === "all" ||
            (filter.origin === "ai" ? event.expansion_id !== null : event.expansion_id === null)),
      ),
    [shown, filter],
  );
  const names = useMemo(
    () => new Map((data?.characters ?? []).map((character) => [character.id, character.name ?? `#${character.id}`])),
    [data],
  );
  // 子を持つ出来事(企て)
  const parentIds = useMemo(
    () => new Set((shown?.events ?? []).map((event) => event.parent_event_id).filter((id) => id != null)),
    [shown],
  );

  const spans: Span[] = useMemo(() => {
    const all: Span[] = [];
    if (!scope || !data) return all;
    // 読んだ期間は、話も出来事も無い所まで軸に含める(スクロールで読み足した先が空でも、その先へ進めるように)
    const since = dayOf(data.since, scope.calendar);
    const until = dayOf(data.until, scope.calendar);
    if (since !== null && until !== null) all.push(timeSpan(since, until));
    for (const item of [...episodes, ...events]) {
      const start = dayOf(item.start, scope.calendar);
      if (start !== null) all.push(timeSpan(start, dayOf(item.end, scope.calendar)));
    }
    return all;
  }, [data, episodes, events, scope]);
  const scale = useMemo(
    () => scaleOf(spans, null, view, box.viewport, calendar),
    [spans, view, box.viewport, calendar],
  );
  const eventPack = useMemo(
    () => (scale ? packEvents(events, scale, calendar) : { placed: [], lanes: 1 }),
    [events, scale, calendar],
  );
  const ticks = useMemo(
    () => (scale ? axisTicksOf(scale, spans, view.squeeze, screen, box.viewport, calendar) : []),
    [scale, spans, view.squeeze, screen, box.viewport, calendar],
  );
  // 話の列。どの作品の話も一つの列に並べ、章の外の話は灰色で描く
  const episodePack = useMemo(() => {
    if (!scale) return { placed: [], lanes: 1 };
    const byTime = [...episodes].sort(
      (a, b) => (dayOf(a.start, calendar) ?? 0) - (dayOf(b.start, calendar) ?? 0) || a.id - b.id,
    );
    return pack(byTime, scale, calendar);
  }, [scale, episodes, calendar]);

  // 読み込んだら、章の最初の話が画面の上の方に来るようにスクロールする
  useLayoutEffect(() => {
    const element = scrollRef.current;
    const first = data?.episodes.find((episode) => episode.in_story);
    if (!element || !scale || !first || storyId === null || scrolledFor.current === storyId) return;
    scrolledFor.current = storyId;
    element.scrollTop = Math.max(0, scale.toY(dayOf(first.start, calendar) ?? 0) - box.viewport / 4);
  }, [data, scale, storyId, box.viewport, calendar]);

  // 読み足して軸が伸びたら、読み足す前に上端にあった時刻を上端に置き直す
  const scaleRef = useRef(scale);
  useLayoutEffect(() => {
    scaleRef.current = scale;
    const element = scrollRef.current;
    if (!element || !scale || keepDay.current === null) return;
    element.scrollTop = scale.toY(keepDay.current);
    keepDay.current = null;
  }, [scale]);

  /**
   * 画面に見えている期間(前後に KEEP_SCREENS 枚の余白)が読んであるようにする。話の期間に関わらず、見えている所の出来事を出すため。
   * 足りない端だけを、前後 LOAD_SCREENS 枚ぶんまで読み足す(両端とも足りなければ、その全体を読む)
   */
  const loadVisible = () => {
    const element = scrollRef.current;
    if (!element || !scale || !data || storyId === null || loadingMore.current || box.viewport === 0) return;
    const since = dayOf(data.since, calendar);
    const until = dayOf(data.until, calendar);
    if (since === null || until === null) return;
    const screen = spanDays(view, calendar);
    const top = scale.fromY(element.scrollTop);
    const bottom = scale.fromY(element.scrollTop + box.viewport);
    if (top - screen * KEEP_SCREENS >= since && bottom + screen * KEEP_SCREENS <= until) return;
    const [lo, hi] = [top - screen * LOAD_SCREENS, bottom + screen * LOAD_SCREENS];
    const stamp = (day: number) => formatStamp(fromDayNumber(day, calendar));
    const range = { since: lo < since ? stamp(lo) : data.until, until: hi > until ? stamp(hi) : data.since };
    loadingMore.current = true;
    getOverview({ story_id: storyId, ...range })
      .then((more) => {
        // 読んでいるあいだにもスクロールするので、上端の時刻は読み終えたときのものを取る
        const now = scaleRef.current;
        if (now && scrollRef.current) keepDay.current = now.fromY(scrollRef.current.scrollTop);
        setData((previous) => (previous?.story_id === more.story_id ? mergeOverview(previous, more, calendar) : previous));
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => {
        loadingMore.current = false;
      });
  };

  const onScroll = () => {
    const element = scrollRef.current;
    if (!element || box.viewport === 0) return;
    setScreen(Math.floor(element.scrollTop / box.viewport));
    loadVisible();
  };
  // 開いたとき・縮尺や画面の高さを変えたとき・読み足して軸が伸びたときも、スクロールを待たずに見えている所を読む。
  // 描くたびに確かめるが、読んであれば何もしない
  useEffect(loadVisible);

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

  // 押した話は、書いたあと読み直した時刻を出す
  const viewingNow = viewing ? (episodes.find((episode) => episode.id === viewing.episode.id) ?? viewing.episode) : null;
  const loaded = viewing?.loaded ?? null;
  const editTimeChanged = !!edit && !!viewingNow && (edit.start !== viewingNow.start || edit.end !== viewingNow.end);
  const editTitleChanged = !!edit && !!loaded && edit.title !== loaded.title;
  const editPlotChanged = !!edit && !!loaded && edit.plot !== loaded.plot;
  const editDirty = editTimeChanged || editTitleChanged || editPlotChanged;
  const canSaveEdit = editDirty && !savingEdit && !!edit?.start;

  const eventDirty =
    !!selected &&
    !!eventForm &&
    (eventForm.name !== selected.name ||
      eventForm.text !== selected.text ||
      eventForm.importance !== selected.importance);
  const canSaveEvent = eventDirty && !savingEvent && !!eventForm?.name.trim();

  useEffect(() => {
    if (!dirty && !editDirty && !eventDirty && pendingCount === 0) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty, editDirty, eventDirty, pendingCount]);

  /** 溜めた変更を捨てる。捨ててよいかを尋ね、捨てないなら false */
  const discardPending = () => {
    if (pendingCount > 0 && !window.confirm(T.timeline.confirmDiscard(pendingCount))) return false;
    setPending(NO_PENDING);
    return true;
  };

  /** 左の枠の話を閉じる。書きかけがあれば捨ててよいかを尋ね、捨てないなら false */
  const closeEpisode = () => {
    if (dirty && !window.confirm(T.overview.confirmDiscardEpisode)) return false;
    setEpisodePanel(null);
    setPanelError(null);
    return true;
  };

  /** 押した話をモーダルで開く(話のタイムラインと同じ)。タイトル・プロットは開くときに引く */
  const openViewing = (episode: OverviewEpisode) => {
    setViewing({ episode, loaded: null });
    setEdit(null);
    setEditError(null);
    getRecord("episode", episode.id)
      .then((r) => {
        const record = draftOf(r.record);
        setViewing((v) => (v?.episode.id === episode.id ? { ...v, loaded: { title: record.title ?? "", plot: record.plot } } : v));
        setEdit({ start: episode.start, end: episode.end, title: record.title ?? "", plot: record.plot });
      })
      .catch((e) => setEditError(e instanceof Error ? e.message : String(e)));
  };

  /** 押した出来事をモーダルで開く(出来事のタイムラインと同じく、名前と本文を直せる) */
  const openEvent = (event: OverviewEvent) => {
    setSelected(event);
    setEventForm({ name: event.name, text: event.text, importance: event.importance });
    setEventError(null);
  };

  /** 出来事のモーダルを閉じる。書きかけがあれば捨ててよいかを尋ね、捨てないなら false */
  const closeEvent = () => {
    if (eventDirty && !window.confirm(T.eventTimeline.confirmDiscardEdit)) return false;
    setSelected(null);
    setEventForm(null);
    return true;
  };

  /** 押した話のモーダルを閉じる。書きかけがあれば捨ててよいかを尋ねる */
  const closeViewing = () => {
    if (editDirty && !window.confirm(T.overview.confirmDiscardEpisode)) return;
    setViewing(null);
    setEdit(null);
  };

  /** 話の列の空いた所を押したら、その時刻で選んだ作品に足す話を左の枠に出す */
  const onTrackClick = (e: MouseEvent<HTMLDivElement>) => {
    if (!scale || storyId === null || !closeEpisode()) return;
    setMessage(null);
    const day = snapDay(scale.fromY(e.clientY - e.currentTarget.getBoundingClientRect().top), scale.pxPerDay, calendar);
    setEpisodePanel({
      id: null,
      label: T.timeline.newEpisode,
      saved: null,
      draft: { start: formatStamp(fromDayNumber(day, calendar)), end: null, title: "", plot: "" },
    });
  };

  /** 出来事の列の空いた所を押したら、その時刻で出来事を足すモーダルを出す(出来事のタイムラインと同じ) */
  const onEventTrackClick = (e: MouseEvent<HTMLDivElement>) => {
    // 線のボタンを出しているときは、空いた所を押したらボタンを閉じるだけにする
    if (link) return setLink(null);
    if (!scale) return;
    hide();
    setMessage(null);
    const day = snapDay(scale.fromY(e.clientY - e.currentTarget.getBoundingClientRect().top), scale.pxPerDay, calendar);
    setAddingEvent({ start: formatStamp(fromDayNumber(day, calendar)) });
  };

  /** 別のページへ移る(Ctrl(⌘)を押しながらなら別タブで開き、書きかけは残る) */
  const leaveTo = (url: string, e?: OpenModifiers) => {
    if (!inNewTab(e)) {
      if ((dirty || editDirty) && !window.confirm(T.overview.confirmDiscardEpisode)) return;
      if (eventDirty && !window.confirm(T.eventTimeline.confirmDiscardEdit)) return;
      if (pendingCount > 0 && !window.confirm(T.timeline.confirmDiscard(pendingCount))) return;
    }
    openPage(url, e);
  };

  /** 話の作品 */
  const storyOf = (id: number) => data?.episodes.find((episode) => episode.id === id)?.story_id ?? storyId!;

  /** 左の枠の話を保存する(足す話なら選んだ作品に足す)。直した話は変えた欄だけを渡し、時刻はどちらかを変えたら両方を渡す */
  const saveEpisode = async () => {
    if (!episodePanel || !draft || storyId === null || !canSave) return;
    const sent = draft;
    setSavingEpisode(true);
    setPanelError(null);
    setMessage(null);
    try {
      if (episodePanel.id === null) {
        const [created, fresh] = await trackSaving(
          addEpisode({ story_id: storyId }, sent, calendar).then(async (created) => [created, await reread()] as const),
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
          toStoryCalendar(
            {
              id,
              ...(titleChanged ? { title: sent.title } : {}),
              ...(plotChanged ? { plot_text: sent.plot } : {}),
              ...(timeChanged ? { start: sent.start, end: sent.end } : {}),
            },
            storyOf(id),
            calendar,
          )
            .then((form) => updateEpisodes([form]))
            .then(reread),
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

  /** 押した話の時刻・タイトル・プロットを保存する。時刻はどちらかを変えたら両方を渡す(溜めた移しを当てた時刻を書くため) */
  const saveEdit = async () => {
    if (!viewingNow || !edit || !canSaveEdit) return;
    const id = viewingNow.id;
    const sent = edit;
    setSavingEdit(true);
    setEditError(null);
    setError(null);
    setMessage(null);
    try {
      const fresh = await trackSaving(
        toStoryCalendar(
          {
            id,
            ...(editTitleChanged ? { title: sent.title } : {}),
            ...(editPlotChanged ? { plot_text: sent.plot } : {}),
            ...(editTimeChanged ? { start: sent.start, end: sent.end } : {}),
          },
          storyOf(id),
          calendar,
        )
          .then((form) => updateEpisodes([form]))
          .then(reread),
      );
      if (editTitleChanged) invalidateOptions("episode");
      setData(fresh);
      // 書いた時刻が db の値になったので、溜めてあった同じ話の時刻は外す
      if (editTimeChanged)
        setPending((p) => {
          const episodes = new Map(p.episodes);
          episodes.delete(id);
          return { ...p, episodes };
        });
      const written = fresh.episodes.find((episode) => episode.id === id);
      setViewing((v) =>
        v?.episode.id === id
          ? { episode: written ?? v.episode, loaded: { title: sent.title ?? "", plot: sent.plot } }
          : v,
      );
      setMessage(T.timeline.saved(T.nameId(sent.title, id)));
    } catch (e) {
      setEditError(e instanceof Error ? e.message : String(e));
    } finally {
      setSavingEdit(false);
    }
  };

  /** 出来事のモーダルの名前・本文を書く(変えた欄だけ) */
  const saveEvent = async () => {
    if (!selected || !eventForm || !canSaveEvent) return;
    const sent = eventForm;
    setSavingEvent(true);
    setEventError(null);
    setMessage(null);
    try {
      const [response, fresh] = await trackSaving(
        updateRecord("event", selected.id, {
          ...(sent.name !== selected.name ? { name: sent.name } : {}),
          ...(sent.text !== selected.text ? { text: sent.text } : {}),
          ...(sent.importance !== selected.importance ? { importance: sent.importance } : {}),
        }).then(async (response) => [response, await reread()] as const),
      );
      invalidateOptions("event");
      setData(fresh);
      const shown = fresh.events.find((event) => event.id === selected.id);
      if (shown) {
        setSelected(shown);
        setEventForm({ name: shown.name, text: shown.text, importance: shown.importance });
      }
      setMessage(T.eventTimeline.saved(response.label));
    } catch (e) {
      setEventError(e instanceof Error ? e.message : String(e));
    } finally {
      setSavingEvent(false);
    }
  };

  /** 出来事を子孫の出来事ごと消す。画面は読んだ期間の出来事しか持たないので、子孫は db から辿って数えて尋ねる */
  const removeEvent = async (event: OverviewEvent) => {
    setEventError(null);
    setMessage(null);
    try {
      const descendants: number[] = [];
      const walk = async (id: number) => {
        for (const child of await listAllRecords("event", { parent_event_id: String(id) })) {
          descendants.push(Number(child.id));
          await walk(Number(child.id));
        }
      };
      await walk(event.id);
      const label = T.nameId(event.name, event.id);
      if (!window.confirm(T.eventTimeline.confirmDelete(label, descendants.length))) return;
      setSavingEvent(true);
      const fresh = await trackSaving(deleteEventWithChildren(event.id).then(reread));
      invalidateOptions("event");
      setData(fresh);
      // 消した出来事に溜めてあった移しと、消した出来事を親にする溜めた結び直しは当てられないので外す
      const gone = new Set([event.id, ...descendants]);
      setPending((p) => {
        const events = new Map<number, EventChange>();
        for (const [id, change] of p.events) {
          if (gone.has(id)) continue;
          if (change.parent == null || !gone.has(change.parent)) events.set(id, change);
          else if (change.range) events.set(id, { range: change.range });
        }
        return { ...p, events };
      });
      setSelected(null);
      setEventForm(null);
      setMessage(T.eventTimeline.deleted(label));
    } catch (e) {
      setEventError(e instanceof Error ? e.message : String(e));
    } finally {
      setSavingEvent(false);
    }
  };

  /** 話の時刻の変更を溜める */
  const stageEpisode = (id: number, range: TimeRange) =>
    setPending((p) => {
      const original = data?.episodes.find((one) => one.id === id);
      const episodes = new Map(p.episodes);
      if (original && sameRange(original, range)) episodes.delete(id);
      else episodes.set(id, range);
      return { ...p, episodes };
    });

  /** 出来事の時刻・親の変更を溜める(前に溜めた分に重ねる) */
  const stageEvent = (id: number, change: EventChange) =>
    setPending((p) => {
      const original = data?.events.find((one) => one.id === id);
      const next = { ...p.events.get(id), ...change };
      if (original && next.range && sameRange(original, next.range)) delete next.range;
      if (original && next.parent !== undefined && next.parent === original.parent_event_id) delete next.parent;
      const events = new Map(p.events);
      if (next.range === undefined && next.parent === undefined) events.delete(id);
      else events.set(id, next);
      return { ...p, events };
    });

  /** 溜めた変更を一つのトランザクションでまとめて書き、読んである期間を読み直す。時刻は行ごとにその作品の暦の桁に直す */
  const applyPending = async () => {
    if (pendingCount === 0 || applying) return;
    const sent = pending;
    setApplying(true);
    setError(null);
    setMessage(null);
    try {
      const fresh = await trackSaving(
        Promise.all([
          Promise.all(
            [...sent.episodes].map(([id, range]) =>
              toStoryCalendar({ id, start: range.start, end: range.end }, storyOf(id), calendar),
            ),
          ),
          Promise.all(
            [...sent.events].map(([id, change]) =>
              convertForWrite(
                {
                  id,
                  ...(change.range ? { time: change.range.start, end: change.range.end } : {}),
                  ...(change.parent !== undefined ? { parent_event_id: change.parent } : {}),
                },
                ["time", "end"],
                calendar,
                { table: "event", id },
              ),
            ),
          ),
        ])
          .then(([episodeForms, eventForms]) => updateEpisodesAndEvents(episodeForms, eventForms))
          .then(reread),
      );
      // 読み直した値と溜めた分を外すのを同じ描画で替え、札が元の所へ一度戻って見えないようにする
      setData(fresh);
      setPending(NO_PENDING);
      setMessage(T.overview.applied(sent.episodes.size + sent.events.size));
    } catch (e) {
      setError(T.timeline.applyFailed(e instanceof Error ? e.message : String(e)));
    } finally {
      setApplying(false);
    }
  };

  /** 丸点から引いた線を落とした先と結ぶ。右の点(out)からなら落とした先を子に、左の点(in)からなら落とした先を親にする */
  const stageWire = (event: OverviewEvent, mode: DragMode, over: number) => {
    const [child, parent] = mode === "out" ? [over, event.id] : [event.id, over];
    stageEvent(child, { parent });
  };

  // 出来事・話のモーダルを開いていればその行を、左の枠に書きかけがあればその話を、溜めた変更があればそれを保存する
  useSaveShortcut(() => {
    if (selected) {
      if (canSaveEvent) void saveEvent();
    } else if (viewingNow) {
      if (canSaveEdit) void saveEdit();
    } else {
      if (canSave) void saveEpisode();
      if (pendingCount > 0) void applyPending();
    }
  });

  /** 縦に dy px 動かしたら、時刻 stamp が何日ずれるか(話のタイムラインと同じ刻みに丸める)。詰めた帯の上では一気に日が進む */
  const daysAt = (stamp: string, dy: number) => {
    const at = dayOf(stamp, calendar);
    if (!scale || scale.pxPerDay === 0 || at === null) return 0;
    const steps = dragSteps(view, calendar);
    return Math.round((scale.fromY(scale.toY(at) + dy) - at) * steps) / steps;
  };

  /** 掴んで動かしている札の、動かしたあとの時刻。動かしていない・別の出来事に重ねているなら null */
  const draggedRange = (range: TimeRange, d: Drag | null): TimeRange | null => {
    if (!d || isWire(d.mode) || d.over !== null || Math.abs(d.dy) <= DRAG_THRESHOLD) return null;
    const at = (stamp: string) => dayOf(stamp, calendar) ?? 0;
    const shift = (stamp: string, days: number) => shiftDays(stamp, days, calendar) ?? stamp;
    if (d.mode === "move") {
      const days = daysAt(range.start, d.dy);
      return days === 0 ? null : { start: shift(range.start, days), end: range.end && shift(range.end, days) };
    }
    if (d.mode === "start") {
      // 始まりは終わりを越えない。越えたら終わりの時刻の一点にする
      const end = range.end ?? range.start;
      const start = shift(range.start, daysAt(range.start, d.dy));
      return at(start) >= at(end) ? { start: end, end: null } : { start, end };
    }
    // 終わりは始まりより前にしない。始まりまで縮めたら一点にする
    const base = range.end ?? range.start;
    const end = shift(base, daysAt(base, d.dy));
    return at(end) <= at(range.start) ? { start: range.start, end: null } : { start: range.start, end };
  };

  /** 出来事の子孫(読んである分) */
  const descendantsOf = (id: number) => {
    const found = new Set<number>();
    const walk = (at: number) => {
      for (const event of shown?.events ?? [])
        if (event.parent_event_id === at && !found.has(event.id)) {
          found.add(event.id);
          walk(event.id);
        }
    };
    walk(id);
    return found;
  };

  /** 出来事の祖先(読んである分) */
  const ancestorsOf = (id: number) => {
    const found = new Set<number>();
    for (let at = shown?.events.find((one) => one.id === id); at?.parent_event_id != null && !found.has(at.parent_event_id); ) {
      found.add(at.parent_event_id);
      at = shown?.events.find((one) => one.id === at!.parent_event_id);
    }
    return found;
  };

  /** 指の下の出来事の札。blocked(結ぶと親子が輪になる出来事)は除く */
  const eventUnder = (x: number, y: number, blocked: Set<number>): number | null => {
    const card = document
      .elementsFromPoint(x, y)
      .map((el) => el.closest<HTMLElement>(".overview-events .timeline-item[data-id]"))
      .find((el) => el && !blocked.has(Number(el.dataset.id)));
    return card ? Number(card.dataset.id) : null;
  };

  /**
   * 札を掴む。上端・下端の帯(data-edge)を掴んだら期間を、出来事の左右の丸点(data-port)を掴んだら親子の線を、
   * それ以外は札ごと時刻を動かす。子にする出来事に、その子孫は親として結べない
   */
  const onItemDown = (e: PointerEvent<HTMLDivElement>, kind: Drag["kind"], id: number) => {
    if (e.button !== 0 || applying) return;
    e.stopPropagation();
    e.currentTarget.setPointerCapture(e.pointerId);
    hide();
    setLink(null);
    const { edge, port } = (e.target as HTMLElement).dataset;
    const mode: DragMode =
      edge === "start" || edge === "end" ? edge : port === "out" || port === "in" ? port : "move";
    const blocked =
      kind !== "event"
        ? new Set<number>()
        : mode === "move" || mode === "in"
          ? new Set([id, ...descendantsOf(id)])
          : mode === "out"
            ? new Set([id, ...ancestorsOf(id)])
            : new Set<number>();
    setDrag({ kind, id, mode, startX: e.clientX, startY: e.clientY, dx: 0, dy: 0, over: null, blocked });
  };

  const onItemMove = (e: PointerEvent<HTMLDivElement>) => {
    if (!drag) return;
    const moved = Math.abs(e.clientX - drag.startX) > DRAG_THRESHOLD || Math.abs(e.clientY - drag.startY) > DRAG_THRESHOLD;
    setDrag({
      ...drag,
      dx: e.clientX - drag.startX,
      dy: e.clientY - drag.startY,
      over:
        drag.kind === "event" && (drag.mode === "move" || isWire(drag.mode)) && moved
          ? eventUnder(e.clientX, e.clientY, drag.blocked)
          : null,
    });
  };

  /**
   * 札を離す。動かさずに離したら開き、出来事の札に重ねたらその子にし(時刻は動かさない)、それ以外は動かした時刻にする。
   * 丸点から引いた線は、出来事の札の上で離したときだけ結ぶ。どれも溜めるだけで、書くのは保存のボタンを押したとき
   */
  const onItemUp = (e: PointerEvent<HTMLDivElement>) => {
    if (!drag) return;
    const d = { ...drag, dx: e.clientX - drag.startX, dy: e.clientY - drag.startY };
    setDrag(null);
    const episode = d.kind === "episode" ? shown?.episodes.find((one) => one.id === d.id) : undefined;
    const event = d.kind === "event" ? shown?.events.find((one) => one.id === d.id) : undefined;
    if (isWire(d.mode)) {
      if (event && d.over !== null) stageWire(event, d.mode, d.over);
      return;
    }
    if (Math.abs(d.dx) <= DRAG_THRESHOLD && Math.abs(d.dy) <= DRAG_THRESHOLD) {
      // Ctrl(⌘)を押しながらなら、行のページを別タブで開く
      if (episode) {
        if (inNewTab(e)) openInNewTab(`/tables/episode/${episode.id}`);
        else openViewing(episode);
      } else if (event) {
        if (inNewTab(e)) openInNewTab(`/tables/event/${event.id}`);
        else openEvent(event);
      }
      return;
    }
    if (event && d.over !== null) {
      stageEvent(event.id, { parent: d.over });
      return;
    }
    const item = episode ?? event;
    const range = item && draggedRange({ start: item.start, end: item.end }, d);
    if (!range || sameRange(range, item)) return;
    if (episode) stageEpisode(episode.id, range);
    else if (event) stageEvent(event.id, { range });
  };

  /** 札を掴んでいるあいだ、札を動かしたあとの時刻の所に描く。返すのは上端・高さと、動かしたあとの時刻 */
  const dragPreview = (kind: Drag["kind"], id: number, range: TimeRange) => {
    if (!scale || drag?.kind !== kind || drag.id !== id) return null;
    const moved = draggedRange(range, drag);
    if (!moved) return null;
    const y = scale.toY(dayOf(moved.start, calendar) ?? 0);
    const end = dayOf(moved.end, calendar);
    return { y, height: Math.max(ITEM_HEIGHT, end === null ? 0 : scale.toY(end) - y), range: moved };
  };

  /** 札の上端・下端の掴む所 */
  const edges = (
    <>
      <span className="overview-edge start" data-edge="start" />
      <span className="overview-edge end" data-edge="end" />
    </>
  );

  // 左の枠の話の期間と、その期間に重なる出来事(絞り込みは出来事の点と同じ)
  const period = periodOf(draft, calendar);
  const periodEvents = period
    ? events.filter((event) => {
        const start = dayOf(event.start, calendar);
        if (start === null) return false;
        return start < period.to && (dayOf(event.end, calendar) ?? start) >= period.from;
      })
    : [];

  const eventLines = (event: OverviewEvent) => [
    T.nameId(event.name, event.id),
    T.span(event.start, event.end) || event.start,
    event.location_name ?? "",
    T.overview.size(event.size.total),
    event.character_ids.map((id) => names.get(id)).join(", "),
  ];
  const gapLines = (g: Gap) => [
    T.overview.gap,
    `${formatStamp(fromDayNumber(g.from, calendar))} – ${formatStamp(fromDayNumber(g.to, calendar))}`,
  ];
  /** 吹き出しと押したときのモーダルに出す、時刻・作品 */
  const detailLines = (episode: OverviewEpisode) => [
    T.span(episode.start, episode.end) || episode.start,
    storyLabel(episode.story_id),
  ];

  const renderEpisodes = () => (
    <div className="timeline-track" style={{ width: episodePack.lanes * EPISODE_LANE_WIDTH, height: scale?.height }} onClick={onTrackClick}>
      {episodePack.placed.map(({ episode, y, height, lane }) => {
        const preview = dragPreview("episode", episode.id, episode);
        const className = [
          "timeline-item",
          episode.end ? "" : "point",
          episode.in_story ? "" : "overview-other",
          viewing?.episode.id === episode.id || episodePanel?.id === episode.id ? "selected" : "",
          drag?.kind === "episode" && drag.id === episode.id ? "dragging" : "",
          pending.episodes.has(episode.id) ? "changed" : "",
          applying && pending.episodes.has(episode.id) ? "saving" : "",
        ].join(" ");
        return (
          <div
            key={episode.id}
            className={className}
            style={{
              left: lane * EPISODE_LANE_WIDTH + 2,
              top: preview?.y ?? y,
              width: EPISODE_LANE_WIDTH - 4,
              height: preview?.height ?? height,
            }}
            onPointerDown={(e) => onItemDown(e, "episode", episode.id)}
            onPointerMove={onItemMove}
            onPointerUp={onItemUp}
            onPointerCancel={() => setDrag(null)}
            onClick={(e) => e.stopPropagation()}
            onMouseMove={(e) => !drag && show(e, [episode.title ?? `#${episode.id}`, ...detailLines(episode)])}
            onMouseLeave={hide}
          >
            {edges}
            <span className="timeline-text">
              {episode.title ?? `#${episode.id}`}
              {preview && <span className="timeline-target"> → {T.span(preview.range.start, preview.range.end) || preview.range.start}</span>}
            </span>
          </div>
        );
      })}
    </div>
  );

  const renderEvents = () => {
    const { placed, lanes } = eventPack;
    const byId = new Map(placed.map((one) => [one.event.id, one]));
    const left = (lane: number) => lane * EVENT_LANE_WIDTH + EVENT_LANE_PAD;
    const right = (lane: number) => (lane + 1) * EVENT_LANE_WIDTH - EVENT_LANE_PAD;
    // 筋ごとの札の上端・下端。親子の線が、間の筋の札を横切らない高さを探すのに使う
    const byLane = new Map<number, PlacedEvent[]>();
    for (const one of placed) byLane.set(one.lane, [...(byLane.get(one.lane) ?? []), one]);
    const clear = (from: number, to: number, y: number) => {
      for (let lane = from; lane < to; lane++)
        if ((byLane.get(lane) ?? []).some((one) => one.y + EVENT_MARGIN <= y && y <= one.y + one.height - EVENT_MARGIN))
          return false;
      return true;
    };
    // 親の札の右から子の札の左へ、筋の間の余白で折れる線を引く(出来事のタイムラインと同じ)。
    // 子が隣より右の筋にあれば、横の線は間の筋が空いた高さに通す。その高さが親の期間の外なら、親のすぐ右の余白で縦に折ってから渡る
    const links = placed.flatMap((child) => {
      const parent = child.event.parent_event_id == null ? undefined : byId.get(child.event.parent_event_id);
      if (!parent) return [];
      const y2 = child.y + ITEM_HEIGHT / 2;
      const [low, high] = [parent.y + 4, parent.y + parent.height - 4];
      const near = Math.min(Math.max(y2, parent.y + ITEM_HEIGHT / 2), high);
      const between = [...Array(Math.max(0, child.lane - parent.lane - 1)).keys()].flatMap(
        (i) => byLane.get(parent.lane + 1 + i) ?? [],
      );
      const across =
        [near, ...between.flatMap((one) => [one.y, one.y + one.height])]
          .sort((a, b) => Number(b >= low && b <= high) - Number(a >= low && a <= high) || Math.abs(a - y2) - Math.abs(b - y2))
          .find((y) => clear(parent.lane + 1, child.lane, y)) ?? near;
      const [x1, x2] = [right(parent.lane), left(child.lane)];
      const xm = x2 - EVENT_LANE_PAD;
      const out = Math.min(Math.max(across, low), high);
      const d =
        out === across
          ? `M ${x1} ${across} H ${xm} V ${y2} H ${x2}`
          : `M ${x1} ${out} H ${x1 + EVENT_LANE_PAD} V ${across} H ${xm} V ${y2} H ${x2}`;
      return [{ key: `${parent.event.id}-${child.event.id}`, parent: parent.event.id, child: child.event.id, d }];
    });
    // 丸点から引いている線。重ねた札があれば、結んだときに線が付く側の丸点まで引く
    const wiring = drag?.kind === "event" && isWire(drag.mode) ? drag : null;
    const wireFrom = wiring ? byId.get(wiring.id) : undefined;
    const wire = (() => {
      if (!wiring || !wireFrom || Math.hypot(wiring.dx, wiring.dy) <= DRAG_THRESHOLD) return null;
      const out = wiring.mode === "out";
      const [x1, y1] = [out ? right(wireFrom.lane) : left(wireFrom.lane), wireFrom.y + ITEM_HEIGHT / 2];
      const target = wiring.over === null ? undefined : byId.get(wiring.over);
      const [x2, y2] = target
        ? [out ? left(target.lane) : right(target.lane), target.y + ITEM_HEIGHT / 2]
        : [x1 + wiring.dx, y1 + wiring.dy];
      return { d: `M ${x1} ${y1} L ${x2} ${y2}`, target };
    })();
    // 左右の丸点。札の上から ITEM_HEIGHT / 2 の高さ(親子の線が付く高さ)に置く
    const portTop = ITEM_HEIGHT / 2 - EVENT_MARGIN - 1;
    const ports = (
      <>
        <span className="overview-port in" data-port="in" style={{ top: portTop }} />
        <span className="overview-port out" data-port="out" style={{ top: portTop }} />
      </>
    );
    return (
      <div
        className={`timeline-track overview-events ${wiring ? "wiring" : ""}`}
        style={{ width: lanes * EVENT_LANE_WIDTH, height: scale?.height }}
        onClick={onEventTrackClick}
      >
        {/* 線を押すと、親子を外すボタンを出す。細い線でも押せるよう、透明の太い線を重ねる */}
        <svg className="overview-links" width={lanes * EVENT_LANE_WIDTH} height={scale?.height ?? 0}>
          {links.map((one) => (
            <g
              key={one.key}
              className={link?.parent === one.parent && link.child === one.child ? "picked" : ""}
              onClick={(e) => {
                e.stopPropagation();
                hide();
                const box = e.currentTarget.ownerSVGElement?.getBoundingClientRect();
                if (box) setLink({ parent: one.parent, child: one.child, x: e.clientX - box.left, y: e.clientY - box.top });
              }}
            >
              <path className="overview-link-hit" d={one.d} />
              <path className="overview-link" d={one.d} />
            </g>
          ))}
          {wire && <path className={`overview-wire ${wire.target ? "ready" : ""}`} d={wire.d} />}
        </svg>
        {link && (
          <div className="overview-link-menu" style={{ left: link.x, top: link.y }} onClick={(e) => e.stopPropagation()}>
            <span className="hint">
              {T.overview.linkOf(
                byId.get(link.parent)?.event.name ?? `#${link.parent}`,
                byId.get(link.child)?.event.name ?? `#${link.child}`,
              )}
            </span>
            <button
              type="button"
              className="danger"
              onClick={() => {
                setLink(null);
                stageEvent(link.child, { parent: null });
              }}
            >
              {T.overview.unlink}
            </button>
            <button type="button" className="ghost" title={T.close} onClick={() => setLink(null)}>
              ×
            </button>
          </div>
        )}
        {placed.map(({ event, y, height, lane }) => {
          const preview = dragPreview("event", event.id, event);
          const dragging = drag?.kind === "event" && drag.id === event.id;
          return (
            <div
              key={event.id}
              data-id={event.id}
              className={[
                "timeline-item",
                event.end ? "" : "point",
                selected?.id === event.id ? "selected" : "",
                dragging ? "dragging" : "",
                drag?.over === event.id ? "drop-target" : "",
                pending.events.has(event.id) ? "changed" : "",
                applying && pending.events.has(event.id) ? "saving" : "",
              ].join(" ")}
              style={{
                left: left(lane),
                top: (preview?.y ?? y) + EVENT_MARGIN,
                width: EVENT_LANE_WIDTH - 2 * EVENT_LANE_PAD,
                height: (preview?.height ?? height) - 2 * EVENT_MARGIN,
              }}
              onPointerDown={(e) => onItemDown(e, "event", event.id)}
              onPointerMove={onItemMove}
              onPointerUp={onItemUp}
              onPointerCancel={() => setDrag(null)}
              // 下の列へ届くと、出来事を足すモーダルが出てしまう
              onClick={(e) => e.stopPropagation()}
              onMouseMove={(e) =>
                !drag && show(e, parentIds.has(event.id) ? [T.overview.arc, ...eventLines(event)] : eventLines(event))
              }
              onMouseLeave={hide}
            >
              {edges}
              {ports}
              <span className="timeline-text">
                {event.name}
                {preview && <span className="timeline-target"> → {T.span(preview.range.start, preview.range.end) || preview.range.start}</span>}
                {dragging && drag.over !== null && (
                  <span className="timeline-target">
                    {" "}
                    →{" "}
                    {(drag.mode === "out" ? T.overview.parentOf : T.overview.childOf)(
                      byId.get(drag.over)?.event.name ?? `#${drag.over}`,
                    )}
                  </span>
                )}
              </span>
            </div>
          );
        })}
      </div>
    );
  };

  const columns = [
    "var(--timeline-axis)",
    `${episodePack.lanes * EPISODE_LANE_WIDTH}px`,
    `${eventPack.lanes * EVENT_LANE_WIDTH}px`,
  ];

  /** 押した出来事のモーダル。ほかのモーダル(話・出来事のタイムライン)と同じく、時刻などを一行ずつ出し、名前と本文を直せる */
  const renderEvent = (event: OverviewEvent) => (
    <Modal
      title={T.nameId(eventForm?.name ?? event.name, event.id)}
      onClose={closeEvent}
      actions={
        <>
          <button type="button" className="danger" disabled={savingEvent} onClick={() => void removeEvent(event)}>
            {T.eventTimeline.delete}
          </button>
          <span className="spacer" />
          <button type="button" onClick={closeEvent}>
            {T.close}
          </button>
          <button type="button" onClick={(e) => leaveTo(`/tables/event/${event.id}`, e)}>
            {T.openRecord}
          </button>
          <button type="button" className="primary" disabled={!canSaveEvent} onClick={() => void saveEvent()}>
            {T.record.save}
          </button>
        </>
      }
    >
      <div className="timeline-sheet">
        {[
          T.span(event.start, event.end) || event.start,
          event.parent_event_id !== null &&
            T.eventTimeline.parent(
              T.nameId(shown?.events.find((one) => one.id === event.parent_event_id)?.name, event.parent_event_id),
            ),
          event.location_name,
          T.eventTimeline.importanceLine(event.importance),
          event.character_ids.length > 0 &&
            `${T.overview.participants}: ${event.character_ids.map((id) => names.get(id)).join(", ")}`,
          event.hidden && T.overview.hidden,
        ]
          .filter(Boolean)
          .join("\n")}
      </div>
      {eventError && <div className="status error">{eventError}</div>}
      {eventForm && (
        <>
          <ImportanceField
            value={eventForm.importance}
            onChange={(importance) => setEventForm({ ...eventForm, importance })}
            disabled={savingEvent}
          />
          <div className="field">
            <label>{T.eventTimeline.name}</label>
            <input
              type="text"
              value={eventForm.name}
              onChange={(e) => setEventForm({ ...eventForm, name: e.target.value })}
              disabled={savingEvent}
            />
          </div>
          <div className="field">
            <label>{T.eventTimeline.text}</label>
            <OpenableText
              title={T.eventTimeline.text}
              value={eventForm.text}
              onChange={(text) => setEventForm({ ...eventForm, text })}
              onSave={canSaveEvent ? () => void saveEvent() : undefined}
            >
              <textarea
                value={eventForm.text}
                onChange={(e) => setEventForm({ ...eventForm, text: e.target.value })}
                disabled={savingEvent}
              />
            </OpenableText>
          </div>
        </>
      )}
    </Modal>
  );

  /** 左の枠。足す・直す話の欄と、その期間の出来事を出す。話を開いていなければ出さない */
  const renderPanel = () => {
    if (!episodePanel) return null;
    return (
      <aside className="overview-panel">
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
          <EpisodeFields
            value={episodePanel.draft}
            onChange={(next) => setEpisodePanel((p) => (p ? { ...p, draft: next } : p))}
            disabled={savingEpisode}
            onSave={canSave ? () => void saveEpisode() : undefined}
          />
          <div className="overview-panel-actions">
            <button
              type="button"
              disabled={savingEpisode}
              onClick={(e) =>
                episodePanel.id === null
                  ? leaveTo(newEpisodeUrl({ story_id: storyId }, episodePanel.draft), e)
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
        {period && (
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
                        // モーダルが上に被さり、ボタンから外れたことにならないので、吹き出しはここで消す
                        hide();
                        openEvent(event);
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

  const content = (
    <div className="page-fill timeline-page overview-page">
      <PageTitle kind={T.overview.title} record={data?.story_name ?? null} />
      <div className="toolbar">
        <h1 style={{ margin: 0 }}>{T.overview.title}</h1>
        <PageHelp page={T.overview.title} help={T.help.overview} />
        <div className="hint timeline-filter">
          {T.overview.story}
          <ReferenceSelect
            table="story"
            value={storyId}
            nullable
            onChange={(value) => {
              if (!closeEpisode() || !closeEvent() || !discardPending()) return;
              setMessage(null);
              navigate({ story_id: value });
            }}
            title={T.overview.story}
          />
        </div>
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
      </div>
      {data && (
        <div className="status info overview-status">
          {T.overview.period(data.since, data.until)} · {T.overview.counts(events.length)} ·{" "}
          {T.overview.legend}
        </div>
      )}
      {error && <div className="status error">{error}</div>}
      {message && !error && <div className="status ok">{message}</div>}
      {storyId === null ? (
        <div className="status info">{T.overview.pickStory}</div>
      ) : !data || !scope ? (
        !error && <div className="status info">{T.loading}</div>
      ) : (
        <div className="overview-split">
        {renderPanel()}
        <div
          className="timeline overview"
          style={{ "--timeline-head": `${box.head}px` } as CSSProperties}
        >
          <div className="timeline-scroll" ref={scrollBoxRef} onScroll={onScroll}>
            <div className="timeline-head" style={{ gridTemplateColumns: columns.join(" ") }}>
              <div className="timeline-corner" />
              <div className="timeline-label">{T.overview.episodes}</div>
              <div className="timeline-label">{T.overview.events}</div>
            </div>
            <div className="timeline-body">
              <div className="timeline-lines">
                {scale?.gaps.map((g) => (
                  <div key={g.from} className="timeline-gap" style={{ top: g.y, height: GAP_PX }} />
                ))}
                {ticks.map((tick) => (
                  <div key={tick.at} className={`timeline-grid ${tick.major ? "major" : ""}`} style={{ top: scale?.toY(tick.at) }} />
                ))}
                {/* 左の枠で書いている話の期間を、人物の列まで横切る帯で示す */}
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
                    {T.timeline.skipped(g.to - g.from, ...skipUnits(calendar))}
                  </div>
                ))}
                {ticks.map((tick) => (
                  <div key={tick.at} className={`timeline-tick ${tick.major ? "major" : ""}`} style={{ top: scale?.toY(tick.at) }}>
                    {tick.label}
                  </div>
                ))}
              </div>
              <div className="timeline-col">{renderEpisodes()}</div>
              <div className="timeline-col">{renderEvents()}</div>
            </div>
          </div>
        </div>
        </div>
      )}
      {viewingNow && (
        <Modal
          title={T.nameId(edit?.title ?? viewingNow.title, viewingNow.id)}
          onClose={closeViewing}
          actions={
            <>
              <span className="spacer" />
              <button type="button" onClick={closeViewing}>
                {T.close}
              </button>
              <button type="button" onClick={(e) => leaveTo(`/tables/episode/${viewingNow.id}`, e)}>
                {T.openRecord}
              </button>
              <button type="button" className="primary" disabled={!canSaveEdit} onClick={() => void saveEdit()}>
                {T.record.save}
              </button>
            </>
          }
        >
          <div className="timeline-sheet">{detailLines(viewingNow).filter(Boolean).join("\n")}</div>
          {editError && <div className="status error">{editError}</div>}
          {edit ? (
            <EpisodeFields
              value={edit}
              onChange={setEdit}
              disabled={savingEdit}
              onSave={canSaveEdit ? () => void saveEdit() : undefined}
            />
          ) : (
            !editError && <div className="status info">{T.loading}</div>
          )}
        </Modal>
      )}
      {/* 溜めた変更があるあいだだけ、画面の下の真ん中に浮かべる。表の並びを押し下げず、スクロールしても見えたままにする */}
      {pendingCount > 0 && (
        <div className="overview-pending" role="status">
          <span>{T.overview.pending(pendingCount)}</span>
          <button type="button" disabled={applying} onClick={discardPending}>
            {T.overview.discard}
          </button>
          <button type="button" className="primary" disabled={applying} onClick={() => void applyPending()}>
            {T.overview.save(pendingCount)}
          </button>
        </div>
      )}
      {selected && renderEvent(selected)}
      {addingEvent && (
        <NewEventModal
          start={addingEvent.start}
          parent={null}
          location={null}
          characters={[]}
          onClose={() => setAddingEvent(null)}
          onAdded={() => {
            if (storyId === null) return;
            // 軸は画面の高さまで伸びるので、章の期間の外も押せる。外に足した出来事は読み直しても出ないので、そう知らせる
            const day = dayOf(addingEvent.start, calendar) ?? 0;
            const outside =
              day < (dayOf(data?.since, calendar) ?? -Infinity) || day > (dayOf(data?.until, calendar) ?? Infinity);
            setMessage(outside && data ? T.overview.addedEventOutside(data.since, data.until) : T.overview.addedEvent);
            reread()
              .then(setData)
              .catch((e) => setError(e instanceof Error ? e.message : String(e)));
          }}
          onOpenPage={leaveTo}
        />
      )}
      <Tooltip tip={tip} />
    </div>
  );
  // 時刻の欄(左の枠・話のモーダル・出来事を足すモーダル)も、軸と同じ暦で数える
  return <CalendarProvider calendar={calendar}>{content}</CalendarProvider>;
}
