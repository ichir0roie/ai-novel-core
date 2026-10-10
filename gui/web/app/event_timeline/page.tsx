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
import Modal from "@/components/Modal";
import NewEventModal from "@/components/NewEventModal";
import { useOptions } from "@/components/ReferenceSelect";
import StampInput from "@/components/StampInput";
import TreeReferenceSelect from "@/components/TreeReferenceSelect";
import Tooltip, { useTooltip } from "@/components/Tooltip";
import {
  deleteEventWithChildren,
  getRecord,
  listAllRecords,
  updateEvents,
  type Rec,
} from "@/lib/api";
import { PageTitle } from "@/lib/meta";
import {
  dayNumber,
  formatStamp,
  fromDayNumber,
  parseStamp,
  shiftDays,
} from "@/lib/stamp";
import { T } from "@/lib/text";
import {
  axisTicksOf,
  DAYS_PER_YEAR,
  dayOf,
  daySpan,
  DRAG_THRESHOLD,
  FULL_STAMP,
  GAP_PX,
  ITEM_GAP,
  ITEM_HEIGHT,
  savedView,
  scaleOf,
  SCROLL_SETTLE_MS,
  type Gap,
  type Scale,
  type View,
} from "@/lib/timelineAxis";

// 縮尺(画面の高さの年数)と、出来事の無い区間を詰めるかを覚えておく localStorage のキー
const VIEW_STORAGE_KEY = "event-timeline-view";
// 層(列)の幅(px)。札はこの幅から左右の余白を引いた幅で、余白に親子を結ぶ線を通す
const LAYER_WIDTH = 190;
const LAYER_PAD = 12;
// 層の右に空けておく空の層の数。出来事を足すときにクリックする所を残す
const SPARE_LAYERS = 1;
// 場所の絞り込みを覚えておく localStorage のキー。絞り込みを付けずに開いたら、前に選んだ場所へ移す
const FILTER_STORAGE_KEY = "event-timeline-filter";

// 出来事一つ。parent は親の出来事の id(親が読めた出来事に無ければ根として置く)
type Item = {
  key: string;
  id: number;
  label: string;
  record: Rec;
  parent: number | null;
  at: number;
  start: number;
  end: number | null;
};
type Placed = Item & {
  y: number;
  height: number;
  barHeight: number;
  layer: number;
};
// over は落とす先(新しい親)の出来事。掴んだ札・その子孫の上・札の無い所では null
type Drag = {
  item: Item;
  startX: number;
  startY: number;
  dx: number;
  dy: number;
  over: number | null;
};
// 変更モードで溜めた移し。base は読み込んだときの出来事で、days はそこから何日ずらすか、
// parent は付け替える先の親(根にするなら null、付け替えないなら undefined)
type Change = { base: Item; days: number; parent?: number | null };

// 動かすと一緒にずらす時刻の欄
const TIME_KEYS = ["time", "start", "end"] as const;

const byTime = (a: Item, b: Item) =>
  a.start - b.start || a.at - b.at || a.id - b.id;

function itemOf(record: Rec): Item | null {
  // 開始の無い出来事は、出来事の時刻(`time`)の一点に置く
  const start = dayOf(record.start ?? record.time);
  if (start === null) return null;
  return {
    key: `event-${record.id}`,
    id: record.id as number,
    label: T.nameId(record.label as string, record.id),
    record,
    parent:
      typeof record.parent_event_id === "number"
        ? record.parent_event_id
        : null,
    ...daySpan(start, dayOf(record.end)),
  };
}

/** 日付をずらしたときに直す欄。時刻・開始・終了を同じ日数だけ動かす */
function shifted(record: Rec, days: number): Rec {
  const changes: Rec = {};
  for (const key of TIME_KEYS)
    if (record[key] != null) changes[key] = shiftDays(record[key], days);
  return changes;
}

/** 溜めた移しを当てた出来事。札はこの時刻・親の所に描く */
function changedItem({ base, days, parent }: Change): Item {
  const record: Rec = {
    ...base.record,
    ...shifted(base.record, days),
    ...(parent !== undefined ? { parent_event_id: parent } : {}),
  };
  return itemOf(record) ?? base;
}

/** 保存する欄。動かした分だけを渡す */
function changeForm({ base, days, parent }: Change): Rec {
  return {
    id: base.id,
    ...(days !== 0 ? shifted(base.record, days) : {}),
    ...(parent !== undefined ? { parent_event_id: parent } : {}),
  };
}

/** 親の id ごとの子(時刻の順)。親が読めた出来事に無い出来事は根(キーは null)に入れる */
function childrenOf(items: Item[]): Map<number | null, Item[]> {
  const ids = new Set(items.map((item) => item.id));
  const children = new Map<number | null, Item[]>();
  for (const item of [...items].sort(byTime)) {
    const key = item.parent !== null && ids.has(item.parent) ? item.parent : null;
    children.set(key, [...(children.get(key) ?? []), item]);
  }
  return children;
}

/** `id` の子孫の出来事(自分は含めない) */
function descendantsOf(
  id: number,
  children: Map<number | null, Item[]>,
): Item[] {
  const found: Item[] = [];
  const seen = new Set<number>([id]);
  const walk = (at: number) => {
    for (const child of children.get(at) ?? []) {
      if (seen.has(child.id)) continue;
      seen.add(child.id);
      found.push(child);
      walk(child.id);
    }
  };
  walk(id);
  return found;
}

/** 場所 `id` とその配下の場所 */
function placesUnder(
  id: number,
  options: { id: number; parent_id?: number | null }[],
): Set<number> {
  const childrenOf = new Map<number, number[]>();
  for (const option of options)
    if (option.parent_id != null)
      childrenOf.set(option.parent_id, [...(childrenOf.get(option.parent_id) ?? []), option.id]);
  const found = new Set<number>();
  const walk = (at: number) => {
    if (found.has(at)) return;
    found.add(at);
    (childrenOf.get(at) ?? []).forEach(walk);
  };
  walk(id);
  return found;
}

/**
 * 場所で絞った出来事。場所に当たる出来事と、親子の線が切れないようその祖先(`context` に入れて薄く描く)を返す
 */
function inPlaces(
  items: Item[],
  places: Set<number>,
): { shown: Item[]; context: Set<number> } {
  const byId = new Map(items.map((item) => [item.id, item]));
  const matched = new Set(
    items
      .filter((item) => places.has(item.record.location_id as number))
      .map((item) => item.id),
  );
  const context = new Set<number>();
  for (const id of matched)
    for (
      let at = byId.get(id)?.parent ?? null;
      at !== null && !matched.has(at) && !context.has(at);
      at = byId.get(at)?.parent ?? null
    )
      context.add(at);
  return {
    shown: items.filter((item) => matched.has(item.id) || context.has(item.id)),
    context,
  };
}

/**
 * 先に根を時刻の順に置き、そのあと根ごとに子孫を深さ優先でたどって置く。札は、親の層の右(根は一番左の層)から、
 * 上下で他の札と重ならない一番左の層に置く。根の期間が重なれば遅い方が 2 層目へ移り、子はその右へ重なっていく。
 * 札は名前が一行入る高さまで層を取る
 */
function layout(
  items: Item[],
  children: Map<number | null, Item[]>,
  toY: (day: number) => number,
): { placed: Placed[]; layers: number } {
  // 層ごとに、札が取った上端・下端
  const taken: [number, number][][] = [];
  const free = (layer: number, top: number, bottom: number) =>
    (taken[layer] ?? []).every(([a, b]) => bottom <= a || top >= b);
  const placed: Placed[] = [];
  const seen = new Set<number>();
  const put = (item: Item, from: number): Placed => {
    seen.add(item.id);
    const y = toY(item.start);
    const barHeight = item.end === null ? 0 : Math.max(0, toY(item.end) - y);
    const height = Math.max(barHeight, ITEM_HEIGHT);
    let layer = from;
    while (!free(layer, y, y + height + ITEM_GAP)) layer++;
    (taken[layer] ??= []).push([y, y + height + ITEM_GAP]);
    const one = { ...item, y, height, barHeight, layer };
    placed.push(one);
    return one;
  };
  const descend = (parent: Placed) => {
    for (const child of children.get(parent.id) ?? [])
      if (!seen.has(child.id)) descend(put(child, parent.layer + 1));
  };
  const roots = (children.get(null) ?? []).map((root) => put(root, 0));
  roots.forEach(descend);
  // 親をたどると輪になる出来事は根から届かないので、残りを根として置く
  for (const item of [...items].sort(byTime))
    if (!seen.has(item.id)) descend(put(item, 0));
  return { placed, layers: Math.max(1, taken.length) };
}

/** 中心の時刻を省いて開いたら、最後の出来事の時刻を中心にする。無ければ 1 年 */
function defaultCenter(items: Item[]): string {
  const last = [...items].sort(byTime).at(-1);
  return formatStamp(
    last
      ? fromDayNumber(last.start)
      : { year: 1, month: 1, day: 1, hour: 0, minute: 0, second: 0 },
  );
}

export default function EventTimelinePage() {
  const router = useRouter();
  const search = useSearchParams();
  const at = search.get("at");
  const locationId = Number(search.get("location_id")) || null;
  const centerParts = parseStamp(at);
  const center = centerParts ? dayNumber(centerParts) : null;

  const [draft, setDraft] = useState<string | null>(at);
  const [records, setRecords] = useState<Rec[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  // スクロールする欄のうち、層の名前の行を除いた見える高さ(viewport)と、層の名前の行の高さ(head)
  const [box, setBox] = useState({ viewport: 0, head: 0 });
  // 期間に必ず含める時刻。入力欄・URL で中心を飛ばした先で、スクロールでは変えない(変えると軸が組み直されて位置が飛ぶ)
  const [anchor, setAnchor] = useState<number | null>(null);
  // 今見ている所が、軸を画面の高さで区切った何番目か(等間隔の軸の目盛りを、この前後にだけ置く)
  const [screen, setScreen] = useState(0);
  const [drag, setDrag] = useState<Drag | null>(null);
  // 変更モード。札を動かしても保存せず、出来事の id ごとに移しを溜めて、適用でまとめて保存する
  const [editing, setEditing] = useState(false);
  const [changes, setChanges] = useState<Map<number, Change>>(new Map());
  const [applying, setApplying] = useState(false);
  // 押した出来事と、その本文(開いてから引く)
  const [viewing, setViewing] = useState<Item | null>(null);
  const [viewingText, setViewingText] = useState<string | null>(null);
  const [adding, setAdding] = useState<{
    start: string | null;
    parent: { id: number; label: string } | null;
  } | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const scrollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // スクロールの位置を合わせ済みの中心(at)と軸(scale)
  const aligned = useRef<{ at: string | null; scale: Scale | null }>({
    at: null,
    scale: null,
  });
  const { tip, show, hide } = useTooltip();
  const [view, setView] = useState<View>({ years: 1, squeeze: false });
  useEffect(() => setView(savedView(VIEW_STORAGE_KEY)), []);
  const span = view.years * DAYS_PER_YEAR;

  const changeView = (next: Partial<View>) => {
    const merged = { ...view, ...next };
    setView(merged);
    try {
      localStorage.setItem(VIEW_STORAGE_KEY, JSON.stringify(merged));
    } catch {
      // 覚えられなくても、この画面の中では縮尺が効く
    }
  };

  const navigate = useCallback(
    (next: Record<string, string | number | null>) => {
      const params = new URLSearchParams(search.toString());
      for (const [key, value] of Object.entries(next)) {
        if (value === null || value === "") params.delete(key);
        else params.set(key, String(value));
      }
      router.replace(`/event_timeline?${params}`);
    },
    [router, search],
  );

  // 絞り込みを付けずに開いたら(ナビのリンクなど)、前に選んだ場所へ移す
  const [restoring, setRestoring] = useState(true);
  useEffect(() => {
    if (!restoring) return;
    let saved: number | null = null;
    try {
      saved = Number(JSON.parse(localStorage.getItem(FILTER_STORAGE_KEY) ?? "null")?.location_id) || null;
    } catch {
      // 読めなければ絞り込まない
    }
    if (!search.has("location_id") && saved !== null) navigate({ location_id: saved });
    else setRestoring(false);
  }, [restoring, search, navigate]);

  /** 場所の絞り込みを変え、次に絞り込みを付けずに開いたときのために覚えておく */
  const filterPlace = (value: number | null) => {
    try {
      localStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify({ location_id: value }));
    } catch {
      // 覚えられなくても、この画面の中では絞り込みが効く
    }
    navigate({ location_id: value });
  };

  // URL の中心が変わったら(スクロールしたときなど)入力欄も合わせる
  const [shownAt, setShownAt] = useState(at);
  if (at !== shownAt) {
    setShownAt(at);
    setDraft(at);
  }

  // 別のタブで出来事を足して戻ってきたら読み直す。保存・ドラッグの途中は待つ
  const [reloads, setReloads] = useState(0);
  const busy = useRef(false);
  useLayoutEffect(() => {
    busy.current = applying || drag !== null;
  });
  useEffect(() => {
    const reload = () => {
      if (!busy.current) setReloads((n) => n + 1);
    };
    window.addEventListener("focus", reload);
    return () => window.removeEventListener("focus", reload);
  }, []);

  useEffect(() => {
    let alive = true;
    listAllRecords("event")
      .then((result) => {
        if (!alive) return;
        setRecords(result);
        setError(null);
      })
      .catch(
        (e) => alive && setError(e instanceof Error ? e.message : String(e)),
      );
    return () => {
      alive = false;
    };
  }, [reloads]);

  useEffect(() => {
    if (changes.size === 0) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [changes.size]);

  useEffect(() => {
    if (!viewing) return;
    let alive = true;
    setViewingText(null);
    getRecord("event", viewing.id)
      .then((r) => alive && setViewingText(String(r.record.text ?? "")))
      .catch(
        (e) => alive && setError(e instanceof Error ? e.message : String(e)),
      );
    return () => {
      alive = false;
    };
  }, [viewing]);

  const scrollBoxRef = useCallback((element: HTMLDivElement | null) => {
    scrollRef.current = element;
    if (!element) return;
    const measure = () => {
      const head =
        element.querySelector<HTMLElement>(".timeline-head")?.offsetHeight ?? 0;
      setBox({ viewport: Math.max(0, element.clientHeight - head), head });
    };
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(
    () => () => {
      if (scrollTimer.current) clearTimeout(scrollTimer.current);
    },
    [],
  );

  const loaded = useMemo(
    () => (records ?? []).map(itemOf).filter((item) => item !== null),
    [records],
  );
  const items = useMemo(
    () =>
      loaded.map((item) => {
        const change = changes.get(item.id);
        return change ? changedItem(change) : item;
      }),
    [loaded, changes],
  );
  // 動かす・消すときの子孫は、絞り込みで隠れた出来事も含めてたどる
  const children = useMemo(() => childrenOf(items), [items]);
  const locations = useOptions("location");
  const { shown, context } = useMemo(
    () =>
      locationId === null
        ? { shown: items, context: new Set<number>() }
        : inPlaces(items, placesUnder(locationId, locations)),
    [items, locationId, locations],
  );
  const shownChildren = useMemo(() => childrenOf(shown), [shown]);
  const byId = useMemo(
    () => new Map(items.map((item) => [item.id, item])),
    [items],
  );

  useEffect(() => {
    if (records && !restoring && !at) navigate({ at: defaultCenter(shown) });
  }, [records, restoring, at, shown, navigate]);

  const scale = useMemo(
    () => scaleOf(shown, anchor, view, box.viewport),
    [anchor, shown, view, box.viewport],
  );
  const pxPerDay = scale?.pxPerDay ?? 0;
  const toY = useCallback((day: number) => scale?.toY(day) ?? 0, [scale]);
  const fromY = useCallback((y: number) => scale?.fromY(y) ?? 0, [scale]);

  // 中心を飛ばしたとき・軸が組み直されたときは、URL の中心が画面の真ん中に来るようスクロールする
  useLayoutEffect(() => {
    if (center === null) return;
    if (at !== aligned.current.at) {
      aligned.current = { at, scale: null };
      if (anchor !== center) {
        setAnchor(center);
        return;
      }
    }
    const element = scrollRef.current;
    if (!element || !scale || aligned.current.scale === scale) return;
    aligned.current.scale = scale;
    element.scrollTop = scale.toY(center) - box.viewport / 2;
  }, [at, center, anchor, scale, box.viewport]);

  // スクロールが止まったときに読む今の値
  const latest = useRef({ scale, viewport: box.viewport, at, center, navigate });
  useLayoutEffect(() => {
    latest.current = { scale, viewport: box.viewport, at, center, navigate };
  });

  const onScroll = () => {
    if (scrollRef.current && box.viewport > 0)
      setScreen(Math.floor(scrollRef.current.scrollTop / box.viewport));
    if (scrollTimer.current) clearTimeout(scrollTimer.current);
    scrollTimer.current = setTimeout(() => {
      const element = scrollRef.current;
      const now = latest.current;
      if (!element || !now.scale) return;
      const middle = element.scrollTop + now.viewport / 2;
      if (
        now.center !== null &&
        Math.abs(now.scale.toY(now.center) - middle) < 1
      )
        return;
      const value = formatStamp(fromDayNumber(now.scale.fromY(middle)));
      if (value === now.at) return;
      aligned.current.at = value;
      now.navigate({ at: value });
    }, SCROLL_SETTLE_MS);
  };

  const { placed, layers } = useMemo(
    () =>
      scale ? layout(shown, shownChildren, toY) : { placed: [], layers: 1 },
    [scale, shown, shownChildren, toY],
  );
  const placedById = useMemo(
    () => new Map(placed.map((item) => [item.id, item])),
    [placed],
  );
  const columns = layers + SPARE_LAYERS;

  const axisTicks = useMemo(
    () =>
      scale
        ? axisTicksOf(scale, shown, view.squeeze, screen, box.viewport)
        : [],
    [scale, shown, view.squeeze, screen, box.viewport],
  );

  const labelOfEvent = (id: number | null) =>
    id === null ? T.eventTimeline.root : (byId.get(id)?.label ?? T.nameId(undefined, id));

  /** 縦に dy px 動かしたら何日ずれるか。詰めた帯の上では一気に日が進む */
  const daysAt = (item: Item, dy: number) =>
    pxPerDay > 0 ? Math.round(fromY(toY(item.start) + dy) - item.start) : 0;

  /** ドラッグ中に、掴んだ札と一緒に動いて見える日数(掴んだ札と、その子孫) */
  const dragging = drag?.item;
  const draggedIds = useMemo(
    () =>
      dragging
        ? new Set([dragging.id, ...descendantsOf(dragging.id, children).map((d) => d.id)])
        : new Set<number>(),
    [dragging, children],
  );
  const dragDays =
    drag && drag.over === null && Math.abs(drag.dy) > DRAG_THRESHOLD
      ? daysAt(drag.item, drag.dy)
      : 0;

  /** 移しを溜める。同じ出来事を何度動かしても、読み込んだときの出来事からの移しにまとめる。元に戻ったら溜めた分から外す */
  const record = (
    next: Map<number, Change>,
    item: Item,
    days: number,
    parent?: number | null,
  ) => {
    const previous = next.get(item.id);
    const base = previous?.base ?? item;
    const target = parent !== undefined ? parent : previous?.parent;
    const change: Change = {
      base,
      days: (previous?.days ?? 0) + days,
      ...(target !== undefined && target !== base.parent ? { parent: target } : {}),
    };
    if (change.days === 0 && change.parent === undefined) next.delete(item.id);
    else next.set(item.id, change);
  };

  /** 札を日数ずらす。子孫の出来事も同じ日数だけずらす */
  const shift = (item: Item, days: number) => {
    const next = new Map(changes);
    for (const target of [item, ...descendantsOf(item.id, children)])
      record(next, target, days);
    setChanges(next);
  };

  const reparent = (item: Item, parent: number | null) => {
    const next = new Map(changes);
    record(next, item, 0, parent);
    setChanges(next);
  };

  const leaveEditing = () => {
    setChanges(new Map());
    setEditing(false);
  };

  const reload = async () => setRecords(await listAllRecords("event"));

  const apply = async () => {
    setApplying(true);
    setError(null);
    setMessage(null);
    try {
      await updateEvents([...changes.values()].map(changeForm));
      // 読み直した出来事と溜めた分を外すのを同じ描画で替え、札が元の所へ一度戻って見えないようにする
      await reload();
      setMessage(T.eventTimeline.applied(changes.size));
      leaveEditing();
    } catch (e) {
      setError(T.timeline.applyFailed(e instanceof Error ? e.message : String(e)));
    } finally {
      setApplying(false);
    }
  };

  const remove = async (item: Item) => {
    const count = descendantsOf(item.id, children).length;
    if (!window.confirm(T.eventTimeline.confirmDelete(item.label, count))) return;
    setError(null);
    setMessage(null);
    try {
      await deleteEventWithChildren(item.id);
      setViewing(null);
      await reload();
      setMessage(T.eventTimeline.deleted(item.label));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const onItemDown = (e: PointerEvent<HTMLDivElement>, item: Item) => {
    if (e.button !== 0 || applying) return;
    e.stopPropagation();
    e.currentTarget.setPointerCapture(e.pointerId);
    hide();
    setDrag({ item, startX: e.clientX, startY: e.clientY, dx: 0, dy: 0, over: null });
  };

  /** 指の下の札。掴んだ札とその子孫の上は親にできないので null */
  const eventUnder = (x: number, y: number): number | null => {
    const card = document
      .elementsFromPoint(x, y)
      .map((el) => el.closest<HTMLElement>(".event-timeline-item[data-id]"))
      .find((el) => el && !draggedIds.has(Number(el.dataset.id)));
    return card ? Number(card.dataset.id) : null;
  };

  const onItemMove = (e: PointerEvent<HTMLDivElement>) => {
    if (drag && editing)
      setDrag({
        ...drag,
        dx: e.clientX - drag.startX,
        dy: e.clientY - drag.startY,
        over: eventUnder(e.clientX, e.clientY),
      });
  };

  const onItemUp = (e: PointerEvent<HTMLDivElement>) => {
    if (!drag) return;
    const { item, over } = drag;
    const dx = e.clientX - drag.startX;
    const dy = e.clientY - drag.startY;
    setDrag(null);
    if (Math.abs(dx) <= DRAG_THRESHOLD && Math.abs(dy) <= DRAG_THRESHOLD) {
      setViewing(item);
      return;
    }
    if (!editing) return;
    // 別の札の上に落としたら、その札の子にする(時刻は動かさない)。それ以外は縦に動かした日数だけずらす
    if (over !== null) {
      if (over !== item.parent) reparent(item, over);
      return;
    }
    const days = Math.abs(dy) > DRAG_THRESHOLD ? daysAt(item, dy) : 0;
    if (days !== 0) shift(item, days);
  };

  /** 空いた所を押したら、その日に根の出来事を足す */
  const onTrackClick = (e: MouseEvent<HTMLDivElement>) => {
    if (pxPerDay === 0) return;
    const day = Math.floor(
      fromY(e.clientY - e.currentTarget.getBoundingClientRect().top),
    );
    setAdding({ start: formatStamp(fromDayNumber(day)), parent: null });
  };

  const spanOf = (r: Rec) => T.span(r.start ?? r.time, r.end) || String(r.time);

  /** 吹き出しと押したときのモーダルに出す、時刻・親・隠しの行 */
  const detailLines = (item: Item) => {
    const base = changes.get(item.id)?.base;
    return [
      spanOf(item.record),
      T.eventTimeline.parent(labelOfEvent(item.parent)),
      item.record.hidden === true && T.eventTimeline.hidden,
      context.has(item.id) && T.eventTimeline.outsideFilter,
      base && T.eventTimeline.was(spanOf(base.record), labelOfEvent(base.parent)),
    ];
  };
  const tooltipLines = (item: Item) => [
    item.label,
    ...detailLines(item).filter((line): line is string => Boolean(line)),
    String(item.record.preview ?? ""),
  ];
  const gapLines = (g: Gap) => [
    T.eventTimeline.gap,
    `${formatStamp(fromDayNumber(g.from))} – ${formatStamp(fromDayNumber(g.to))}`,
  ];

  const left = (layer: number) => layer * LAYER_WIDTH + LAYER_PAD;
  const right = (layer: number) => (layer + 1) * LAYER_WIDTH - LAYER_PAD;

  /** ドラッグ中に、掴んだ札と一緒に動いて見える縦のずれ(px) */
  const offsetOf = (item: Placed) =>
    dragDays && draggedIds.has(item.id) ? toY(item.start + dragDays) - item.y : 0;

  /** 親の札の右端から子の札の左端へ、子の札の名前の高さで折れ線を引く */
  const links = placed.flatMap((child) => {
    const parent = child.parent === null ? undefined : placedById.get(child.parent);
    if (!parent) return [];
    const [childY, parentY] = [child.y + offsetOf(child), parent.y + offsetOf(parent)];
    const y2 = childY + ITEM_HEIGHT / 2;
    const y1 = Math.min(Math.max(y2, parentY + ITEM_HEIGHT / 2), parentY + parent.height - 4);
    const [x1, x2] = [right(parent.layer), left(child.layer)];
    const xm = x2 - LAYER_PAD / 2;
    return [{ key: `${parent.id}-${child.id}`, d: `M ${x1} ${y1} H ${xm} V ${y2} H ${x2}` }];
  });

  /** 画面の半分ずつ前後へスクロールする。スクロールできないときは中心の時刻を送る */
  const page = (direction: number) => {
    const element = scrollRef.current;
    if (element && element.scrollHeight > element.clientHeight)
      element.scrollBy({ top: (direction * box.viewport) / 2, behavior: "smooth" });
    else if (center !== null)
      navigate({ at: formatStamp(fromDayNumber(center + (direction * span) / 2)) });
  };

  const viewingNow = viewing ? (byId.get(viewing.id) ?? viewing) : null;

  return (
    <div className="page-fill timeline-page">
      <PageTitle kind={T.eventTimeline.title} record={at} />
      <div className="toolbar">
        <h1 style={{ margin: 0 }}>{T.eventTimeline.title}</h1>
        <button type="button" onClick={() => page(-1)} disabled={center === null}>
          {T.timeline.earlier}
        </button>
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
        <button type="button" onClick={() => page(1)} disabled={center === null}>
          {T.timeline.later}
        </button>
        <div className="hint timeline-filter">
          {T.timeline.scale}
          <button
            type="button"
            onClick={() => changeView({ years: view.years - 1 })}
            disabled={view.years <= 1}
            title={T.timeline.fewerYears}
          >
            −
          </button>
          <span className="timeline-years">{T.timeline.years(view.years)}</span>
          <button
            type="button"
            onClick={() => changeView({ years: view.years + 1 })}
            title={T.timeline.moreYears}
          >
            +
          </button>
        </div>
        <div className="hint timeline-filter">
          {T.eventTimeline.location}
          <TreeReferenceSelect
            table="location"
            value={locationId}
            nullable
            onChange={filterPlace}
            title={T.eventTimeline.location}
          />
        </div>
        <label className="hint timeline-filter">
          <input
            type="checkbox"
            checked={view.squeeze}
            onChange={(e) => changeView({ squeeze: e.target.checked })}
          />
          {T.timeline.squeeze}
        </label>
        {editing ? (
          <>
            <button
              type="button"
              className="primary"
              disabled={changes.size === 0 || applying}
              onClick={() => void apply()}
            >
              {T.timeline.apply(changes.size)}
            </button>
            <button
              type="button"
              disabled={applying}
              onClick={() => {
                if (changes.size === 0 || window.confirm(T.timeline.confirmDiscard(changes.size)))
                  leaveEditing();
              }}
            >
              {T.timeline.discard}
            </button>
          </>
        ) : (
          <button type="button" onClick={() => setEditing(true)}>
            {T.timeline.edit}
          </button>
        )}
      </div>
      {editing && <div className="status info">{T.eventTimeline.editHint}</div>}
      {error && <div className="status error">{error}</div>}
      {message && !error && <div className="status ok">{message}</div>}
      {!records ? (
        !error && <div className="status info">{T.loading}</div>
      ) : (
        <div
          className={`timeline ${editing ? "editing" : ""}`}
          aria-busy={applying}
          style={{ "--timeline-head": `${box.head}px` } as CSSProperties}
        >
          <div className="timeline-scroll" ref={scrollBoxRef} onScroll={onScroll}>
            <div
              className="timeline-head"
              style={{
                gridTemplateColumns: `var(--timeline-axis) repeat(${columns}, ${LAYER_WIDTH}px)`,
              }}
            >
              <div className="timeline-corner" style={{ gridColumn: 1 }} />
              {Array.from({ length: columns }, (_, layer) => (
                <div key={layer} className="timeline-label" style={{ gridColumn: layer + 2 }}>
                  {T.eventTimeline.layer(layer + 1)}
                </div>
              ))}
            </div>
            <div className="timeline-body">
              <div className="timeline-lines">
                {scale?.gaps.map((g) => (
                  <div key={g.from} className="timeline-gap" style={{ top: g.y, height: GAP_PX }} />
                ))}
                {axisTicks.map((tick) => (
                  <div
                    key={tick.at}
                    className={`timeline-grid ${tick.major ? "major" : ""}`}
                    style={{ top: scale?.toY(tick.at) }}
                  />
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
                {axisTicks.map((tick) => (
                  <div
                    key={tick.at}
                    className={`timeline-tick ${tick.major ? "major" : ""}`}
                    style={{ top: scale?.toY(tick.at) }}
                  >
                    {tick.label}
                  </div>
                ))}
              </div>
              <div
                className="timeline-track event-timeline-track"
                style={{
                  width: columns * LAYER_WIDTH,
                  height: scale?.height,
                  backgroundSize: `${LAYER_WIDTH}px 100%`,
                }}
                onClick={onTrackClick}
              >
                <svg className="event-timeline-links" width={columns * LAYER_WIDTH} height={scale?.height ?? 0}>
                  {links.map((link) => (
                    <path key={link.key} d={link.d} />
                  ))}
                </svg>
                {placed.map((item) => {
                  const offset = offsetOf(item);
                  const isDragged = drag?.item.id === item.id;
                  const className = [
                    "timeline-item",
                    "event-timeline-item",
                    item.end === null ? "point" : "",
                    item.record.hidden === true ? "hidden-event" : "",
                    context.has(item.id) ? "context-event" : "",
                    isDragged ? "dragging" : "",
                    drag?.over === item.id ? "drop-target" : "",
                    changes.has(item.id) ? "changed" : "",
                    applying && changes.has(item.id) ? "saving" : "",
                  ].join(" ");
                  return (
                    <div
                      key={item.key}
                      data-id={item.id}
                      className={className}
                      style={{
                        left: left(item.layer),
                        top: item.y,
                        width: LAYER_WIDTH - 2 * LAYER_PAD,
                        transform: offset ? `translateY(${offset}px)` : undefined,
                        ...(isDragged ? { minHeight: item.height } : { height: item.height }),
                      }}
                      onPointerDown={(e) => onItemDown(e, item)}
                      onPointerMove={onItemMove}
                      onPointerUp={onItemUp}
                      onPointerCancel={() => setDrag(null)}
                      onClick={(e) => e.stopPropagation()}
                      onMouseMove={(e) => !drag && show(e, tooltipLines(item))}
                      onMouseLeave={hide}
                    >
                      {item.barHeight > 0 && (
                        <span className="timeline-bar" style={{ height: item.barHeight }} />
                      )}
                      <span className="timeline-text">
                        {item.label}
                        {isDragged && dragDays !== 0 && (
                          <span className="timeline-target">
                            {" "}→ {String(shifted(item.record, dragDays).time ?? "")}
                          </span>
                        )}
                        {isDragged && drag.over !== null && (
                          <span className="timeline-target">
                            {" "}{T.eventTimeline.becomesChildOf(labelOfEvent(drag.over))}
                          </span>
                        )}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
          {scale && <div className="timeline-center" style={{ top: box.head + box.viewport / 2 }} />}
        </div>
      )}
      {viewingNow && (
        <Modal
          title={viewingNow.label}
          onClose={() => setViewing(null)}
          actions={
            <>
              {editing ? (
                viewingNow.parent !== null && (
                  <button
                    type="button"
                    onClick={() => {
                      reparent(viewingNow, null);
                      setViewing(null);
                    }}
                  >
                    {T.eventTimeline.detach}
                  </button>
                )
              ) : (
                <>
                  <button type="button" className="danger" onClick={() => void remove(viewingNow)}>
                    {T.eventTimeline.delete}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setAdding({
                        start: String(viewingNow.record.start ?? viewingNow.record.time),
                        parent: { id: viewingNow.id, label: viewingNow.label },
                      });
                      setViewing(null);
                    }}
                  >
                    {T.eventTimeline.addChild}
                  </button>
                </>
              )}
              <span className="spacer" />
              <button type="button" onClick={() => setViewing(null)}>
                {T.close}
              </button>
              <button
                type="button"
                className="primary"
                onClick={() => window.open(`/tables/event/${viewingNow.id}`, "_blank", "noopener,noreferrer")}
              >
                {T.timeline.openInNewTab}
              </button>
            </>
          }
        >
          <div className="timeline-sheet">
            {detailLines(viewingNow).filter(Boolean).join("\n")}
          </div>
          <div className="timeline-sheet">
            {viewingText === null ? T.loading : viewingText || T.characterSheet.noText}
          </div>
        </Modal>
      )}
      {adding && (
        <NewEventModal
          start={adding.start}
          parent={adding.parent}
          onClose={() => setAdding(null)}
          onAdded={() => setReloads((n) => n + 1)}
        />
      )}
      <Tooltip tip={tip} />
    </div>
  );
}
