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
import Modal from "@/components/Modal";
import NewEventModal from "@/components/NewEventModal";
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
  type Rec,
} from "@/lib/api";
import { PageTitle } from "@/lib/meta";
import { inNewTab, openInNewTab, useOpenPage, type OpenModifiers } from "@/lib/openPage";
import { trackSaving, useSaveShortcut } from "@/lib/saving";
import { fromDayNumber, formatStamp, shiftDays } from "@/lib/stamp";
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
  roundHours,
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
// 企ての帯を置く幅。列の左の空きと、押して出来事を足せるよう列の右に残す余白(px)
const ARC_LEFT = 4;
const ARC_RIGHT_SPACE = 16;
// 章の話の列の key。兄弟の作品の列は `story-<作品の id>`
const CHAPTER_KEY = "chapter";

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
type Packed = { placed: Placed[]; lanes: number };
// 話の列。章の列(storyId は選んだ作品)と、兄弟の作品ごとの列
type EpisodeColumn = { key: string; storyId: number; label: string; packed: Packed; faint: boolean };
// from は掴んだ列、over は落とす先の作品(掴んだ列の上・作品の無い列の上では null)
type Drag = { episode: OverviewEpisode; from: string; startX: number; startY: number; dx: number; dy: number; over: number | null };
// 変更モードで溜めた移し。base は読み込んだときの話で、days はそこから何日ずらすか、story は移す先の作品(移さないなら null)
type Change = { base: OverviewEpisode; days: number; story: number | null };

/** 話の札を、重ならないよう筋に振り分ける(話のタイムラインと同じく、上から空いた筋に入れる) */
function pack(episodes: OverviewEpisode[], scale: Scale): Packed {
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

/** 日付をずらしたときの開始・終了。開始・終了を同じ日数だけ動かす */
const shifted = (episode: OverviewEpisode, days: number) => ({
  start: shiftDays(episode.start, days) ?? episode.start,
  end: episode.end === null ? null : shiftDays(episode.end, days),
});

/** 保存する欄。動かした分だけを渡す */
function changeForm({ base, days, story }: Change): Rec {
  return { id: base.id, ...(days !== 0 ? shifted(base, days) : {}), ...(story !== null ? { story_id: story } : {}) };
}

const columnKeyOf = (episode: OverviewEpisode) => (episode.in_story ? CHAPTER_KEY : `story-${episode.story_id}`);

const radius = (event: OverviewEvent) => Math.min(DOT_MAX, DOT_BASE + (event.size.total - 1) * DOT_STEP);

// 企ての帯の置き場所。slot は列の中で何本目にずらすか、slots はその列でずらす本数
type ArcSlot = { owner: number; start: number; end: number; slot: number; slots: number };

/** 企ての帯を、動いた人物の列ごとに時刻の順で並べ、期間の重なる帯は別の slot に置く(重ならなければ同じ slot に戻す) */
function arcSlotsOf(arcs: { id: number; owner: number; start: number; end: number }[]): Map<number, ArcSlot> {
  const slots = new Map<number, ArcSlot>();
  const byOwner = new Map<number, typeof arcs>();
  for (const arc of arcs) byOwner.set(arc.owner, [...(byOwner.get(arc.owner) ?? []), arc]);
  for (const list of byOwner.values()) {
    const ends: number[] = [];
    const placed = [...list]
      .sort((a, b) => a.start - b.start || a.id - b.id)
      .map((arc) => {
        let slot = ends.findIndex((end) => end <= arc.start);
        if (slot < 0) slot = ends.length;
        ends[slot] = arc.end;
        return { arc, slot };
      });
    for (const { arc, slot } of placed)
      slots.set(arc.id, { owner: arc.owner, start: arc.start, end: arc.end, slot, slots: ends.length });
  }
  return slots;
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
  // 変更モード。札を動かしても保存せず、話の id ごとに移しを溜めて、適用でまとめて保存する(話のタイムラインと同じ)
  const [editing, setEditing] = useState(false);
  const [changes, setChanges] = useState<Map<number, Change>>(new Map());
  const [applying, setApplying] = useState(false);
  const [drag, setDrag] = useState<Drag | null>(null);
  // 押した話のモーダルと、書きかけの時刻・タイトル・プロット
  const [viewing, setViewing] = useState<Viewing | null>(null);
  const [edit, setEdit] = useState<EpisodeDraft | null>(null);
  const [savingEdit, setSavingEdit] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  // 人物の列の空いた所を押して足す出来事の、押した時刻と人物
  const [addingEvent, setAddingEvent] = useState<{ start: string; character: OverviewCharacter } | null>(null);
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

  const reread = () => getOverview({ story_id: storyId!, margin_days: margin });

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

  // 作品の名前。兄弟の作品の列の見出しと、移しの前後に出す
  const storyNames = useMemo(() => {
    const map = new Map<number, string>();
    if (data) map.set(data.story_id, data.story_name ?? T.nameId(null, data.story_id));
    for (const episode of data?.episodes ?? [])
      if (!map.has(episode.story_id)) map.set(episode.story_id, episode.story_name ?? T.nameId(null, episode.story_id));
    return map;
  }, [data]);
  const storyLabel = (id: number) => storyNames.get(id) ?? T.nameId(null, id);

  // 溜めた移しを当てた話。札はこの時刻・作品の所に描く
  const episodes = useMemo(
    () =>
      (data?.episodes ?? []).map((episode) => {
        const change = changes.get(episode.id);
        if (!change) return episode;
        const moved = { ...episode, ...shifted(change.base, change.days) };
        if (change.story === null) return moved;
        return {
          ...moved,
          story_id: change.story,
          story_name: storyNames.get(change.story) ?? null,
          in_story: change.story === data?.story_id,
        };
      }),
    [data, changes, storyNames],
  );

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
    for (const item of [...episodes, ...events]) {
      const start = dayOf(item.start);
      if (start !== null) all.push(timeSpan(start, dayOf(item.end)));
    }
    return all;
  }, [episodes, events]);
  const scale = useMemo(() => scaleOf(spans, null, view, box.viewport), [spans, view, box.viewport]);
  const ticks = useMemo(
    () => (scale ? axisTicksOf(scale, spans, view.squeeze, screen, box.viewport) : []),
    [scale, spans, view.squeeze, screen, box.viewport],
  );
  // 章の列と、兄弟の作品ごとの列。兄弟の列は、読み込んだ話を移したあとも、話を運び戻せるよう残す
  const episodeColumns = useMemo((): EpisodeColumn[] => {
    if (!scale || !data) return [];
    const byTime = (list: OverviewEpisode[]) =>
      [...list].sort((a, b) => (dayOf(a.start) ?? 0) - (dayOf(b.start) ?? 0) || a.id - b.id);
    const siblingIds = [
      ...new Set([...data.episodes, ...episodes].filter((episode) => !episode.in_story).map((episode) => episode.story_id)),
    ];
    return [
      {
        key: CHAPTER_KEY,
        storyId: data.story_id,
        label: data.story_name ?? T.overview.episodes,
        packed: pack(byTime(episodes.filter((episode) => episode.in_story)), scale),
        faint: false,
      },
      ...siblingIds.map((id) => ({
        key: `story-${id}`,
        storyId: id,
        label: storyNames.get(id) ?? T.nameId(null, id),
        packed: pack(byTime(episodes.filter((episode) => !episode.in_story && episode.story_id === id)), scale),
        faint: true,
      })),
    ];
  }, [scale, data, episodes, storyNames]);

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

  // 押した話は、移しを溜めたら移したあとの時刻を出す
  const viewingNow = viewing ? (episodes.find((episode) => episode.id === viewing.episode.id) ?? viewing.episode) : null;
  const loaded = viewing?.loaded ?? null;
  const editTimeChanged = !!edit && !!viewingNow && (edit.start !== viewingNow.start || edit.end !== viewingNow.end);
  const editTitleChanged = !!edit && !!loaded && edit.title !== loaded.title;
  const editPlotChanged = !!edit && !!loaded && edit.plot !== loaded.plot;
  const editDirty = editTimeChanged || editTitleChanged || editPlotChanged;
  const canSaveEdit = editDirty && !savingEdit && !!edit?.start;

  useEffect(() => {
    if (!dirty && !editDirty && changes.size === 0) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty, editDirty, changes.size]);

  /** 左の枠の話を閉じる。書きかけがあれば捨ててよいかを尋ね、捨てないなら false */
  const closeEpisode = () => {
    if (dirty && !window.confirm(T.overview.confirmDiscardEpisode)) return false;
    setEpisodePanel(null);
    setPanelError(null);
    return true;
  };

  /** 溜めた移しを捨ててよいかを尋ね、捨てるなら変更モードを出る。捨てないなら false */
  const discardChanges = () => {
    if (changes.size > 0 && !window.confirm(T.timeline.confirmDiscard(changes.size))) return false;
    leaveEditing();
    return true;
  };

  const leaveEditing = () => {
    setChanges(new Map());
    setEditing(false);
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
        // 時刻は、移しを溜めた話なら移したあとの時刻から書き始める
        setEdit({ start: episode.start, end: episode.end, title: record.title ?? "", plot: record.plot });
      })
      .catch((e) => setEditError(e instanceof Error ? e.message : String(e)));
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
    const day = snapDay(scale.fromY(e.clientY - e.currentTarget.getBoundingClientRect().top), scale.pxPerDay);
    setEpisodePanel({
      id: null,
      label: T.timeline.newEpisode,
      saved: null,
      draft: { start: formatStamp(fromDayNumber(day)), end: null, title: "", plot: "" },
    });
  };

  /** 人物の列の空いた所を押したら、その時刻・その人物を当事者にした出来事を足すモーダルを出す(出来事のタイムラインと同じ) */
  const onPeopleClick = (e: MouseEvent<HTMLDivElement>) => {
    if (!scale) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const character = characters[Math.floor((e.clientX - rect.left) / CHARACTER_WIDTH)];
    if (!character) return;
    hide();
    setMessage(null);
    const day = snapDay(scale.fromY(e.clientY - rect.top), scale.pxPerDay);
    setAddingEvent({ start: formatStamp(fromDayNumber(day)), character });
  };

  /** 別のページへ移る(Ctrl(⌘)を押しながらなら別タブで開き、書きかけ・溜めた移しは残る) */
  const leaveTo = (url: string, e?: OpenModifiers) => {
    if (!inNewTab(e)) {
      if ((dirty || editDirty) && !window.confirm(T.overview.confirmDiscardEpisode)) return;
      if (changes.size > 0 && !window.confirm(T.timeline.confirmDiscard(changes.size))) return;
    }
    openPage(url, e);
  };

  /** 書き終えたあと、読み直した話で溜めた移しの元を替える。時刻を書いた話は、溜めた時刻の移しを書いた時刻に含めたので外す */
  const rebase = (fresh: OverviewResponse, id: number, wroteTime: boolean) =>
    setChanges((previous) => {
      const change = previous.get(id);
      const base = fresh.episodes.find((episode) => episode.id === id);
      if (!change || !base) return previous;
      const next = new Map(previous);
      const days = wroteTime ? 0 : change.days;
      if (days === 0 && change.story === null) next.delete(id);
      else next.set(id, { ...change, base, days });
      return next;
    });

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
        rebase(fresh, id, timeChanged);
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
        updateEpisodes([
          {
            id,
            ...(editTitleChanged ? { title: sent.title } : {}),
            ...(editPlotChanged ? { plot_text: sent.plot } : {}),
            ...(editTimeChanged ? { start: sent.start, end: sent.end } : {}),
          },
        ]).then(reread),
      );
      if (editTitleChanged) invalidateOptions("episode");
      setData(fresh);
      rebase(fresh, id, editTimeChanged);
      const shown = fresh.episodes.find((episode) => episode.id === id);
      setViewing((v) =>
        v?.episode.id === id
          ? { episode: shown ?? v.episode, loaded: { title: sent.title ?? "", plot: sent.plot } }
          : v,
      );
      setMessage(T.timeline.saved(T.nameId(sent.title, id)));
    } catch (e) {
      setEditError(e instanceof Error ? e.message : String(e));
    } finally {
      setSavingEdit(false);
    }
  };

  /** 溜めた移しをまとめて保存する */
  const apply = async () => {
    if (storyId === null || changes.size === 0) return;
    setApplying(true);
    setError(null);
    setMessage(null);
    try {
      const fresh = await trackSaving(updateEpisodes([...changes.values()].map(changeForm)).then(reread));
      // 読み直した話と溜めた分を外すのを同じ描画で替え、札が元の所へ一度戻って見えないようにする
      setData(fresh);
      setMessage(T.timeline.applied(changes.size));
      leaveEditing();
    } catch (e) {
      setError(T.timeline.applyFailed(e instanceof Error ? e.message : String(e)));
    } finally {
      setApplying(false);
    }
  };

  // 話のモーダルを開いていればその話を、左の枠に書きかけがあればその話を、どちらも無ければ溜めた移しを保存する
  useSaveShortcut(() => {
    if (viewingNow) {
      if (canSaveEdit) void saveEdit();
    } else if (canSave) void saveEpisode();
    else if (changes.size > 0 && !applying) void apply();
  });

  /** 縦に dy px 動かしたら何日ずれるか(話のタイムラインと同じ刻みに丸める)。詰めた帯の上では一気に日が進む */
  const daysAt = (episode: OverviewEpisode, dy: number) => {
    if (!scale || scale.pxPerDay === 0) return 0;
    const start = dayOf(episode.start) ?? 0;
    const steps = dragSteps(view);
    return Math.round((scale.fromY(scale.toY(start) + dy) - start) * steps) / steps;
  };
  const dragDays = (episode: OverviewEpisode) =>
    drag?.episode.id === episode.id && Math.abs(drag.dy) > DRAG_THRESHOLD ? daysAt(episode, drag.dy) : 0;

  /** 移しを溜める。同じ話を何度動かしても、読み込んだときの話からの移しにまとめる。元に戻ったら溜めた分から外す */
  const move = (episode: OverviewEpisode, days: number, story: number | null) => {
    const next = new Map(changes);
    const previous = changes.get(episode.id);
    const base = previous?.base ?? data?.episodes.find((e) => e.id === episode.id) ?? episode;
    const target = story ?? previous?.story ?? null;
    // 章の列は章の子の作品の話も並べるので、章の話を章の列へ戻したら元の作品のまま
    const back = target === base.story_id || (target === storyId && base.in_story);
    const change = { base, days: roundHours((previous?.days ?? 0) + days), story: back ? null : target };
    if (change.days === 0 && change.story === null) next.delete(episode.id);
    else next.set(episode.id, change);
    setChanges(next);
  };

  /** 指の下の話の列の作品。札は掴んだ列に留まるので、掴んだ札ではなく位置から列を探す */
  const storyUnder = (x: number, y: number, from: string): number | null => {
    const col = document
      .elementsFromPoint(x, y)
      .map((el) => el.closest<HTMLElement>(".timeline-col[data-story]"))
      .find(Boolean);
    const story = Number(col?.dataset.story);
    if (!col || col.dataset.key === from || !story) return null;
    return story;
  };

  const onItemDown = (e: PointerEvent<HTMLDivElement>, episode: OverviewEpisode) => {
    if (e.button !== 0 || applying) return;
    e.stopPropagation();
    e.currentTarget.setPointerCapture(e.pointerId);
    hide();
    setDrag({ episode, from: columnKeyOf(episode), startX: e.clientX, startY: e.clientY, dx: 0, dy: 0, over: null });
  };

  const onItemMove = (e: PointerEvent<HTMLDivElement>) => {
    if (drag && editing)
      setDrag({
        ...drag,
        dx: e.clientX - drag.startX,
        dy: e.clientY - drag.startY,
        over: storyUnder(e.clientX, e.clientY, drag.from),
      });
  };

  const onItemUp = (e: PointerEvent<HTMLDivElement>) => {
    if (!drag) return;
    const { episode, over } = drag;
    const dx = e.clientX - drag.startX;
    const dy = e.clientY - drag.startY;
    setDrag(null);
    if (Math.abs(dx) <= DRAG_THRESHOLD && Math.abs(dy) <= DRAG_THRESHOLD) {
      // Ctrl(⌘)を押しながらなら、話のページを別タブで開く
      if (inNewTab(e)) openInNewTab(`/tables/episode/${episode.id}`);
      else openViewing(episode);
      return;
    }
    // 変更モードの外では札を動かさない
    if (!editing) return;
    // 列を移すときの手ぶれで時刻が動かないよう、縦にしきい値を超えて動かしたときだけ時刻を送る
    const days = Math.abs(dy) > DRAG_THRESHOLD ? daysAt(episode, dy) : 0;
    if (days !== 0 || over !== null) move(episode, days, over);
  };

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
  /** 吹き出しと押したときのモーダルに出す、時刻・作品と、移しを溜めた話は移す前の行 */
  const detailLines = (episode: OverviewEpisode) => {
    const base = changes.get(episode.id)?.base;
    return [
      T.span(episode.start, episode.end) || episode.start,
      storyLabel(episode.story_id),
      base && T.timeline.was(T.span(base.start, base.end) || base.start, storyLabel(base.story_id)),
    ];
  };

  const renderEpisodes = (col: EpisodeColumn) => (
    <div
      key={col.key}
      className={`timeline-col ${drag?.over === col.storyId ? "drop-target" : ""}`}
      data-key={col.key}
      data-story={col.storyId}
    >
      {/* 足す話は選んだ作品に入れるので、空いた所を押して足せるのは章の列だけ */}
      <div
        className={`timeline-track ${col.faint ? "overview-readonly" : ""}`}
        style={{ width: col.packed.lanes * EPISODE_LANE_WIDTH, height: scale?.height }}
        onClick={col.faint ? undefined : onTrackClick}
      >
        {col.packed.placed.map(({ episode, y, height, lane }) => {
          const days = dragDays(episode);
          const dragging = drag?.episode.id === episode.id;
          const target = days !== 0 && shifted(episode, days);
          const offset = days && scale ? scale.toY((dayOf(episode.start) ?? 0) + days) - y : 0;
          const className = [
            "timeline-item",
            episode.end ? "" : "point",
            col.faint ? "overview-faint" : "",
            viewing?.episode.id === episode.id || episodePanel?.id === episode.id ? "selected" : "",
            dragging ? "dragging" : "",
            changes.has(episode.id) ? "changed" : "",
            applying && changes.has(episode.id) ? "saving" : "",
          ].join(" ");
          return (
            <div
              key={episode.id}
              className={className}
              style={{
                left: lane * EPISODE_LANE_WIDTH + 2,
                top: y,
                width: EPISODE_LANE_WIDTH - 4,
                transform: offset ? `translateY(${offset}px)` : undefined,
                ...(dragging ? { minHeight: height } : { height }),
              }}
              onPointerDown={(e) => onItemDown(e, episode)}
              onPointerMove={onItemMove}
              onPointerUp={onItemUp}
              onPointerCancel={() => setDrag(null)}
              onClick={(e) => e.stopPropagation()}
              onMouseMove={(e) => !drag && show(e, [episode.title ?? `#${episode.id}`, ...detailLines(episode)])}
              onMouseLeave={hide}
            >
              <span className="timeline-text">
                {episode.title ?? `#${episode.id}`}
                {target && <span className="timeline-target"> → {target.start}</span>}
                {dragging && drag.over !== null && (
                  <span className="timeline-target"> → {storyLabel(drag.over)}</span>
                )}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );

  const x = (characterId: number) => (column.get(characterId) ?? 0) * CHARACTER_WIDTH + CHARACTER_WIDTH / 2;

  const arcSlots = useMemo(() => {
    const arcs = [];
    for (const event of events) {
      if (!parentIds.has(event.id)) continue;
      const owner = event.actor_id ?? event.character_ids.find((id) => column.has(id));
      const start = dayOf(event.start);
      if (owner == null || !column.has(owner) || start === null) continue;
      arcs.push({ id: event.id, owner, start, end: dayOf(event.end) ?? Infinity });
    }
    return arcSlotsOf(arcs);
  }, [events, parentIds, column]);

  const renderEvents = () => {
    if (!scale) return null;
    const width = characters.length * CHARACTER_WIDTH;
    const dimmed = (event: OverviewEvent) => focus !== null && !event.character_ids.includes(focus);
    // 出来事を押したら詳細を出す。下の人物の列へ届くと、出来事を足すモーダルが出てしまう
    const pick = (e: MouseEvent, event: OverviewEvent) => {
      e.stopPropagation();
      setSelected(event);
    };
    return (
      <div className="overview-people" style={{ width, height: scale.height }} onClick={onPeopleClick}>
        {characters.map((character) => (
          <div
            key={character.id}
            className={`overview-lane ${focus === character.id ? "focused" : ""}`}
            style={{ left: (column.get(character.id) ?? 0) * CHARACTER_WIDTH, width: CHARACTER_WIDTH }}
          />
        ))}
        <svg className="overview-svg" width={width} height={scale.height}>
          {/* 企て(子を持つ出来事)は、動いた人物の列に始まりから終わりまでの帯で描く。期間の重なる帯は、幅の半分ずつずらして重ねる */}
          {events
            .filter((event) => arcSlots.has(event.id))
            .map((event) => {
              const { owner, start, end, slot, slots } = arcSlots.get(event.id)!;
              const top = scale.toY(start);
              const bottom = end === Infinity ? scale.height : scale.toY(end);
              // slots 本を半分ずつ重ねて、列の左から右の余白の手前までに収める
              const width = (2 * (CHARACTER_WIDTH - ARC_LEFT - ARC_RIGHT_SPACE)) / (slots + 1);
              return (
                <rect
                  key={`arc-${event.id}`}
                  className={`overview-arc ${dimmed(event) ? "dimmed" : ""}`}
                  x={x(owner) - CHARACTER_WIDTH / 2 + ARC_LEFT + (slot * width) / 2}
                  y={top}
                  width={width}
                  height={Math.max(4, bottom - top)}
                  rx={4}
                  onMouseMove={(e) => show(e, [T.overview.arc, ...eventLines(event)])}
                  onMouseLeave={hide}
                  onClick={(e) => pick(e, event)}
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
                onClick={(e) => pick(e, event)}
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
    ...episodeColumns.map((col) => `${col.packed.lanes * EPISODE_LANE_WIDTH}px`),
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

  /** 左の枠。足す話の欄と、その期間の出来事(押した出来事があればその詳細)を出す。どちらも無ければ出さない */
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
              if (!discardChanges() || !closeEpisode()) return;
              setSelected(null);
              setMessage(null);
              navigate({ story_id: value });
            }}
            title={T.overview.story}
          />
        </div>
        <label className="hint timeline-filter">
          {T.overview.margin}
          <select
            value={margin}
            onChange={(e) => discardChanges() && navigate({ margin: Number(e.target.value) })}
          >
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
        {editing ? (
          <>
            <button type="button" className="primary" disabled={changes.size === 0 || applying} onClick={() => void apply()}>
              {T.timeline.apply(changes.size)}
            </button>
            <button type="button" disabled={applying} onClick={discardChanges}>
              {T.timeline.discard}
            </button>
          </>
        ) : (
          <button type="button" disabled={!data} onClick={() => setEditing(true)}>
            {T.timeline.edit}
          </button>
        )}
      </div>
      {data && (
        <div className="status info overview-status">
          {T.overview.period(data.since, data.until)} · {T.overview.legend}
        </div>
      )}
      {editing && <div className="status info">{T.timeline.editHint}</div>}
      {error && <div className="status error">{error}</div>}
      {message && !error && <div className="status ok">{message}</div>}
      {storyId === null ? (
        <div className="status info">{T.overview.pickStory}</div>
      ) : !data ? (
        !error && <div className="status info">{T.loading}</div>
      ) : (
        <div className="overview-split">
        {renderPanel()}
        <div
          className={`timeline overview ${editing ? "editing" : ""}`}
          aria-busy={applying}
          style={{ "--timeline-head": `${box.head}px` } as CSSProperties}
        >
          <div className="timeline-scroll" ref={scrollBoxRef} onScroll={onScroll}>
            <div className="timeline-head overview-head" style={{ gridTemplateColumns: columns.join(" ") }}>
              <div className="timeline-corner" />
              {episodeColumns.map((col) => (
                <div
                  key={col.key}
                  className={`timeline-label ${drag?.over === col.storyId ? "drop-target" : ""}`}
                  title={col.faint ? `${T.overview.siblings}: ${col.label}` : col.label}
                >
                  {col.label}
                </div>
              ))}
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
                    {T.timeline.skipped(g.to - g.from)}
                  </div>
                ))}
                {ticks.map((tick) => (
                  <div key={tick.at} className={`timeline-tick ${tick.major ? "major" : ""}`} style={{ top: scale?.toY(tick.at) }}>
                    {tick.label}
                  </div>
                ))}
              </div>
              {episodeColumns.map(renderEpisodes)}
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
      {addingEvent && (
        <NewEventModal
          start={addingEvent.start}
          parent={null}
          location={null}
          characters={[{ id: addingEvent.character.id, label: names.get(addingEvent.character.id) ?? `#${addingEvent.character.id}` }]}
          onClose={() => setAddingEvent(null)}
          onAdded={() => {
            if (storyId === null) return;
            // 軸は画面の高さまで伸びるので、章の期間の外も押せる。外に足した出来事は読み直しても出ないので、そう知らせる
            const day = dayOf(addingEvent.start) ?? 0;
            const outside = day < (dayOf(data?.since) ?? -Infinity) || day > (dayOf(data?.until) ?? Infinity);
            setMessage(outside && data ? T.overview.addedEventOutside(data.since, data.until) : T.overview.addedEvent);
            reread()
              .then(setData)
              .catch((e) => setError(e instanceof Error ? e.message : String(e)));
          }}
          onOpenPage={leaveTo}
        />
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
