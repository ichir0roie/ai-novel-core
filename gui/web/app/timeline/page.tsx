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
  type PointerEvent,
} from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import Modal from "@/components/Modal";
import NewEpisodeModal from "@/components/NewEpisodeModal";
import ReferenceSelect from "@/components/ReferenceSelect";
import StampInput from "@/components/StampInput";
import Tooltip, { useTooltip } from "@/components/Tooltip";
import {
  getTimeline,
  labelOf,
  listAllRecords,
  updateEpisodes,
  type Labels,
  type Rec,
  type TimelineResponse,
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
  labelWidth,
  savedView,
  scaleOf,
  SCROLL_SETTLE_MS,
  type Gap,
  type Scale,
  type View,
} from "@/lib/timelineAxis";
import { useTreeOpen } from "@/lib/treeOpen";

// 縮尺(画面の高さの年数)と、話の無い区間を詰めるかを覚えておく localStorage のキー
const VIEW_STORAGE_KEY = "timeline-view";
// 作品の列の中の筋(札を並べる縦長の帯)の幅の上限(px)。筋は列の一番長い名前に合わせ、これを超える名前は筋の幅で切れる(全部の名前はかざすと出る)
const LANE_WIDTH = 180;
// 筋の幅の下限(px)。札の無い列・閉じた列はこの細さになる
const MIN_LANE_WIDTH = 10;
// 作品の列の右に空けておく空の筋の数。話を足すときにクリックする所を残す
const STORY_SPARE_LANES = 1;
// 閉じた列で、札の代わりに置く印の高さ(px)
const MARKER_PX = 8;
// 絞り込みの URL の引数と、それを覚えておく localStorage のキー
const FILTER_KEYS = ["story_id"] as const;
const FILTER_STORAGE_KEY = "timeline-filter";

// 軸は日の単位。start・end は日の境目に丸めた通算日で、at は丸める前の時刻(同じ日の中の並び順に使う)
type Item = {
  key: string;
  id: number;
  label: string;
  record: Rec;
  at: number;
  start: number;
  end: number | null;
};
type Placed = Item & {
  y: number;
  height: number;
  barHeight: number;
  lane: number;
};
// 列の木。列は作品で、その話を持つ
type Group = {
  key: string;
  label: string;
  storyId: number | null;
  items: Item[];
  children: Group[];
};
// open は列の札(と子の列)を出しているか。閉じた列は子孫の札もまとめて、名前の無い印で一筋に置く。foldable が false の列は開閉しない。
// span は、この列と、並べた子孫の列の数(見出しがまたぐ列の数)
type Row = {
  key: string;
  label: string;
  storyId: number | null;
  items: Placed[];
  lanes: number;
  laneWidth: number;
  depth: number;
  foldable: boolean;
  open: boolean;
  span: number;
};
type StoryInfo = { name: string; parent: number | null; order: number | null };
// from は掴んだ列、over は落とす先の作品(掴んだ列の上・作品の無い列の上では null)
type Drag = {
  item: Item;
  from: string;
  startX: number;
  startY: number;
  dx: number;
  dy: number;
  over: number | null;
};
// 変更モードで溜めた移し。base は読み込んだときの話で、days はそこから何日ずらすか、story は移す先の作品(移さないなら null)
type Change = { base: Item; days: number; story: number | null };

const byTime = (a: Item, b: Item) =>
  a.start - b.start || a.at - b.at || a.id - b.id;

/**
 * 重ならないよう、上から順に空いている一番左の筋へ置く。同じ日の札は同じ位置なので、時刻の順に横へ並ぶ。
 * 札は名前が一行入る高さまで筋を取るので、札は次の札に重ならない。
 * 閉じた列(`folded`)は、札を名前の無い印にして一筋にまとめる(印は重なってよい)
 */
function pack(
  items: Item[],
  toY: (day: number) => number,
  folded: boolean,
): { placed: Placed[]; lanes: number } {
  const laneEnds: number[] = [];
  const placed = [...items].sort(byTime).map((item) => {
    const y = toY(item.start);
    const barHeight = item.end === null ? 0 : Math.max(0, toY(item.end) - y);
    if (folded)
      return {
        ...item,
        y,
        height: Math.max(barHeight, MARKER_PX),
        barHeight,
        lane: 0,
      };
    const height = Math.max(barHeight, ITEM_HEIGHT);
    let lane = laneEnds.findIndex((end) => end <= y);
    if (lane < 0) lane = laneEnds.length;
    laneEnds[lane] = y + height + ITEM_GAP;
    return { ...item, y, height, barHeight, lane };
  });
  return { placed, lanes: Math.max(1, laneEnds.length) };
}

/** 溜めた移しを当てた話。札はこの時刻・作品の所に描く */
function changedItem({ base, days, story }: Change): Item {
  const record: Rec = {
    ...base.record,
    ...shifted(base, days),
    ...(story !== null ? { story_id: story } : {}),
  };
  return {
    ...base,
    record,
    ...daySpan(dayOf(record.start)!, dayOf(record.end)),
  };
}

/** 保存する欄。動かした分だけを渡す */
function changeForm({ base, days, story }: Change): Rec {
  return {
    id: base.id,
    ...(days !== 0 ? shifted(base, days) : {}),
    ...(story !== null ? { story_id: story } : {}),
  };
}

function itemsOf(data: TimelineResponse): Item[] {
  const items: Item[] = [];
  for (const record of data.items) {
    const start = dayOf(record.start);
    if (start === null) continue;
    items.push({
      key: `episode-${record.id}`,
      id: record.id as number,
      label: T.nameId(record.label, record.id),
      record,
      ...daySpan(start, dayOf(record.end)),
    });
  }
  return items;
}

function saveFilter(
  filter: Record<string, string | number | null | undefined>,
) {
  try {
    localStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify(filter));
  } catch {
    // 覚えられなくても、この画面の中では絞り込みが効く
  }
}

/** 覚えておいた絞り込みのうち、値のあるもの。無ければ null */
function savedFilter(): Record<string, string> | null {
  try {
    const saved = JSON.parse(
      localStorage.getItem(FILTER_STORAGE_KEY) ?? "null",
    );
    const filter: Record<string, string> = {};
    for (const key of FILTER_KEYS)
      if (saved?.[key]) filter[key] = String(saved[key]);
    return Object.keys(filter).length > 0 ? filter : null;
  } catch {
    return null;
  }
}

/** 日付をずらしたときに直す欄。開始・終了を同じ日数だけ動かす。 */
function shifted(item: Item, days: number): Rec {
  const changes: Rec = {};
  for (const key of ["start", "end"])
    if (item.record[key] != null)
      changes[key] = shiftDays(item.record[key], days);
  return changes;
}

/**
 * 作品の木。話の無い作品も段にする(作品で絞ったときは、その作品と子孫の作品)。
 * 段にする作品の祖先の作品も段にする。親が段に無い作品は根に置く。兄弟は、作品一覧と同じく `display_order` の順に並べる。
 * `display_order` の空の作品は後ろに回し、その作品と子孫の作品の一番早い話の順にする(話の無い作品はさらに後ろ)。
 * 読み直しても段が入れ替わらないよう、一番早い話が同じなら作品の id 順にする
 */
function storyGroups(
  episodes: Item[],
  stories: Map<number, StoryInfo>,
  storyId: number | null,
  labels: Labels,
): Group[] {
  const byStory = new Map<number, Item[]>();
  if (storyId !== null) byStory.set(storyId, []);
  for (const id of stories.keys())
    if (storyId === null || descendsFrom(id, storyId, stories))
      byStory.set(id, []);
  for (const item of episodes) {
    const story = item.record.story_id as number;
    byStory.set(story, [...(byStory.get(story) ?? []), item]);
  }
  const shown = new Set<number>();
  for (const id of byStory.keys()) {
    for (
      let at: number | null = id;
      at !== null && !shown.has(at);
      at = stories.get(at)?.parent ?? null
    )
      shown.add(at);
  }
  const firstAt = new Map<number, number>();
  for (const item of episodes) {
    const seen = new Set<number>();
    for (
      let at: number | null = item.record.story_id as number;
      at !== null && !seen.has(at);
      at = stories.get(at)?.parent ?? null
    ) {
      seen.add(at);
      if (item.at < (firstAt.get(at) ?? Infinity)) firstAt.set(at, item.at);
    }
  }
  const firstOf = (id: number) => firstAt.get(id) ?? Infinity;
  const orderOf = (id: number) => stories.get(id)?.order ?? Infinity;
  const byOrder = (a: number, b: number) =>
    orderOf(a) - orderOf(b) || firstOf(a) - firstOf(b) || a - b;
  const childrenOf = new Map<number | null, number[]>();
  for (const id of [...shown].sort(byOrder)) {
    const parent = stories.get(id)?.parent ?? null;
    const key = parent !== null && shown.has(parent) ? parent : null;
    childrenOf.set(key, [...(childrenOf.get(key) ?? []), id]);
  }
  const node = (id: number): Group => {
    const name = stories.get(id)?.name ?? labels.story_id?.[id];
    return {
      key: `story-${id}`,
      label: T.nameId(name, id),
      storyId: id,
      items: byStory.get(id) ?? [],
      children: (childrenOf.get(id) ?? []).map(node),
    };
  };
  // 親を循環してたどる作品は根から届かないので、届かなかった分を根に足す
  const roots = childrenOf.get(null) ?? [];
  const reached = new Set<number>();
  const reach = (id: number) => {
    reached.add(id);
    (childrenOf.get(id) ?? []).forEach(reach);
  };
  roots.forEach(reach);
  return [
    ...roots,
    ...[...shown].filter((id) => !reached.has(id)).sort(byOrder),
  ].map(node);
}

/** 作品 `id` が `ancestor` か、その子孫か。親を循環してたどる作品でも止まる */
function descendsFrom(
  id: number,
  ancestor: number,
  stories: Map<number, StoryInfo>,
): boolean {
  const seen = new Set<number>();
  for (
    let at: number | null = id;
    at !== null && !seen.has(at);
    at = stories.get(at)?.parent ?? null
  ) {
    if (at === ancestor) return true;
    seen.add(at);
  }
  return false;
}

/** 段の木を、開いた段の子だけをたどって並べる。閉じた段には子孫の札をまとめて置く */
function flatten(
  groups: Group[],
  depth: number,
  isOpen: (key: string) => boolean,
  toY: (day: number) => number,
): Row[] {
  const all = (g: Group): Item[] => [...g.items, ...g.children.flatMap(all)];
  return groups.flatMap((g) => {
    const open = isOpen(g.key);
    const { placed, lanes } = pack(open ? g.items : all(g), toY, !open);
    const below = open ? flatten(g.children, depth + 1, isOpen, toY) : [];
    const laneWidth = open
      ? Math.min(
          LANE_WIDTH,
          Math.max(
            MIN_LANE_WIDTH,
            ...g.items.map((item) => labelWidth(item.label)),
          ),
        )
      : MIN_LANE_WIDTH;
    const row: Row = {
      key: g.key,
      label: g.label,
      storyId: g.storyId,
      items: placed,
      lanes,
      laneWidth,
      depth,
      foldable: true,
      open,
      span: 1 + below.length,
    };
    return [row, ...below];
  });
}

/** 中心の時刻を省いて開いたら、最後の話の時刻を中心にする。無ければ 1 年。API は時刻の順に返す */
function defaultCenter(data: TimelineResponse): string {
  const episode = data.items.at(-1)?.start;
  if (episode) return String(episode);
  return formatStamp({
    year: 1,
    month: 1,
    day: 1,
    hour: 0,
    minute: 0,
    second: 0,
  });
}

/** 話の全部が収まる期間(最初の話の始め〜最後の話の終わり)の真ん中。話が無ければ {@link defaultCenter} */
function middleCenter(data: TimelineResponse): string {
  let [lo, hi] = [Infinity, -Infinity];
  for (const record of data.items) {
    const start = dayOf(record.start);
    if (start === null) continue;
    lo = Math.min(lo, start);
    hi = Math.max(hi, dayOf(record.end) ?? start);
  }
  return lo <= hi
    ? formatStamp(fromDayNumber((lo + hi) / 2))
    : defaultCenter(data);
}

export default function TimelinePage() {
  const router = useRouter();
  const search = useSearchParams();
  const at = search.get("at");
  // 作品の画面から飛んできた印(`focus=story`)。話を引いたら、その作品の期間の真ん中を中心にして印を消す
  const focus = search.get("focus");
  const storyId = Number(search.get("story_id")) || null;
  const centerParts = parseStamp(at);
  const center = centerParts ? dayNumber(centerParts) : null;

  const [draft, setDraft] = useState<string | null>(at);
  const [data, setData] = useState<TimelineResponse | null>(null);
  // 段の木を組むための作品の名前と親。話の無い作品も段に出すので、全部の作品を引く
  const [stories, setStories] = useState<Map<number, StoryInfo> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  // スクロールする欄のうち、列の名前の行を除いた見える高さ(viewport)と、列の名前の行の高さ(head)
  const [box, setBox] = useState({ viewport: 0, head: 0 });
  // 期間に必ず含める時刻。入力欄・URL で中心を飛ばした先で、スクロールでは変えない(変えると軸が組み直されて位置が飛ぶ)
  const [anchor, setAnchor] = useState<number | null>(null);
  // 今見ている所が、軸を画面の幅で区切った何番目か。等間隔の軸の目盛りは、全期間に置くと数が増えすぎるので、この前後の区切りにだけ置く
  const [screen, setScreen] = useState(0);
  const [drag, setDrag] = useState<Drag | null>(null);
  // 変更モード。札を動かしても保存せず、話の id ごとに移しを溜めて、適用でまとめて保存する
  const [editing, setEditing] = useState(false);
  const [changes, setChanges] = useState<Map<number, Change>>(new Map());
  const [applying, setApplying] = useState(false);
  // 空いた所を押して足す話の初期値・作品の名前
  // 押した話。吹き出しと同じく読み込んだ話から出し、開くたびに引かない
  const [viewing, setViewing] = useState<Item | null>(null);
  const [adding, setAdding] = useState<{
    initial: Rec;
    storyLabel: string | null;
  } | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const scrollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // スクロールの位置を合わせ済みの中心(at)と軸(scale)。スクロールから URL へ書いた at はここに入れ、位置を合わせ直さない
  const aligned = useRef<{ at: string | null; scale: Scale | null }>({
    at: null,
    scale: null,
  });
  const { isOpen, setOpen } = useTreeOpen("timeline");
  const { tip, show, hide } = useTooltip();
  // 縮尺と詰め方は URL に載せず、このブラウザに覚えておく。サーバで描いた初めの画面と合わせるため、読むのは描いたあと
  const [view, setView] = useState<View>({ years: 1, squeeze: false });
  useEffect(() => setView(savedView(VIEW_STORAGE_KEY)), []);
  const span = view.years * DAYS_PER_YEAR;

  const changeView = (changes: Partial<View>) => {
    const next = { ...view, ...changes };
    setView(next);
    try {
      localStorage.setItem(VIEW_STORAGE_KEY, JSON.stringify(next));
    } catch {
      // 覚えられなくても、この画面の中では縮尺が効く
    }
  };

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

  // 絞り込みを付けずに開いたら(ナビのリンクなど)、前に選んだ絞り込みへ移す。移し終わるまで話を引かない(引いた話から中心を決めると、
  // 移す前の URL に中心を書いて絞り込みを消してしまう)
  const [restoring, setRestoring] = useState(true);
  useEffect(() => {
    if (!restoring) return;
    const target = FILTER_KEYS.some((key) => search.has(key))
      ? null
      : savedFilter();
    if (target) navigate(target);
    else setRestoring(false);
  }, [restoring, search, navigate]);

  /** 絞り込みを変え、次に絞り込みを付けずに開いたときのために覚えておく */
  const filter = (
    changes: Partial<
      Record<(typeof FILTER_KEYS)[number], string | number | null>
    >,
  ) => {
    saveFilter(
      Object.fromEntries(
        FILTER_KEYS.map((key) => [
          key,
          key in changes ? changes[key] : search.get(key),
        ]),
      ),
    );
    navigate(changes);
  };

  useEffect(() => {
    if (!data) return;
    if (focus === "story") {
      // 飛んできた先の絞り込みも、選び直したときと同じく次に開いたときのために覚えておく
      saveFilter({ story_id: storyId });
      navigate({ at: middleCenter(data), focus: null });
    } else if (!at) navigate({ at: defaultCenter(data) });
  }, [at, focus, data, storyId, navigate]);

  // URL の中心が変わったら(スクロールしたときなど)入力欄も合わせる
  const [shownAt, setShownAt] = useState(at);
  if (at !== shownAt) {
    setShownAt(at);
    setDraft(at);
  }

  // 別のタブで話・作品を足して戻ってきたら読み直す。保存・ドラッグの途中は、読み直した話で札が動かないよう待つ
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
    listAllRecords("story")
      .then((records) => {
        if (!alive) return;
        setStories(
          new Map(
            records.map((r) => [
              Number(r.id),
              {
                name: String(r.name ?? r.label ?? ""),
                parent:
                  typeof r.parent_story_id === "number"
                    ? r.parent_story_id
                    : null,
                order:
                  typeof r.display_order === "number" ? r.display_order : null,
              },
            ]),
          ),
        );
      })
      .catch(
        (e) => alive && setError(e instanceof Error ? e.message : String(e)),
      );
    return () => {
      alive = false;
    };
  }, [reloads]);

  useEffect(() => {
    if (restoring) return;
    let alive = true;
    getTimeline({ story_id: storyId })
      .then((result) => {
        if (!alive) return;
        setData(result);
        setError(null);
      })
      .catch(
        (e) => alive && setError(e instanceof Error ? e.message : String(e)),
      );
    return () => {
      alive = false;
    };
  }, [restoring, storyId, reloads]);

  useEffect(() => {
    if (changes.size === 0) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [changes.size]);

  // スクロールする欄。高さを測る
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

  const loaded = useMemo(() => (data ? itemsOf(data) : []), [data]);
  const items = useMemo(
    () =>
      loaded.map((item) => {
        const change = changes.get(item.id);
        return change ? changedItem(change) : item;
      }),
    [loaded, changes],
  );

  const scale = useMemo(
    () => scaleOf(items, anchor, view, box.viewport),
    [anchor, items, view, box.viewport],
  );
  const pxPerDay = scale?.pxPerDay ?? 0;
  const toY = useCallback((day: number) => scale?.toY(day) ?? 0, [scale]);
  const fromY = useCallback((y: number) => scale?.fromY(y) ?? 0, [scale]);

  // 中心を飛ばしたとき・軸が組み直されたとき(縮尺を変えた、保存して読み直した)は、URL の中心が画面の真ん中に来るようスクロールする
  useLayoutEffect(() => {
    if (center === null) return;
    if (at !== aligned.current.at) {
      aligned.current = { at, scale: null };
      // 中心を含む軸に組み直してから合わせる。今の軸の外ならスクロールが端で止まってしまう
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

  // スクロールが止まったときに読む今の値。待つあいだに軸が組み直されることがあるので、スクロールした時の値は使わない
  const latest = useRef({
    scale,
    viewport: box.viewport,
    at,
    center,
    navigate,
  });
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
      // 今の中心がもう真ん中にあれば書かない。詰めた帯の上は 1px で何日も進むので、書き直すと入れた時刻からずれる
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

  const labels = useMemo(() => data?.labels ?? {}, [data]);

  const rows = useMemo(() => {
    if (!stories || !scale) return [];
    const rows = flatten(
      storyGroups(items, stories, storyId, labels),
      0,
      isOpen,
      toY,
    );
    if (rows.length === 0)
      rows.push({
        key: "story-none",
        label: "",
        storyId: null,
        items: [],
        lanes: 1,
        laneWidth: LANE_WIDTH,
        depth: 0,
        foldable: false,
        open: true,
        span: 1,
      });
    return rows;
  }, [stories, scale, items, storyId, labels, isOpen, toY]);

  // 見出しの段の数は列の木で変わるので、列が変わったら見出しの高さを測り直す
  const headDepth = Math.max(0, ...rows.map((r) => r.depth));
  useLayoutEffect(() => {
    const element = scrollRef.current;
    const head =
      element?.querySelector<HTMLElement>(".timeline-head")?.offsetHeight;
    if (element && head !== undefined)
      setBox((b) =>
        b.head === head
          ? b
          : { viewport: Math.max(0, element.clientHeight - head), head },
      );
  }, [headDepth, data, stories]);

  const axisTicks = useMemo(
    () =>
      scale
        ? axisTicksOf(scale, items, view.squeeze, screen, box.viewport)
        : [],
    [scale, items, view.squeeze, screen, box.viewport],
  );

  /** 縦に dy px 動かしたら何日ずれるか。詰めた帯の上では一気に日が進む */
  const daysAt = (item: Item, dy: number) =>
    pxPerDay > 0 ? Math.round(fromY(toY(item.start) + dy) - item.start) : 0;

  const dragDays = (item: Item) =>
    drag?.item.key === item.key && Math.abs(drag.dy) > DRAG_THRESHOLD
      ? daysAt(item, drag.dy)
      : 0;

  const storyLabel = (id: number) =>
    T.nameId(stories?.get(id)?.name ?? labels.story_id?.[id], id);

  /** 移しを溜める。同じ話を何度動かしても、読み込んだときの話からの移しにまとめる。元に戻ったら溜めた分から外す */
  const move = (item: Item, days: number, story: number | null) => {
    const next = new Map(changes);
    const previous = changes.get(item.id);
    const base = previous?.base ?? item;
    const target = story ?? previous?.story ?? null;
    const change = {
      base,
      days: (previous?.days ?? 0) + days,
      story: target === base.record.story_id ? null : target,
    };
    if (change.days === 0 && change.story === null) next.delete(item.id);
    else next.set(item.id, change);
    setChanges(next);
  };

  const leaveEditing = () => {
    setChanges(new Map());
    setEditing(false);
  };

  const apply = async () => {
    setApplying(true);
    setError(null);
    setMessage(null);
    try {
      await updateEpisodes([...changes.values()].map(changeForm));
      // 読み直した話と溜めた分を外すのを同じ描画で替え、札が元の所へ一度戻って見えないようにする
      const result = await getTimeline({ story_id: storyId });
      setData(result);
      setMessage(T.timeline.applied(changes.size));
      leaveEditing();
    } catch (e) {
      setError(
        T.timeline.applyFailed(e instanceof Error ? e.message : String(e)),
      );
    } finally {
      setApplying(false);
    }
  };

  const onItemDown = (
    e: PointerEvent<HTMLDivElement>,
    item: Item,
    row: Row,
  ) => {
    if (e.button !== 0 || applying) return;
    e.stopPropagation();
    e.currentTarget.setPointerCapture(e.pointerId);
    hide();
    setDrag({
      item,
      from: row.key,
      startX: e.clientX,
      startY: e.clientY,
      dx: 0,
      dy: 0,
      over: null,
    });
  };

  /** 指の下の列の作品。札は掴んだ列に留まるので、掴んだ札ではなく位置から列を探す */
  const storyUnder = (
    x: number,
    y: number,
    from: string,
    item: Item,
  ): number | null => {
    const row = document
      .elementsFromPoint(x, y)
      .map((el) => el.closest<HTMLElement>(".timeline-col[data-story]"))
      .find(Boolean);
    const story = Number(row?.dataset.story);
    if (
      !row ||
      row.dataset.key === from ||
      !story ||
      story === item.record.story_id
    )
      return null;
    return story;
  };

  const onItemMove = (e: PointerEvent<HTMLDivElement>) => {
    if (drag && editing)
      setDrag({
        ...drag,
        dx: e.clientX - drag.startX,
        dy: e.clientY - drag.startY,
        over: storyUnder(e.clientX, e.clientY, drag.from, drag.item),
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
    // 変更モードの外では札を動かさない
    if (!editing) return;
    // 列を移すときの手ぶれで時刻が動かないよう、縦にしきい値を超えて動かしたときだけ時刻を送る
    const days = Math.abs(dy) > DRAG_THRESHOLD ? daysAt(item, dy) : 0;
    if (days !== 0 || over !== null) move(item, days, over);
  };

  /** 空いた所を押したら、その日・その列の作品で話を足す(時刻・タイトル・プロットだけならその場で、ほかの欄も書くなら追加ページを別タブに開く) */
  const onTrackClick = (e: MouseEvent<HTMLDivElement>, row: Row) => {
    if (pxPerDay === 0) return;
    const snapped = Math.floor(
      fromY(e.clientY - e.currentTarget.getBoundingClientRect().top),
    );
    const initial: Rec = { start: formatStamp(fromDayNumber(snapped)) };
    const story = row.storyId ?? storyId;
    if (story !== null) initial.story_id = story;
    setAdding({
      initial,
      storyLabel: story === null ? null : storyLabel(story),
    });
  };

  /** 吹き出しと押したときのモーダルに出す、時刻・作品・場所の行 */
  const detailLines = (item: Item) => {
    const r = item.record;
    const base = changes.get(item.id)?.base.record;
    return [
      T.span(r.start, r.end) || String(r.start),
      labelOf(labels, "story_id", r.story_id),
      base &&
        T.timeline.was(
          T.span(base.start, base.end) || String(base.start),
          storyLabel(base.story_id as number),
        ),
      r.location_id != null && labelOf(labels, "location_id", r.location_id),
    ];
  };
  const tooltipLines = (item: Item) => [
    item.label,
    ...detailLines(item),
    String(item.record.preview ?? ""),
  ];

  const gapLines = (g: Gap) => [
    T.timeline.gap,
    `${formatStamp(fromDayNumber(g.from))} – ${formatStamp(fromDayNumber(g.to))}`,
  ];

  /** 列の筋の数。開いた作品の列は、話を足す空の筋を右に一つ空ける */
  const lanesOf = (row: Row) =>
    row.lanes + (row.storyId !== null && row.open ? STORY_SPARE_LANES : 0);

  /** 見出しは作品の木の形に、親の見出しが子の列の上にまたがる。子の無い見出しは、下の段まで縦に伸ばす */
  const renderHead = (row: Row, index: number, all: Row[]) => (
    <div
      key={row.key}
      className={`timeline-label ${row.storyId !== null && drag?.over === row.storyId ? "drop-target" : ""}`}
      title={row.label}
      style={{
        gridColumn: `${index + 2} / span ${row.span}`,
        gridRow: `${row.depth + 1} / span ${row.span > 1 ? 1 : Math.max(...all.map((r) => r.depth)) - row.depth + 1}`,
      }}
    >
      {row.foldable ? (
        <button
          type="button"
          className="timeline-toggle"
          aria-expanded={row.open}
          onClick={() => setOpen(row.key, !row.open)}
        >
          {row.open ? "▾" : "▸"}
        </button>
      ) : (
        <span className="timeline-toggle" />
      )}
      {row.storyId !== null ? (
        <Link
          href={`/tables/story/${row.storyId}`}
          target="_blank"
          rel="noopener noreferrer"
        >
          {row.label}
        </Link>
      ) : (
        row.label
      )}
    </div>
  );

  const renderRow = (row: Row) => (
    <div
      key={row.key}
      className={`timeline-col ${row.storyId !== null && drag?.over === row.storyId ? "drop-target" : ""}`}
      data-key={row.key}
      data-story={row.storyId ?? undefined}
    >
      <div
        className="timeline-track"
        style={{ width: lanesOf(row) * row.laneWidth, height: scale?.height }}
        onClick={(e) => onTrackClick(e, row)}
      >
        {row.items.map((item) => {
          const days = dragDays(item);
          const dragging = drag?.item.key === item.key;
          const className = [
            "timeline-item",
            item.end === null ? "point" : "",
            row.open ? "" : "folded",
            dragging ? "dragging" : "",
            changes.has(item.id) ? "changed" : "",
            applying && changes.has(item.id) ? "saving" : "",
          ].join(" ");
          const target = days !== 0 && shifted(item, days);
          const offset = days ? toY(item.start + days) - item.y : 0;
          return (
            <div
              key={item.key}
              className={className}
              style={{
                left: item.lane * row.laneWidth + 2,
                top: item.y,
                width: row.laneWidth - 4,
                transform: offset ? `translateY(${offset}px)` : undefined,
                ...(dragging
                  ? { minHeight: item.height }
                  : { height: item.height }),
              }}
              onPointerDown={(e) => onItemDown(e, item, row)}
              onPointerMove={onItemMove}
              onPointerUp={onItemUp}
              onPointerCancel={() => setDrag(null)}
              onClick={(e) => e.stopPropagation()}
              onMouseMove={(e) => !drag && show(e, tooltipLines(item))}
              onMouseLeave={hide}
            >
              {item.barHeight > 0 && (
                <span
                  className="timeline-bar"
                  style={{ height: item.barHeight }}
                />
              )}
              <span className="timeline-text">
                {row.open && item.label}
                {target && (
                  <span className="timeline-target">
                    {" "}
                    → {String(target.start)}
                  </span>
                )}
                {dragging && drag.over !== null && (
                  <span className="timeline-target">
                    {" "}
                    → {storyLabel(drag.over)}
                  </span>
                )}
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
    if (element && element.scrollHeight > element.clientHeight)
      element.scrollBy({
        top: (direction * box.viewport) / 2,
        behavior: "smooth",
      });
    else if (center !== null)
      navigate({
        at: formatStamp(fromDayNumber(center + (direction * span) / 2)),
      });
  };

  return (
    <div className="page-fill timeline-page">
      <PageTitle kind={T.timeline.title} record={at} />
      <div className="toolbar">
        <h1 style={{ margin: 0 }}>{T.timeline.title}</h1>
        <button
          type="button"
          onClick={() => shift(-1)}
          disabled={center === null}
        >
          {T.timeline.earlier}
        </button>
        <form
          className="timeline-center-input"
          onSubmit={(e) => {
            e.preventDefault();
            if (parseStamp(draft))
              navigate({ at: formatStamp(parseStamp(draft)!) });
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
        <button
          type="button"
          onClick={() => shift(1)}
          disabled={center === null}
        >
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
        <label className="hint timeline-filter">
          <input
            type="checkbox"
            checked={view.squeeze}
            onChange={(e) => changeView({ squeeze: e.target.checked })}
          />
          {T.timeline.squeeze}
        </label>
        <div className="hint timeline-filter">
          {T.timeline.story}
          <ReferenceSelect
            table="story"
            value={storyId}
            nullable
            onChange={(value) => filter({ story_id: value })}
            title={T.timeline.story}
          />
        </div>
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
                if (
                  changes.size === 0 ||
                  window.confirm(T.timeline.confirmDiscard(changes.size))
                )
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
      {editing && <div className="status info">{T.timeline.editHint}</div>}
      {error && <div className="status error">{error}</div>}
      {message && !error && <div className="status ok">{message}</div>}
      {!data || !stories ? (
        !error && <div className="status info">{T.loading}</div>
      ) : (
        <div
          className={`timeline ${editing ? "editing" : ""}`}
          aria-busy={applying}
          style={{ "--timeline-head": `${box.head}px` } as CSSProperties}
        >
          <div
            className="timeline-scroll"
            ref={scrollBoxRef}
            onScroll={onScroll}
          >
            <div
              className="timeline-head"
              style={{
                gridTemplateColumns: `var(--timeline-axis) ${rows.map((r) => `${lanesOf(r) * r.laneWidth}px`).join(" ")}`,
              }}
            >
              <div
                className="timeline-corner"
                style={{
                  gridColumn: 1,
                  gridRow: `1 / span ${Math.max(...rows.map((r) => r.depth)) + 1}`,
                }}
              />
              {rows.map(renderHead)}
            </div>
            <div className="timeline-body">
              {/* 目盛りの線と詰めた帯は、列ごとに描かず全部の列に一枚で重ねる */}
              <div className="timeline-lines">
                {scale?.gaps.map((g) => (
                  <div
                    key={g.from}
                    className="timeline-gap"
                    style={{ top: g.y, height: GAP_PX }}
                  />
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
              {rows.map(renderRow)}
            </div>
          </div>
          {/* 画面の真ん中の線。スクロールが止まると、ここの時刻が中心(URL の at)になる */}
          {scale && (
            <div
              className="timeline-center"
              style={{ top: box.head + box.viewport / 2 }}
            />
          )}
        </div>
      )}
      {viewing && (
        <Modal
          title={viewing.label}
          onClose={() => setViewing(null)}
          actions={
            <>
              <span className="spacer" />
              <button type="button" onClick={() => setViewing(null)}>
                {T.close}
              </button>
              <button
                type="button"
                className="primary"
                onClick={() =>
                  window.open(
                    `/tables/episode/${viewing.id}`,
                    "_blank",
                    "noopener,noreferrer",
                  )
                }
              >
                {T.timeline.openInNewTab}
              </button>
            </>
          }
        >
          <div className="timeline-sheet">
            {detailLines(viewing).filter(Boolean).join("\n")}
          </div>
          <div className="field section auto">
            <label>plot_text</label>
            <div className="section markdown-preview auto">
              {viewing.record.plot_text ? (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {String(viewing.record.plot_text)}
                </ReactMarkdown>
              ) : (
                <span className="hint">{T.characterSheet.noText}</span>
              )}
            </div>
          </div>
        </Modal>
      )}
      {adding && (
        <NewEpisodeModal
          initial={adding.initial}
          storyLabel={adding.storyLabel}
          onClose={() => setAdding(null)}
          onAdded={() => setReloads((n) => n + 1)}
        />
      )}
      <Tooltip tip={tip} />
    </div>
  );
}
