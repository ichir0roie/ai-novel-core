/** "11579/03/02 10:00:00" 形式の Stamp(`db/stamp.py` の `Stamp`)を扱う小さなヘルパー。年は桁数が可変なので、文字列比較ではなく区切りで割って数に直す。
 *
 * 作品が西暦でない暦(`Calendar`)を持つとき、API はその暦の桁で時刻を出し入れする。画面の計算(ピッカー・タイムライン)も
 * 同じ暦で数える。暦の始まり(`offset`)の桁は両方の暦で同じなので、桁の並びの大小はそのまま時の前後になる。 */

import type { components } from "./openapi";

export type StampParts = { year: number; month: number; day: number; hour: number; minute: number; second: number };

export function parseStamp(value: unknown): StampParts | null {
  // 人物の来歴の始まりは年だけの整数
  if (typeof value === "number") value = String(value);
  if (typeof value !== "string" || value.trim() === "") return null;
  const [year, month = 1, day = 1, hour = 0, minute = 0, second = 0] = value
    .trim()
    .split(/[-/ :T]/)
    .filter(Boolean)
    .map(Number);
  if (year === undefined || Number.isNaN(year)) return null;
  return { year, month, day, hour, minute, second };
}

/** 大小比較できる数へ。空は最も古い扱い(始まりが無い=最初から)。 */
export function stampOrder(value: unknown): number {
  const s = parseStamp(value);
  if (!s) return -Infinity;
  return ((((s.year * 100 + s.month) * 100 + s.day) * 100 + s.hour) * 100 + s.minute) * 100 + s.second;
}

/** `born` に生まれた者が `at` の時点で何歳か。`ai/time_keeper/event_progression_generator.py` の `age_at` と同じ数え方(誕生日を迎えていなければ 1 引く)。 */
export function ageAt(born: unknown, at: unknown): number | null {
  const b = parseStamp(born);
  const a = parseStamp(at);
  if (!b || !a) return null;
  const hadBirthday = a.month > b.month || (a.month === b.month && a.day >= b.day);
  return a.year - b.year - (hadBirthday ? 0 : 1);
}

// --- 作品の暦(`db/stamp.py` の `Calendar`) ---------------------------------------------------

/** API が返す暦(`gui/api/models.py` の `CalendarModel`)。offset は西暦の桁 */
export type CalendarModel = components["schemas"]["CalendarModel"];

/** 西暦でない暦。`offset`(西暦の桁)より前は西暦で数え、`offset` から先はこの暦で数える。
 * 秒は地球の秒のままで、一分の秒・一時間の分・一日の時間の数を暦ごとに持つ */
export type Calendar = {
  name: string;
  offset: StampParts;
  monthDays: number[];
  monthNames: string[];
  hoursPerDay: number;
  minutesPerHour: number;
  secondsPerMinute: number;
  daysPerWeek: number;
  // 月ごとの、月の終わりの週に数えない日の数
  outsideWeekDays: number[];
  yearDays: number;
  hourSeconds: number;
  daySeconds: number;
  // 月ごとの、その月より前の日数
  daysBefore: number[];
  // 一年の週に数える日の数と、月ごとの、その月より前の週に数える日の数(`Calendar._week_count`)
  weekYearDays: number;
  weekDaysBefore: number[];
  // 同じ暦かを比べる値(API の暦の JSON)
  key: string;
};

export function calendarOf(model: CalendarModel | null | undefined): Calendar | null {
  const offset = model ? parseStamp(model.offset) : null;
  if (!model || !offset || model.month_days.length === 0) return null;
  const minutesPerHour = model.minutes_per_hour || 60;
  const secondsPerMinute = model.seconds_per_minute || 60;
  // 空の `outside_week_days` は、どの月も 0 日
  const outsideWeekDays = model.month_days.map((_, i) => model.outside_week_days?.[i] ?? 0);
  const daysBefore: number[] = [];
  const weekDaysBefore: number[] = [];
  let yearDays = 0;
  let weekYearDays = 0;
  for (const [i, days] of model.month_days.entries()) {
    daysBefore.push(yearDays);
    weekDaysBefore.push(weekYearDays);
    yearDays += days;
    weekYearDays += days - outsideWeekDays[i];
  }
  const hourSeconds = minutesPerHour * secondsPerMinute;
  return {
    name: model.name,
    offset,
    monthDays: [...model.month_days],
    monthNames: [...(model.month_names ?? [])],
    hoursPerDay: model.hours_per_day,
    minutesPerHour,
    secondsPerMinute,
    daysPerWeek: model.days_per_week,
    outsideWeekDays,
    yearDays,
    hourSeconds,
    daySeconds: model.hours_per_day * hourSeconds,
    daysBefore,
    weekYearDays,
    weekDaysBefore,
    key: JSON.stringify(model),
  };
}

export function sameCalendar(a: Calendar | null, b: Calendar | null): boolean {
  return (a?.key ?? null) === (b?.key ?? null);
}

const DIGIT_KEYS = ["year", "month", "day", "hour", "minute", "second"] as const;

function compareParts(a: StampParts, b: StampParts): number {
  for (const key of DIGIT_KEYS) if (a[key] !== b[key]) return a[key] - b[key];
  return 0;
}

/** 桁の頭(年・年月・年月日)が暦の始まりより前か(西暦で数えるか)。始まりと同じ年・月・日は暦の側に数える */
function beforeOffset(calendar: Calendar, ...prefix: number[]): boolean {
  for (const [i, value] of prefix.entries()) {
    const offset = calendar.offset[DIGIT_KEYS[i]];
    if (value !== offset) return value < offset;
  }
  return false;
}

/** その桁を暦の側で数えるか。暦が無ければ西暦 */
function counted(calendar: Calendar | null, ...prefix: number[]): calendar is Calendar {
  return calendar !== null && !beforeOffset(calendar, ...prefix);
}

// --- ここから、カレンダー形式のポップアップ選択(StampInput)向けの計算 -----------------
// `db/stamp.py` の Stamp と同じ規則(西暦の続きの暦。うるう年以外は月ごとの日数が固定)を
// ここでも小さく再現する。ピッカーの表示にだけ使うので、Stamp.parse ほど厳密な検査はしない。
// 暦があれば、始まりの年・月・日から先はその暦の月の数・日数・一日の時間・一週の日数で数える

const MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
const DAYS_BEFORE_MONTH = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];

export function isLeapYear(year: number): boolean {
  return year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
}

export function monthsInYear(year: number, calendar: Calendar | null = null): number {
  return counted(calendar, year) ? calendar.monthDays.length : 12;
}

export function daysInMonth(year: number, month: number, calendar: Calendar | null = null): number {
  if (counted(calendar, year, month)) return calendar.monthDays[month - 1] ?? 0;
  if (month === 2 && isLeapYear(year)) return 29;
  return MONTH_DAYS[month - 1] ?? 31;
}

export function hoursInDay(year: number, month: number, day: number, calendar: Calendar | null = null): number {
  return counted(calendar, year, month, day) ? calendar.hoursPerDay : 24;
}

export function minutesInHour(year: number, month: number, day: number, calendar: Calendar | null = null): number {
  return counted(calendar, year, month, day) ? calendar.minutesPerHour : 60;
}

export function secondsInMinute(year: number, month: number, day: number, calendar: Calendar | null = null): number {
  return counted(calendar, year, month, day) ? calendar.secondsPerMinute : 60;
}

/** 月のカレンダーの一週の列の数 */
export function daysInWeek(year: number, month: number, calendar: Calendar | null = null): number {
  return counted(calendar, year, month) ? calendar.daysPerWeek : 7;
}

/** 暦の月の呼び名。呼び名の無い月・西暦の月は null */
export function monthName(year: number, month: number, calendar: Calendar | null = null): string | null {
  return counted(calendar, year, month) ? calendar.monthNames[month - 1] || null : null;
}

// その年の1月1日を基準にした通算日数(閏年を跨いだ差分の計算にだけ使う。実世界の暦との対応は無い)
function totalDays(year: number, month: number, day: number): number {
  const daysBeforeYear = 365 * year + Math.floor(year / 4) - Math.floor(year / 100) + Math.floor(year / 400);
  let dayOfYear = DAYS_BEFORE_MONTH[month - 1] + day;
  if (month > 2 && isLeapYear(year)) dayOfYear += 1;
  return daysBeforeYear + dayOfYear;
}

function modulo(n: number, d: number): number {
  return ((n % d) + d) % d;
}

// その月の週に数える日の数(`Calendar._week_days_of`)
function weekDaysOf(calendar: Calendar, month: number): number {
  return (calendar.monthDays[month - 1] ?? 0) - (calendar.outsideWeekDays[month - 1] ?? 0);
}

// その日より前に週に数えた日の数(`Calendar._week_count`)
function weekCount(calendar: Calendar, year: number, month: number, day: number): number {
  return year * calendar.weekYearDays + (calendar.weekDaysBefore[month - 1] ?? calendar.weekYearDays) + Math.min(day - 1, weekDaysOf(calendar, month));
}

/** 週の何日目か(暦の始まりの日を 1 日目とする。`Calendar.weekday`)。週に数えない日・始まりより前・暦が無ければ null */
export function weekday(p: StampParts, calendar: Calendar | null): number | null {
  if (calendar === null || compareParts(p, calendar.offset) < 0 || p.day > weekDaysOf(calendar, p.month)) return null;
  const { year, month, day } = calendar.offset;
  return modulo(weekCount(calendar, p.year, p.month, p.day) - weekCount(calendar, year, month, day), calendar.daysPerWeek) + 1;
}

/** その日が並ぶ曜日の列(0 始まり)。週に数えない日は null。実世界の曜日とは対応しないが、月をまたいでも列がずれないように使う。
 * 暦の月では {@link weekday} と同じ数え方で、暦の始まりの月の、始まりより前の日も同じ並びの続きに置く */
export function weekdayOf(year: number, month: number, day: number, calendar: Calendar | null = null): number | null {
  if (counted(calendar, year, month)) {
    if (day > weekDaysOf(calendar, month)) return null;
    const { offset } = calendar;
    return modulo(weekCount(calendar, year, month, day) - weekCount(calendar, offset.year, offset.month, offset.day), calendar.daysPerWeek);
  }
  return modulo(totalDays(year, month, day), 7);
}

export function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

export function formatStamp(p: StampParts): string {
  return `${p.year}/${pad2(p.month)}/${pad2(p.day)} ${pad2(p.hour)}:${pad2(p.minute)}:${pad2(p.second)}`;
}

/** 日をその月の日数に収める。暦があれば、年・月を変えて月の数・一日の時間が変わったときの月・時も収める */
export function clampDay(p: StampParts, calendar: Calendar | null = null): StampParts {
  if (calendar === null) {
    const max = daysInMonth(p.year, p.month);
    return p.day > max ? { ...p, day: max } : p;
  }
  const month = Math.min(Math.max(1, p.month), monthsInYear(p.year, calendar));
  const day = Math.min(Math.max(1, p.day), daysInMonth(p.year, month, calendar));
  const hour = Math.min(Math.max(0, p.hour), hoursInDay(p.year, month, day, calendar) - 1);
  const minute = Math.min(Math.max(0, p.minute), minutesInHour(p.year, month, day, calendar) - 1);
  const second = Math.min(Math.max(0, p.second), secondsInMinute(p.year, month, day, calendar) - 1);
  return { ...p, month, day, hour, minute, second };
}

// --- ここから、時刻を数直線に置く計算(タイムライン) ------------------------------------
// 西暦は `db/stamp.py` の `plus_days` と同じ通算日(1 年 1 月 1 日が 1)。時・分・秒は日の端数にする。
// 暦があれば、暦の始まりから先は暦の一日(`daySeconds` 秒)を 1 とし、始まりより前は西暦の一日を 1 として、
// 始まりの時刻で繋いだ一本の軸に置く(始まりの前後で一日の長さが違っても、前後は崩れない)

const WESTERN_DAY_SECONDS = 86400;

function daysBeforeYear(year: number): number {
  const y = year - 1;
  return 365 * y + Math.floor(y / 4) - Math.floor(y / 100) + Math.floor(y / 400);
}

function ordinalOf(year: number, month: number, day: number): number {
  return daysBeforeYear(year) + DAYS_BEFORE_MONTH[month - 1] + (month > 2 && isLeapYear(year) ? 1 : 0) + day;
}

function fromOrdinal(ordinal: number): { year: number; month: number; day: number } {
  let year = Math.floor((ordinal * 400) / 146097) + 1;
  while (daysBeforeYear(year) >= ordinal) year -= 1;
  while (daysBeforeYear(year + 1) < ordinal) year += 1;
  let day = ordinal - daysBeforeYear(year);
  let month = 1;
  while (day > daysInMonth(year, month)) {
    day -= daysInMonth(year, month);
    month += 1;
  }
  return { year, month, day };
}

// 一日のうちの秒(`_clock_seconds`)。暦があれば暦の一時間・一分の長さで数える
function clockSeconds(p: StampParts, calendar: Calendar | null = null): number {
  const [hourSeconds, minuteSeconds] = calendar ? [calendar.hourSeconds, calendar.secondsPerMinute] : [3600, 60];
  return p.hour * hourSeconds + p.minute * minuteSeconds + p.second;
}

function clockOf(seconds: number, calendar: Calendar | null = null): { hour: number; minute: number; second: number } {
  const [hourSeconds, minuteSeconds] = calendar ? [calendar.hourSeconds, calendar.secondsPerMinute] : [3600, 60];
  const rest = seconds % hourSeconds;
  return { hour: Math.floor(seconds / hourSeconds), minute: Math.floor(rest / minuteSeconds), second: rest % minuteSeconds };
}

function westernSeconds(p: StampParts): number {
  return (ordinalOf(p.year, p.month, p.day) - 1) * WESTERN_DAY_SECONDS + clockSeconds(p);
}

function westernParts(seconds: number): StampParts {
  const days = Math.floor(seconds / WESTERN_DAY_SECONDS);
  return { ...fromOrdinal(days + 1), ...clockOf(seconds - days * WESTERN_DAY_SECONDS) };
}

// 暦の 0 年の最初の日を 0 とする通算日(`Calendar._day_number`)
function localDayNumber(calendar: Calendar, year: number, month: number, day: number): number {
  return year * calendar.yearDays + (calendar.daysBefore[month - 1] ?? calendar.yearDays) + day - 1;
}

function localSeconds(calendar: Calendar, p: StampParts): number {
  return localDayNumber(calendar, p.year, p.month, p.day) * calendar.daySeconds + clockSeconds(p, calendar);
}

function localParts(calendar: Calendar, seconds: number): StampParts {
  const days = Math.floor(seconds / calendar.daySeconds);
  const year = Math.floor(days / calendar.yearDays);
  let day = days - year * calendar.yearDays;
  let month = 1;
  while (month < calendar.monthDays.length && day >= calendar.monthDays[month - 1]) {
    day -= calendar.monthDays[month - 1];
    month += 1;
  }
  return { year, month, day: day + 1, ...clockOf(seconds - days * calendar.daySeconds, calendar) };
}

/** 暦の桁を西暦の桁に(`Calendar.to_western`)。始まりより前の桁・暦が無いときは、そのまま */
export function toWestern(p: StampParts, calendar: Calendar | null): StampParts {
  if (calendar === null || compareParts(p, calendar.offset) < 0) return p;
  return westernParts(westernSeconds(calendar.offset) + localSeconds(calendar, p) - localSeconds(calendar, calendar.offset));
}

/** 西暦の桁を暦の桁に(`Calendar.to_local`)。始まりより前・暦が無いときは、そのまま */
export function toLocal(western: StampParts, calendar: Calendar | null): StampParts {
  if (calendar === null || compareParts(western, calendar.offset) < 0) return western;
  return localParts(calendar, localSeconds(calendar, calendar.offset) + westernSeconds(western) - westernSeconds(calendar.offset));
}

/** `from` の暦で数えた時刻を、同じ時刻を指す `to` の暦の桁に。空・読めない値はそのまま */
export function convertStamp(value: string | null, from: Calendar | null, to: Calendar | null): string | null {
  const p = parseStamp(value);
  if (!p || sameCalendar(from, to)) return value;
  return formatStamp(toLocal(toWestern(p, from), to));
}

// 軸の上の、暦の始まりの時刻の位置
function offsetDay(calendar: Calendar): number {
  return localSeconds(calendar, calendar.offset) / calendar.daySeconds;
}

/** 通算日に時刻の端数を足した数。差がそのまま日数になる(暦があれば、始まりから先は暦の日数)。 */
export function dayNumber(p: StampParts, calendar: Calendar | null = null): number {
  if (calendar === null) return ordinalOf(p.year, p.month, p.day) + clockSeconds(p) / WESTERN_DAY_SECONDS;
  if (compareParts(p, calendar.offset) < 0)
    return offsetDay(calendar) + (westernSeconds(p) - westernSeconds(calendar.offset)) / WESTERN_DAY_SECONDS;
  return localSeconds(calendar, p) / calendar.daySeconds;
}

/** {@link dayNumber} の逆。秒より細かい端数は丸める。 */
export function fromDayNumber(n: number, calendar: Calendar | null = null): StampParts {
  if (calendar === null) {
    let ordinal = Math.floor(n);
    let seconds = Math.round((n - ordinal) * WESTERN_DAY_SECONDS);
    if (seconds >= WESTERN_DAY_SECONDS) {
      ordinal += 1;
      seconds -= WESTERN_DAY_SECONDS;
    }
    return { ...fromOrdinal(ordinal), ...clockOf(seconds) };
  }
  const start = offsetDay(calendar);
  if (n < start) return westernParts(westernSeconds(calendar.offset) + Math.round((n - start) * WESTERN_DAY_SECONDS));
  return localParts(calendar, Math.round(n * calendar.daySeconds));
}

/** 西暦の時刻を、軸の日(暦の始まりから先は暦の一日、前は西暦の一日)で `days` 日動かす。時・分・秒はそのまま。
 * db の `Stamp.plus_days` は暦に依らず西暦の日で数えるが、画面は暦の日を並べた軸の上で札を動かすので、軸の日で送る */
function plusDays(western: StampParts, days: number, calendar: Calendar): StampParts {
  if (compareParts(western, calendar.offset) < 0)
    return { ...western, ...fromOrdinal(ordinalOf(western.year, western.month, western.day) + days) };
  const local = toLocal(western, calendar);
  const moved = localParts(calendar, (localDayNumber(calendar, local.year, local.month, local.day) + days) * calendar.daySeconds + clockSeconds(local, calendar));
  return westernParts(westernSeconds(calendar.offset) + localSeconds(calendar, moved) - localSeconds(calendar, calendar.offset));
}

/** `days` 日後(負なら前)。整数なら時・分・秒はそのままで、端数があればその分だけ時刻も進める。空なら空のまま。
 * 暦があれば、日は軸の日({@link dayNumber})で数える */
export function shiftDays(value: unknown, days: number, calendar: Calendar | null = null): string | null {
  const p = parseStamp(value);
  if (!p) return null;
  if (!Number.isInteger(days)) return formatStamp(fromDayNumber(dayNumber(p, calendar) + days, calendar));
  if (calendar === null) return formatStamp({ ...p, ...fromOrdinal(ordinalOf(p.year, p.month, p.day) + days) });
  return formatStamp(toLocal(plusDays(toWestern(p, calendar), days, calendar), calendar));
}
