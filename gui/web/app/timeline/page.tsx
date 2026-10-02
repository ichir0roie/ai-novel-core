"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type MouseEvent, type PointerEvent } from "react";
import RecordModal from "@/components/RecordModal";
import ReferenceSelect, { useOptions } from "@/components/ReferenceSelect";
import StampInput from "@/components/StampInput";
import Tooltip, { useTooltip } from "@/components/Tooltip";
import TreeReferenceSelect from "@/components/TreeReferenceSelect";
import { getTimeline, labelOf, updateRecord, type Labels, type Rec, type TimelineResponse } from "@/lib/api";
import { PageTitle } from "@/lib/meta";
import { dayNumber, formatStamp, fromDayNumber, pad2, parseStamp, shiftDays } from "@/lib/stamp";
import { T } from "@/lib/text";

// 画面の幅に見せる期間(日数)。全期間はこの縮尺で横に並べ、スクロールで見て回る
const SPANS = [3, 7, 31, 92, 365, 3650, 36500];
const DEFAULT_SPAN = 31;
const LANE_HEIGHT = 26;
const ITEM_GAP = 6;
// 目盛りどうしの最小の間隔(px)。これより詰まる刻みは使わない
const MIN_TICK_PX = 64;
// スクロールが止まってから中心の時刻を URL に書くまでの間(ms)
const SCROLL_SETTLE_MS = 200;
// ドラッグとクリックを分けるしきい値(px)
const DRAG_THRESHOLD = 4;
const ADD_MENU_WIDTH = 190;
const ADD_MENU_HEIGHT = 120;
// 話・出来事の無い区間を詰めた帯の幅(px)。これより広く空く区間だけ詰める
const GAP_PX = 40;
const MIN_GAP_PX = 2 * GAP_PX;
// 札の前後に空けておく余白(px)。札のすぐ脇から帯にならないようにする
const OCCUPY_MARGIN_PX = 24;
// 帯の直前・帯の左端の目盛りは、文字が帯に掛かるので文字を出さない
const TICK_LABEL_PX = 48;
const FULL_STAMP = /^\d+\/\d{2}\/\d{2} \d{2}:\d{2}:\d{2}$/;

type Kind = "episode" | "event";
// 軸は日の単位。start・end は日の境目に丸めた通算日で、at は丸める前の時刻(同じ日の中の並び順に使う)
type Item = { kind: Kind; key: string; id: number; label: string; record: Rec; labels: Labels; at: number; start: number; end: number | null };
type Placed = Item & { x: number; width: number; barWidth: number; lane: number };
type Row = { key: string; label: string; storyId: number | null; items: Placed[]; lanes: number };
type Tick = { at: number; label: string; major: boolean };
type Gap = { from: number; to: number; x: number };
// since〜until が軸の全体で、width はその横幅(px)
type Scale = { since: number; until: number; width: number; pxPerDay: number; gaps: Gap[]; toX: (day: number) => number; fromX: (x: number) => number };

type Drag = { item: Item; startX: number; dx: number };
type AddMenu = { x: number; y: number; at: string; storyId: number | null };
type ModalState = { table: Kind; id?: number; initial?: Rec };

function dayOf(value: unknown): number | null {
  const parts = parseStamp(value);
  return parts ? dayNumber(parts) : null;
}

/** 札の幅。枠と余白に 22px、全角は 14px、半角は 8px ほどで見積もる */
function labelWidth(label: string): number {
  let width = 22;
  for (const c of label) width += c.charCodeAt(0) > 0xff ? 14 : 8;
  return Math.min(240, width);
}

/** 重ならないよう、左から順に空いている一番上の段へ置く。同じ日の札は同じ位置なので、時刻の順に縦へ並ぶ */
function pack(items: Item[], toX: (day: number) => number): { placed: Placed[]; lanes: number } {
  const laneEnds: number[] = [];
  const placed = [...items]
    .sort((a, b) => a.start - b.start || a.at - b.at || a.id - b.id)
    .map((item) => {
      const x = toX(item.start);
      const barWidth = item.end === null ? 0 : Math.max(0, toX(item.end) - x);
      const width = Math.max(barWidth, labelWidth(item.label));
      let lane = laneEnds.findIndex((end) => end <= x);
      if (lane < 0) lane = laneEnds.length;
      laneEnds[lane] = x + width + ITEM_GAP;
      return { ...item, x, width, barWidth, lane };
    });
  return { placed, lanes: Math.max(1, laneEnds.length) };
}

/**
 * 縮尺 `pxPerDay` で札が占めない区間(日の単位)。札は少なくともその日いっぱいを占め、札の幅は px なので縮尺が上がるほど占める日数は減る。
 * 期間の帯は頭(名前の札)と終わりの日だけを占めるとみなす。何年も続く帯が間を全部埋めると、全期間の軸がどこも詰められず長くなりすぎる。
 * `keep` の区間も占めるとみなす(飛ばした先の中心の前後を、札が無くても詰めずに見せる)
 */
function emptiesAt(since: number, until: number, pxPerDay: number, items: Item[], keep: [number, number] | null): { from: number; to: number }[] {
  const margin = OCCUPY_MARGIN_PX / pxPerDay;
  const occupied = items
    .flatMap((item) => {
      const head = Math.max(item.start + 1, item.start + labelWidth(item.label) / pxPerDay);
      return item.end === null || item.end <= head ? [[item.start, Math.max(head, item.end ?? head)]] : [[item.start, head], [item.end - 1, item.end]];
    })
    .concat(keep ? [keep] : [])
    .map(([from, to]) => [Math.max(since, from - margin), Math.min(until, to + margin)])
    .filter(([from, to]) => from < to)
    .sort((a, b) => a[0] - b[0]);
  const empties: { from: number; to: number }[] = [];
  let cursor = since;
  const push = (from: number, to: number) => {
    const [a, b] = [Math.max(since, Math.ceil(from)), Math.min(until, Math.floor(to))];
    if (b - a >= 1) empties.push({ from: a, to: b });
  };
  for (const [from, to] of occupied) {
    if (from > cursor) push(cursor, from);
    cursor = Math.max(cursor, to);
  }
  if (occupied.length > 0 && cursor < until) push(cursor, until);
  return empties;
}

/**
 * 時刻と横の位置の対応。縮尺は `pxPerDay` に決めておき、lo〜hi の中で話・出来事の無い広い区間だけを幅 {@link GAP_PX} の帯に詰める。
 * lo〜hi の外(前後の余白)と `anchor` の前後の画面の半分ずつは詰めない。詰めて画面の幅より短くなったら、後ろへ延ばして画面を埋める。
 */
function compress(since: number, until: number, lo: number, hi: number, anchor: number | null, pxPerDay: number, viewport: number, items: Item[]): Scale {
  const half = viewport / 2 / pxPerDay;
  const empties = emptiesAt(lo, hi, pxPerDay, items, anchor === null ? null : [anchor - half, anchor + half]).filter((g) => (g.to - g.from) * pxPerDay > MIN_GAP_PX);
  const gaps: Gap[] = [];
  const knots: [number, number][] = [[since, 0]];
  let x = 0;
  let day = since;
  for (const g of empties) {
    x += (g.from - day) * pxPerDay;
    gaps.push({ ...g, x });
    knots.push([g.from, x]);
    x += GAP_PX;
    knots.push([g.to, x]);
    day = g.to;
  }
  let width = x + (until - day) * pxPerDay;
  if (width < viewport) {
    until += (viewport - width) / pxPerDay;
    width = viewport;
  }
  knots.push([until, width]);

  // knots の from 列の値を to 列へ。端より外は詰めない縮尺で延ばす
  const along = (value: number, from: 0 | 1): number => {
    const to = 1 - from;
    const outside = from === 0 ? pxPerDay : 1 / pxPerDay;
    const first = knots[0];
    const last = knots[knots.length - 1];
    if (value <= first[from]) return first[to] + (value - first[from]) * outside;
    if (value >= last[from]) return last[to] + (value - last[from]) * outside;
    const i = knots.findIndex((k) => k[from] > value);
    const [a, b] = [knots[i - 1], knots[i]];
    return a[to] + ((value - a[from]) * (b[to] - a[to])) / (b[from] - a[from]);
  };
  return { since, until, width, pxPerDay, gaps, toX: (d) => along(d, 0), fromX: (px) => along(px, 1) };
}

/** 目盛りの文字の幅。左の余白に 4px、数字・区切りは 0.75rem で 8px ほどで見積もる */
function tickLabelWidth(label: string): number {
  return 4 + label.length * 8;
}

function ticks(since: number, until: number, pxPerDay: number): Tick[] {
  const result: Tick[] = [];
  for (const days of [1, 2, 7, 14]) {
    if (days * pxPerDay < MIN_TICK_PX) continue;
    for (let day = Math.ceil(since); day <= until; day += days) {
      const p = fromDayNumber(day);
      const yearStart = p.month === 1 && p.day === 1;
      result.push({ at: day, label: yearStart ? `${p.year}/01/01` : `${pad2(p.month)}/${pad2(p.day)}`, major: p.day === 1 });
    }
    return result;
  }
  const first = fromDayNumber(since);
  for (const months of [1, 2, 3, 6]) {
    if (months * 30.4 * pxPerDay < MIN_TICK_PX) continue;
    let year = first.year;
    let month = Math.ceil(first.month / months) * months + 1 - months;
    for (;;) {
      if (month > 12) {
        year += 1;
        month -= 12;
      }
      const at = dayNumber({ year, month, day: 1, hour: 0, minute: 0, second: 0 });
      if (at > until) return result;
      if (at >= since) result.push({ at, label: `${year}/${pad2(month)}`, major: month === 1 });
      month += months;
    }
  }
  const steps = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000];
  const years = steps.find((step) => step * 365.2 * pxPerDay >= MIN_TICK_PX) ?? steps[steps.length - 1];
  for (let year = Math.ceil(first.year / years) * years; ; year += years) {
    const at = dayNumber({ year, month: 1, day: 1, hour: 0, minute: 0, second: 0 });
    if (at > until) return result;
    if (at >= since) result.push({ at, label: String(year), major: year % (years * 5) === 0 });
  }
}

/** 時刻を日の単位に丸める。期間はその日の始めから、終わりの日の終わりまで */
function daySpan(start: number, end: number | null): { at: number; start: number; end: number | null } {
  const from = Math.floor(start);
  return { at: start, start: from, end: end === null ? null : Math.max(from + 1, Math.ceil(end)) };
}

function itemsOf(data: TimelineResponse): Item[] {
  const items: Item[] = [];
  for (const record of data.episode.items) {
    const start = dayOf(record.start);
    if (start === null) continue;
    items.push({ kind: "episode", key: `episode-${record.id}`, id: record.id as number, label: String(record.label || `id=${record.id}`),
      record, labels: data.episode.labels ?? {}, ...daySpan(start, dayOf(record.end)) });
  }
  for (const record of data.event.items) {
    const time = dayOf(record.time);
    if (time === null) continue;
    // 期間(start〜end)を持つ出来事は帯にする
    const start = dayOf(record.start);
    const end = dayOf(record.end);
    const span = start !== null && end !== null && end >= start;
    items.push({ kind: "event", key: `event-${record.id}`, id: record.id as number, label: String(record.label || `id=${record.id}`),
      record, labels: data.event.labels ?? {}, ...daySpan(span ? start : time, span ? end : null) });
  }
  return items;
}

/** 日付をずらしたときに直す欄。話は開始・終了、出来事は時刻・開始・終了を同じ日数だけ動かす。 */
function shifted(item: Item, days: number): Rec {
  const keys = item.kind === "episode" ? ["start", "end"] : ["time", "start", "end"];
  const changes: Rec = {};
  for (const key of keys) if (item.record[key] != null) changes[key] = shiftDays(item.record[key], days);
  return changes;
}

/** 中心の時刻を省いて開いたら、最後の話(無ければ最後の出来事)の時刻を中心にする。どちらも無ければ 1 年。API は時刻の順に返す */
function defaultCenter(data: TimelineResponse): string {
  const episode = data.episode.items.at(-1)?.start;
  if (episode) return String(episode);
  const event = data.event.items.at(-1)?.time;
  if (event) return String(event);
  return formatStamp({ year: 1, month: 1, day: 1, hour: 0, minute: 0, second: 0 });
}

export default function TimelinePage() {
  const router = useRouter();
  const search = useSearchParams();
  const at = search.get("at");
  const spanParam = Number(search.get("span"));
  const span = SPANS.includes(spanParam) ? spanParam : DEFAULT_SPAN;
  const storyId = Number(search.get("story_id")) || null;
  const locationId = Number(search.get("location_id")) || null;
  const centerParts = parseStamp(at);
  const center = centerParts ? dayNumber(centerParts) : null;

  const [draft, setDraft] = useState<string | null>(at);
  const [data, setData] = useState<TimelineResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  // スクロールする欄のうち、段の名前を除いた見える幅(viewport)と、段の名前の幅(label)
  const [box, setBox] = useState({ viewport: 0, label: 0 });
  // 期間に必ず含める時刻。入力欄・URL で中心を飛ばした先で、スクロールでは変えない(変えると軸が組み直されて位置が飛ぶ)
  const [anchor, setAnchor] = useState<number | null>(null);
  const [drag, setDrag] = useState<Drag | null>(null);
  // 保存を待つあいだ、落とした所に置いておく
  const [pending, setPending] = useState<{ key: string; days: number } | null>(null);
  const [addMenu, setAddMenu] = useState<AddMenu | null>(null);
  const [modal, setModal] = useState<ModalState | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const scrollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // スクロールの位置を合わせ済みの中心(at)と軸(scale)。スクロールから URL へ書いた at はここに入れ、位置を合わせ直さない
  const aligned = useRef<{ at: string | null; scale: Scale | null }>({ at: null, scale: null });
  const storyOptions = useOptions("story");
  const { tip, show, hide } = useTooltip();

  const navigate = useCallback(
    (changes: Record<string, string | number | null>) => {
      const params = new URLSearchParams(search.toString());
      for (const [key, value] of Object.entries(changes)) {
        if (value === null || value === "") params.delete(key);
        else params.set(key, String(value));
      }
      router.replace(`/timeline?${params}`);
    },
    [router, search],
  );

  useEffect(() => {
    if (!at && data) navigate({ at: defaultCenter(data) });
  }, [at, data, navigate]);

  // URL の中心が変わったら(スクロールしたときなど)入力欄も合わせる
  const [shownAt, setShownAt] = useState(at);
  if (at !== shownAt) {
    setShownAt(at);
    setDraft(at);
  }

  useEffect(() => {
    let alive = true;
    getTimeline({ story_id: storyId, location_id: locationId })
      .then((result) => {
        if (!alive) return;
        setData(result);
        setError(null);
        setPending(null);
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [storyId, locationId, version]);

  // スクロールする欄。幅を測り、縦のホイールを横のスクロールに回す(段の名前の上と Shift を押したときは縦のまま)
  const scrollBoxRef = useCallback((element: HTMLDivElement | null) => {
    scrollRef.current = element;
    if (!element) return;
    const measure = () => {
      const label = element.querySelector<HTMLElement>(".timeline-label")?.offsetWidth ?? 0;
      setBox({ viewport: Math.max(0, element.clientWidth - label), label });
    };
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    const onWheel = (e: WheelEvent) => {
      if (e.ctrlKey || (e.target as Element).closest(".timeline-label")) return;
      const unit = e.deltaMode === WheelEvent.DOM_DELTA_LINE ? 16 : 1;
      // ブラウザは Shift のホイールを横にするので、こちらは逆に縦へ回す
      if (e.shiftKey) {
        e.preventDefault();
        element.scrollTop += (e.deltaY || e.deltaX) * unit;
        return;
      }
      // タッチパッドの横の動きはそのまま
      if (Math.abs(e.deltaX) >= Math.abs(e.deltaY)) return;
      e.preventDefault();
      element.scrollLeft += e.deltaY * unit;
    };
    element.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      observer.disconnect();
      element.removeEventListener("wheel", onWheel);
    };
  }, []);

  useEffect(() => {
    if (!addMenu) return;
    const onDown = (e: globalThis.PointerEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setAddMenu(null);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setAddMenu(null);
    };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [addMenu]);

  useEffect(() => () => {
    if (scrollTimer.current) clearTimeout(scrollTimer.current);
  }, []);

  const items = useMemo(() => (data ? itemsOf(data) : []), [data]);

  // 軸は全部の札(と飛ばした先の中心)を含め、前後に画面の半分ずつ余白を取る。端の札も画面の中ほどまで持ってこられる
  const scale = useMemo(() => {
    let lo = anchor ?? Infinity;
    let hi = anchor ?? -Infinity;
    for (const item of items) {
      lo = Math.min(lo, item.start);
      hi = Math.max(hi, item.end ?? item.start + 1);
    }
    if (box.viewport === 0 || lo > hi) return null;
    return compress(Math.floor(lo - span / 2), Math.ceil(hi + span / 2), lo, hi, anchor, box.viewport / span, box.viewport, items);
  }, [anchor, items, span, box.viewport]);
  const pxPerDay = scale?.pxPerDay ?? 0;
  const toX = useCallback((day: number) => scale?.toX(day) ?? 0, [scale]);
  const fromX = useCallback((x: number) => scale?.fromX(x) ?? 0, [scale]);

  // 中心を飛ばしたとき・軸が組み直されたとき(縮尺を変えた、保存して読み直した)は、URL の中心が画面の真ん中に来るようスクロールする
  useLayoutEffect(() => {
    if (center === null) return;
    if (at !== aligned.current.at) {
      aligned.current = { at, scale: null };
      setAnchor(center);
    }
    const element = scrollRef.current;
    if (!element || !scale || aligned.current.scale === scale) return;
    aligned.current.scale = scale;
    element.scrollLeft = scale.toX(center) - box.viewport / 2;
  }, [at, center, scale, box.viewport]);

  const onScroll = () => {
    setAddMenu(null);
    if (scrollTimer.current) clearTimeout(scrollTimer.current);
    scrollTimer.current = setTimeout(() => {
      const element = scrollRef.current;
      if (!element || !scale) return;
      const value = formatStamp(fromDayNumber(scale.fromX(element.scrollLeft + box.viewport / 2)));
      if (value === at) return;
      aligned.current.at = value;
      navigate({ at: value });
    }, SCROLL_SETTLE_MS);
  };

  const rows = useMemo(() => {
    if (!data || !scale) return { episodes: [] as Row[], events: null as Row | null };
    const byStory = new Map<number, Item[]>();
    if (storyId !== null) byStory.set(storyId, []);
    for (const item of items.filter((i) => i.kind === "episode")) {
      const story = item.record.story_id as number;
      if (!byStory.has(story)) byStory.set(story, []);
      byStory.get(story)!.push(item);
    }
    // 読み直しても段が入れ替わらないよう、作品の id 順に並べる
    const episodes: Row[] = [...byStory.entries()].sort(([a], [b]) => a - b).map(([story, storyItems]) => {
      const { placed, lanes } = pack(storyItems, toX);
      // 絞り込んだ作品に話が無ければ、名前は選択肢から引く
      const name = data.episode.labels?.story_id?.[story] ?? storyOptions.find((o) => o.id === story)?.label;
      return { key: `story-${story}`, label: name ? `${name} (${story})` : String(story), storyId: story, items: placed, lanes };
    });
    if (episodes.length === 0) episodes.push({ key: "story-none", label: "", storyId: null, items: [], lanes: 1 });
    const { placed, lanes } = pack(items.filter((i) => i.kind === "event"), toX);
    return { episodes, events: { key: "events", label: "", storyId: null, items: placed, lanes } as Row };
  }, [data, scale, items, storyId, storyOptions, toX]);

  const axisTicks = useMemo(() => {
    if (!scale) return [];
    // 詰めた帯の間ごとに刻む。帯の中は目盛りを置かないので、全期間を一日ずつ回らずに済む
    const bounds = [scale.since, ...scale.gaps.flatMap((g) => [g.from, g.to]), scale.until];
    const all: Tick[] = [];
    for (let i = 0; i < bounds.length; i += 2) all.push(...ticks(bounds[i], bounds[i + 1], scale.pxPerDay));
    // 年の入った目盛り(11572/01/01)は日の間隔より長いことがあるので、前の文字に掛かる目盛りは文字を出さない
    let labelEnd = -Infinity;
    return all.map((tick) => {
      const x = scale.toX(tick.at);
      if (x < labelEnd || scale.gaps.some((g) => x > g.x - TICK_LABEL_PX && x < g.x + GAP_PX)) return { ...tick, label: "" };
      labelEnd = x + tickLabelWidth(tick.label);
      return tick;
    });
  }, [scale]);

  /** 横に dx px 動かしたら何日ずれるか。詰めた帯の上では一気に日が進む */
  const daysAt = (item: Item, dx: number) => (pxPerDay > 0 ? Math.round(fromX(toX(item.start) + dx) - item.start) : 0);

  const dragDays = (item: Item) => {
    if (drag?.item.key === item.key) return daysAt(item, drag.dx);
    if (pending?.key === item.key) return pending.days;
    return 0;
  };

  const move = async (item: Item, days: number) => {
    const changes = shifted(item, days);
    setPending({ key: item.key, days });
    setMessage(null);
    try {
      await updateRecord(item.kind, item.id, changes);
      setMessage(T.timeline.moved(item.label, String(changes.start ?? changes.time)));
    } catch (e) {
      setError(T.timeline.moveFailed(e instanceof Error ? e.message : String(e)));
    }
    setVersion((v) => v + 1);
  };

  const onItemDown = (e: PointerEvent<HTMLDivElement>, item: Item) => {
    if (e.button !== 0 || pending) return;
    e.stopPropagation();
    e.currentTarget.setPointerCapture(e.pointerId);
    hide();
    setDrag({ item, startX: e.clientX, dx: 0 });
  };

  const onItemMove = (e: PointerEvent<HTMLDivElement>) => {
    if (drag) setDrag({ ...drag, dx: e.clientX - drag.startX });
  };

  const onItemUp = (e: PointerEvent<HTMLDivElement>) => {
    if (!drag) return;
    const { item } = drag;
    const dx = e.clientX - drag.startX;
    setDrag(null);
    if (Math.abs(dx) <= DRAG_THRESHOLD) {
      setModal({ table: item.kind, id: item.id });
      return;
    }
    const days = daysAt(item, dx);
    if (days !== 0) void move(item, days);
  };

  const onTrackClick = (e: MouseEvent<HTMLDivElement>, row: Row) => {
    if (pxPerDay === 0) return;
    const snapped = Math.floor(fromX(e.clientX - e.currentTarget.getBoundingClientRect().left));
    // 画面の端で押しても吹き出しがはみ出さないよう、内側へ寄せる
    setAddMenu({ x: Math.min(e.clientX, window.innerWidth - ADD_MENU_WIDTH), y: Math.min(e.clientY, window.innerHeight - ADD_MENU_HEIGHT),
      at: formatStamp(fromDayNumber(snapped)), storyId: row.storyId });
  };

  const openAdd = (table: Kind) => {
    if (!addMenu) return;
    const initial: Rec = table === "episode" ? { start: addMenu.at } : { time: addMenu.at };
    const story = addMenu.storyId ?? storyId;
    if (table === "episode" && story !== null) initial.story_id = story;
    if (locationId !== null) initial.location_id = locationId;
    setAddMenu(null);
    setModal({ table, initial });
  };

  const tooltipLines = (item: Item) => {
    const r = item.record;
    return item.kind === "episode"
      ? [item.label, T.span(r.start, r.end) || String(r.start), labelOf(item.labels, "story_id", r.story_id),
         r.location_id != null && labelOf(item.labels, "location_id", r.location_id), String(r.preview ?? "")]
      : [item.label, String(r.time), r.start != null && T.span(r.start, r.end), String(r.confirmed ?? ""),
         r.location_id != null && labelOf(item.labels, "location_id", r.location_id), String(r.preview ?? "")];
  };

  const gapLines = (g: Gap) => [T.timeline.gap, `${formatStamp(fromDayNumber(g.from))} – ${formatStamp(fromDayNumber(g.to))}`];

  const renderRow = (row: Row) => (
    <div key={row.key} className="timeline-row">
      <div className="timeline-label" title={row.label}>{row.label}</div>
      <div className="timeline-track" style={{ width: scale?.width, height: row.lanes * LANE_HEIGHT + 6 }} onClick={(e) => onTrackClick(e, row)}>
        {row.items.map((item) => {
          const days = dragDays(item);
          const dragging = drag?.item.key === item.key;
          const className = [
            "timeline-item", item.kind,
            item.end === null ? "point" : "",
            dragging ? "dragging" : "",
            pending?.key === item.key ? "saving" : "",
            item.record.confirmed === "未確認" ? "unconfirmed" : "",
            item.record.confirmed === "非承認" ? "rejected" : "",
          ].join(" ");
          const target = days !== 0 && shifted(item, days);
          const offset = days ? toX(item.start + days) - item.x : 0;
          return (
            <div
              key={item.key}
              className={className}
              style={{ left: item.x, top: 3 + item.lane * LANE_HEIGHT, transform: offset ? `translateX(${offset}px)` : undefined,
                ...(dragging ? { minWidth: item.width } : { width: item.width }) }}
              onPointerDown={(e) => onItemDown(e, item)}
              onPointerMove={onItemMove}
              onPointerUp={onItemUp}
              onPointerCancel={() => setDrag(null)}
              onClick={(e) => e.stopPropagation()}
              onMouseMove={(e) => !drag && show(e, tooltipLines(item))}
              onMouseLeave={hide}
            >
              {item.barWidth > 0 && <span className="timeline-bar" style={{ width: item.barWidth }} />}
              <span className="timeline-text">
                {item.label}
                {target && <span className="timeline-target"> → {String(target.start ?? target.time)}</span>}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );

  /** 画面の半分ずつ前後へスクロールする。スクロールできない(札が無く画面に収まる)ときは中心の時刻を送る */
  const shift = (direction: number) => {
    const element = scrollRef.current;
    if (element && element.scrollWidth > element.clientWidth) element.scrollBy({ left: (direction * box.viewport) / 2, behavior: "smooth" });
    else if (center !== null) navigate({ at: formatStamp(fromDayNumber(center + (direction * span) / 2)) });
  };

  return (
    <div className="page-fill">
      <PageTitle kind={T.timeline.title} record={at} />
      <div className="toolbar">
        <h1 style={{ margin: 0 }}>{T.timeline.title}</h1>
        <button type="button" onClick={() => shift(-1)} disabled={center === null}>{T.timeline.earlier}</button>
        <form
          className="timeline-center-input"
          onSubmit={(e) => {
            e.preventDefault();
            if (parseStamp(draft)) navigate({ at: formatStamp(parseStamp(draft)!) });
          }}
        >
          <span className="hint">{T.timeline.center}</span>
          <StampInput
            value={draft}
            onChange={(value) => {
              setDraft(value);
              if (value && FULL_STAMP.test(value)) navigate({ at: value });
            }}
          />
        </form>
        <button type="button" onClick={() => shift(1)} disabled={center === null}>{T.timeline.later}</button>
        <label className="hint">
          {T.timeline.span}{" "}
          <select value={span} onChange={(e) => navigate({ span: Number(e.target.value) })}>
            {SPANS.map((days) => (
              <option key={days} value={days}>{T.timeline.spanOf(days)}</option>
            ))}
          </select>
        </label>
        <label className="hint timeline-filter">
          {T.timeline.story}
          <ReferenceSelect table="story" value={storyId} nullable onChange={(value) => navigate({ story_id: value })} />
        </label>
        <label className="hint timeline-filter">
          {T.timeline.location}
          <TreeReferenceSelect table="location" value={locationId} nullable onChange={(value) => navigate({ location_id: value })} />
        </label>
      </div>
      {error && <div className="status error">{error}</div>}
      {message && !error && <div className="status ok">{message}</div>}
      {!data ? (
        !error && <div className="status info">{T.loading}</div>
      ) : (
        <div className="timeline" aria-busy={pending !== null}>
          <div className="timeline-scroll" ref={scrollBoxRef} onScroll={onScroll}>
            <div className="timeline-row timeline-axis">
              <div className="timeline-label" />
              <div className="timeline-track" style={{ width: scale?.width }}>
                {scale?.gaps.map((g) => (
                  <div key={g.from} className="timeline-gap" style={{ left: g.x, width: GAP_PX }}
                    onMouseMove={(e) => show(e, gapLines(g))} onMouseLeave={hide}>
                    {T.timeline.skipped(g.to - g.from)}
                  </div>
                ))}
                {axisTicks.map((tick) => (
                  <div key={tick.at} className={`timeline-tick ${tick.major ? "major" : ""}`} style={{ left: toX(tick.at) }}>
                    {tick.label}
                  </div>
                ))}
              </div>
            </div>
            <div className="timeline-body">
              {/* 目盛りの線と詰めた帯は、段ごとに描かず全部の段に一枚で重ねる */}
              <div className="timeline-lines" style={{ left: box.label, width: scale?.width }}>
                {scale?.gaps.map((g) => (
                  <div key={g.from} className="timeline-gap" style={{ left: g.x, width: GAP_PX }} />
                ))}
                {axisTicks.map((tick) => (
                  <div key={tick.at} className={`timeline-grid ${tick.major ? "major" : ""}`} style={{ left: toX(tick.at) }} />
                ))}
              </div>
              <div className="timeline-section" style={{ width: box.label + box.viewport }}>{T.timeline.episodes}</div>
              {rows.episodes.map(renderRow)}
              <div className="timeline-section" style={{ width: box.label + box.viewport }}>{T.timeline.events}</div>
              {rows.events && renderRow(rows.events)}
            </div>
          </div>
          {/* 画面の真ん中の線。スクロールが止まると、ここの時刻が中心(URL の at)になる */}
          {scale && <div className="timeline-center" style={{ left: box.label + box.viewport / 2 }} />}
        </div>
      )}
      <div className="hint" style={{ marginTop: "0.4rem" }}>{T.timeline.hint}</div>
      {addMenu && (
        <div ref={menuRef} className="timeline-add" style={{ left: addMenu.x, top: addMenu.y }}>
          <span className="hint">{addMenu.at}</span>
          <button type="button" onClick={() => openAdd("episode")}>{T.timeline.addEpisode}</button>
          <button type="button" onClick={() => openAdd("event")}>{T.timeline.addEvent}</button>
        </div>
      )}
      {modal && (
        <RecordModal
          table={modal.table}
          id={modal.id}
          initial={modal.initial}
          onClose={() => setModal(null)}
          onSaved={() => {
            setModal(null);
            setVersion((v) => v + 1);
          }}
        />
      )}
      <Tooltip tip={tip} />
    </div>
  );
}
