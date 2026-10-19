// 話のタイムライン(/timeline)と出来事のタイムライン(/event_timeline)が共有する、時刻の縦の軸
import {
  dayNumber,
  daysInMonth,
  fromDayNumber,
  pad2,
  parseStamp,
} from "@/lib/stamp";

// 画面の高さに見せる期間(縮尺)。全期間はこの縮尺で縦に並べ、スクロールで見て回る
const DAYS_PER_YEAR = 365.2425;
// 年より細かい縮尺の段。年からは 1 年ずつ広げる
const FINE_ZOOMS: Zoom[] = [
  { unit: "day", count: 1 },
  { unit: "month", count: 1 },
  { unit: "month", count: 3 },
  { unit: "month", count: 6 },
];
// 札の最低の高さ(px)。名前が一行入る
export const ITEM_HEIGHT = 22;
export const ITEM_GAP = 4;
// スクロールが止まってから中心の時刻を URL に書くまでの間(ms)
export const SCROLL_SETTLE_MS = 200;
// ドラッグとクリックを分けるしきい値(px)
export const DRAG_THRESHOLD = 4;
// 札の無い区間を詰めた帯の高さ(px)。これより広く空く区間だけ詰める
export const GAP_PX = 40;
const MIN_GAP_PX = 2 * GAP_PX;
// 札の前後に空けておく余白(px)。札のすぐ脇から帯にならないようにする
const OCCUPY_MARGIN_PX = 24;
// 帯の直前・帯の上端の目盛りは、文字が帯に掛かるので文字を出さない
const TICK_LABEL_PX = 24;
// 目盛りの文字の高さ(px)
const TICK_TEXT_PX = 20;
// 等間隔の軸で、年の目盛りの間・月の目盛りの間・日と時の目盛りの間に取る最小の高さ(px)
const YEAR_TICK_PX = 28;
const MONTH_TICK_PX = 20;
const FINE_TICK_PX = 24;
// 日・時の目盛りの刻み。日の刻みは月の始めから数える
const DAY_STEPS = [1, 2, 5, 10];
const HOUR_STEPS = [1, 2, 3, 6, 12];
export const FULL_STAMP = /^\d+\/\d{2}\/\d{2} \d{2}:\d{2}:\d{2}$/;

// 軸に置く札の期間。start・end は時刻の端数を含む通算日
export type Span = { start: number; end: number | null };
export type Tick = { at: number; label: string; major: boolean };
export type Gap = { from: number; to: number; y: number };
// since〜until が軸の全体で、height はその縦の長さ(px)
export type Scale = {
  since: number;
  until: number;
  height: number;
  pxPerDay: number;
  gaps: Gap[];
  toY: (day: number) => number;
  fromY: (y: number) => number;
};
// 画面の高さに見せる期間。count 個の unit
export type Zoom = { unit: "day" | "month" | "year"; count: number };
// squeeze は札の無い広い区間を帯に詰めるか
export type View = Zoom & { squeeze: boolean };

/** 縮尺の段の番号。年より細かい段の後ろに、1 年・2 年…と続く。段に無い縮尺は null */
function zoomLevel({ unit, count }: Zoom): number | null {
  if (unit === "year")
    return Number.isInteger(count) && count >= 1
      ? FINE_ZOOMS.length + count - 1
      : null;
  const level = FINE_ZOOMS.findIndex(
    (z) => z.unit === unit && z.count === count,
  );
  return level < 0 ? null : level;
}

/** 縮尺を一段細かく(-1)・粗く(+1)した見方。一番細かい段より細かくはできないので null */
export function zoomed(view: View, direction: -1 | 1): View | null {
  const level = (zoomLevel(view) ?? FINE_ZOOMS.length) + direction;
  if (level < 0) return null;
  const zoom: Zoom = FINE_ZOOMS[level] ?? {
    unit: "year",
    count: level - FINE_ZOOMS.length + 1,
  };
  return { ...view, ...zoom };
}

/** 画面の高さに見せる日数。月は 1 年の 12 分の 1 にならす */
export function spanDays({ unit, count }: Zoom): number {
  if (unit === "day") return count;
  return (count * DAYS_PER_YEAR) / (unit === "month" ? 12 : 1);
}

export function dayOf(value: unknown): number | null {
  const parts = parseStamp(value);
  return parts ? dayNumber(parts) : null;
}

/** 開始〜終了の期間。終了が開始より前なら開始の一点まで縮める */
export function timeSpan(start: number, end: number | null): Span {
  return { start, end: end === null ? null : Math.max(start, end) };
}

/**
 * 等間隔の軸の目盛りの細かさ。年の刻み、月の境目を置くか、日・時の刻み(置かないなら undefined)と、
 * 置く一番細かい目盛り(finest。0 年・1 月・2 日・3 時)
 */
function levelsOf(pxPerDay: number) {
  const pxPerYear = pxPerDay * DAYS_PER_YEAR;
  let yearStep = 1;
  for (let k = 1; yearStep * pxPerYear < YEAR_TICK_PX; k++)
    yearStep = [1, 2, 5][k % 3] * 10 ** Math.floor(k / 3);
  const months = pxPerYear / 12 >= MONTH_TICK_PX;
  const dayStep = months
    ? DAY_STEPS.find((step) => step * pxPerDay >= FINE_TICK_PX)
    : undefined;
  const hourStep =
    dayStep === 1
      ? HOUR_STEPS.find((step) => (step * pxPerDay) / 24 >= FINE_TICK_PX)
      : undefined;
  const finest = hourStep ? 3 : dayStep ? 2 : months ? 1 : 0;
  return { yearStep, months, dayStep, hourStep, finest };
}

/** 押した所の時刻を目盛りの細かさに丸める。時の目盛りを置く縮尺では時に、それより粗ければ日に丸める */
export function snapDay(day: number, pxPerDay: number): number {
  return levelsOf(pxPerDay).hourStep
    ? Math.floor(day * 24) / 24
    : Math.floor(day);
}

/** 札の名前の幅。枠と余白に 22px、全角は 14px、半角は 8px ほどで見積もる */
export function labelWidth(label: string): number {
  let width = 22;
  for (const c of label) width += c.charCodeAt(0) > 0xff ? 14 : 8;
  return width;
}

/**
 * 縮尺 `pxPerDay` で札が占めない区間(日の単位)。札は少なくともその日いっぱいを占め、札の高さは px なので縮尺が上がるほど占める日数は減る。
 * 期間の帯は頭(名前の札)と終わりの日だけを占めるとみなす。何年も続く帯が間を全部埋めると、全期間の軸がどこも詰められず長くなりすぎる
 */
function emptiesAt(
  since: number,
  until: number,
  pxPerDay: number,
  items: Span[],
): { from: number; to: number }[] {
  const margin = OCCUPY_MARGIN_PX / pxPerDay;
  const occupied = items
    .flatMap((item) => {
      const head = Math.max(
        item.start + 1,
        item.start + ITEM_HEIGHT / pxPerDay,
      );
      return item.end === null || item.end <= head
        ? [[item.start, Math.max(head, item.end ?? head)]]
        : [
            [item.start, head],
            [item.end - 1, item.end],
          ];
    })
    .map(([from, to]) => [
      Math.max(since, from - margin),
      Math.min(until, to + margin),
    ])
    .filter(([from, to]) => from < to)
    .sort((a, b) => a[0] - b[0]);
  const empties: { from: number; to: number }[] = [];
  let cursor = since;
  const push = (from: number, to: number) => {
    const [a, b] = [
      Math.max(since, Math.ceil(from)),
      Math.min(until, Math.floor(to)),
    ];
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
 * 時刻と縦の位置の対応。縮尺は `pxPerDay` に決めておく。`squeeze` なら、lo〜hi の中で札の無い広い区間だけを幅 {@link GAP_PX} の帯に詰める。
 * lo〜hi の外(前後の余白)は詰めない。画面の高さより短ければ、後ろへ延ばして画面を埋める。
 */
function compress(
  since: number,
  until: number,
  lo: number,
  hi: number,
  pxPerDay: number,
  viewport: number,
  items: Span[],
  squeeze: boolean,
): Scale {
  const empties = squeeze
    ? emptiesAt(lo, hi, pxPerDay, items).filter(
        (g) => (g.to - g.from) * pxPerDay > MIN_GAP_PX,
      )
    : [];
  const gaps: Gap[] = [];
  const knots: [number, number][] = [[since, 0]];
  let y = 0;
  let day = since;
  for (const g of empties) {
    y += (g.from - day) * pxPerDay;
    gaps.push({ ...g, y });
    knots.push([g.from, y]);
    y += GAP_PX;
    knots.push([g.to, y]);
    day = g.to;
  }
  let height = y + (until - day) * pxPerDay;
  if (height < viewport) {
    until += (viewport - height) / pxPerDay;
    height = viewport;
  }
  knots.push([until, height]);

  // knots の from 列の値を to 列へ。端より外は詰めない縮尺で延ばす
  const along = (value: number, from: 0 | 1): number => {
    const to = 1 - from;
    const outside = from === 0 ? pxPerDay : 1 / pxPerDay;
    const first = knots[0];
    const last = knots[knots.length - 1];
    if (value <= first[from])
      return first[to] + (value - first[from]) * outside;
    if (value >= last[from]) return last[to] + (value - last[from]) * outside;
    const i = knots.findIndex((k) => k[from] > value);
    const [a, b] = [knots[i - 1], knots[i]];
    return a[to] + ((value - a[from]) * (b[to] - a[to])) / (b[from] - a[from]);
  };
  return {
    since,
    until,
    height,
    pxPerDay,
    gaps,
    toY: (d) => along(d, 0),
    fromY: (px) => along(px, 1),
  };
}

/**
 * 全部の札(と飛ばした先の中心 `anchor`)を含む軸。前後に画面の半分ずつ余白を取り、端の札も画面の中ほどまで持ってこられる。
 * 画面の高さが測れていない・札も中心も無ければ null
 */
export function scaleOf(
  items: Span[],
  anchor: number | null,
  view: View,
  viewport: number,
): Scale | null {
  const span = spanDays(view);
  let lo = anchor ?? Infinity;
  let hi = anchor ?? -Infinity;
  for (const item of items) {
    lo = Math.min(lo, item.start);
    hi = Math.max(hi, item.end ?? item.start + 1);
  }
  if (viewport === 0 || lo > hi) return null;
  return compress(
    Math.floor(lo - span / 2),
    Math.ceil(hi + span / 2),
    lo,
    hi,
    viewport / span,
    viewport,
    items,
    view.squeeze,
  );
}

/**
 * 札の開始ごとの目盛り。開始は {@link snapDay} で丸める。文字は縮尺に合わせて年・年/月・月/日にし、文字が変わる所を太くする
 */
function startTicks(items: Span[], pxPerDay: number): Tick[] {
  const { finest } = levelsOf(pxPerDay);
  let previous: string | null = null;
  return [...new Set(items.map((item) => snapDay(item.start, pxPerDay)))]
    .sort((a, b) => a - b)
    .map((at) => {
      const { year, month, day } = fromDayNumber(at);
      const label =
        finest === 3
          ? `${pad2(month)}/${pad2(day)}`
          : finest === 2
            ? `${year}/${pad2(month)}`
            : String(year);
      const major = label !== previous;
      previous = label;
      return { at, label, major };
    });
}

/**
 * 等間隔の軸の、from〜to の目盛り。年の境目を、間が {@link YEAR_TICK_PX} より広くなる刻み(1・2・5 の 10 のべき倍の年)で置き、
 * 1 年が広ければ月の境目、1 月が広ければ日、1 日が広ければ時の目盛りも置く。
 * 一番細かい目盛りより粗い目盛りは太くし、文字に上の位を添える(日を置くなら月は「年/月」、時を置くなら日は「月/日」)
 */
function calendarTicks(scale: Scale, from: number, to: number): Tick[] {
  const { yearStep, months, dayStep, hourStep, finest } = levelsOf(
    scale.pxPerDay,
  );
  const [lo, hi] = [Math.max(from, scale.since), Math.min(to, scale.until)];
  const [first, last] = [fromDayNumber(lo).year, fromDayNumber(hi).year];
  const start = (year: number, month: number) =>
    dayNumber({ year, month, day: 1, hour: 0, minute: 0, second: 0 });
  const ticks: Tick[] = [];
  // level は目盛りの位(0 年・1 月・2 日・3 時)
  const push = (at: number, level: number, label: string) => {
    if (at >= lo && at <= hi)
      ticks.push({ at, label, major: level === 0 || level < finest });
  };
  for (
    let year = Math.ceil(first / yearStep) * yearStep;
    year <= last;
    year += yearStep
  )
    push(start(year, 1), 0, String(year));
  if (months)
    for (let year = first; year <= last; year++)
      for (let month = 2; month <= 12; month++)
        push(
          start(year, month),
          1,
          finest === 1
            ? pad2(month)
            : finest === 2
              ? `${year}/${pad2(month)}`
              : `${pad2(month)}/01`,
        );
  if (dayStep)
    for (let at = Math.floor(lo); at <= hi; at++) {
      const { year, month, day } = fromDayNumber(at);
      // 月の終わりの刻みは、次の月の始めに近すぎれば置かない
      if (
        day > 1 &&
        (day - 1) % dayStep === 0 &&
        day - 1 + dayStep / 2 <= daysInMonth(year, month)
      )
        push(at, 2, hourStep ? `${pad2(month)}/${pad2(day)}` : pad2(day));
      if (hourStep)
        for (let hour = hourStep; hour < 24; hour += hourStep)
          push(at + hour / 24, 3, `${pad2(hour)}:00`);
    }
  return ticks.sort((a, b) => a.at - b.at);
}

/**
 * 軸の目盛り。詰めた軸は、札の開始に目盛りを置く(暦の境目は帯に飲まれる)。等間隔の軸は、暦の境目に置く。
 * 等間隔の軸の目盛りは、全期間に置くと数が増えすぎるので、今見ている画面(軸を画面の高さで区切った `screen` 番目)の前後にだけ置く。
 * 詰めた軸の文字は、まだ出していなければ出す。前の文字・詰めた帯に掛かるときは、同じ文字の次の目盛りに回す
 */
export function axisTicksOf(
  scale: Scale,
  items: Span[],
  squeeze: boolean,
  screen: number,
  viewport: number,
): Tick[] {
  let labelEnd = -Infinity;
  let shownLabel: string | null = null;
  const ticks = squeeze
    ? startTicks(items, scale.pxPerDay)
    : calendarTicks(
        scale,
        scale.fromY((screen - 1) * viewport),
        scale.fromY((screen + 2) * viewport),
      );
  return ticks.map((tick) => {
    const y = scale.toY(tick.at);
    if (
      (squeeze && tick.label === shownLabel) ||
      y < labelEnd ||
      scale.gaps.some((g) => y > g.y - TICK_LABEL_PX && y < g.y + GAP_PX)
    ) {
      return { ...tick, label: "" };
    }
    shownLabel = tick.label;
    labelEnd = y + TICK_TEXT_PX;
    return tick;
  });
}

export const DEFAULT_VIEW: View = { unit: "year", count: 1, squeeze: false };

/**
 * 覚えておいた縮尺と詰め方。年数だけを覚えていた前のバージョンの値(`years`)は年の縮尺として読む。
 * 無い・読めない・段に無い縮尺は既定(1 年)にする
 */
export function savedView(key: string): View {
  try {
    const saved = JSON.parse(localStorage.getItem(key) ?? "null");
    const zoom: Zoom =
      saved?.years !== undefined
        ? { unit: "year", count: Number(saved.years) }
        : { unit: saved?.unit, count: Number(saved?.count) };
    return {
      ...(zoomLevel(zoom) === null ? DEFAULT_VIEW : zoom),
      squeeze: saved?.squeeze === true,
    };
  } catch {
    return DEFAULT_VIEW;
  }
}
