/** "11579/03/02 10:00:00" 形式の Stamp(`db/stamp.py` の `Stamp`)を扱う小さなヘルパー。年は桁数が可変なので、文字列比較ではなく区切りで割って数に直す。 */

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

/** `born` に生まれた者が `year` 年のうちに迎える歳。人物の来歴の始まりは年だけなので、誕生日の前後は見ない。生まれる前の年は null。 */
export function ageInYear(born: unknown, year: unknown): number | null {
  const b = parseStamp(born);
  const y = parseStamp(year);
  if (!b || !y || y.year < b.year) return null;
  return y.year - b.year;
}

// --- ここから、カレンダー形式のポップアップ選択(StampInput)向けの計算 -----------------
// `db/stamp.py` の Stamp と同じ規則(西暦の続きの暦。うるう年以外は月ごとの日数が固定)を
// ここでも小さく再現する。ピッカーの表示にだけ使うので、Stamp.parse ほど厳密な検査はしない。

const MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
const DAYS_BEFORE_MONTH = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];

export function isLeapYear(year: number): boolean {
  return year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
}

export function daysInMonth(year: number, month: number): number {
  if (month === 2 && isLeapYear(year)) return 29;
  return MONTH_DAYS[month - 1] ?? 31;
}

// その年の1月1日を基準にした通算日数(閏年を跨いだ差分の計算にだけ使う。実世界の暦との対応は無い)
function totalDays(year: number, month: number, day: number): number {
  const daysBeforeYear = 365 * year + Math.floor(year / 4) - Math.floor(year / 100) + Math.floor(year / 400);
  let dayOfYear = DAYS_BEFORE_MONTH[month - 1] + day;
  if (month > 2 && isLeapYear(year)) dayOfYear += 1;
  return daysBeforeYear + dayOfYear;
}

/** 1日が並ぶ曜日の列(0〜6)。実世界の曜日とは対応しないが、月をまたいでも列がずれないように使う。 */
export function weekdayOf(year: number, month: number, day: number): number {
  const total = totalDays(year, month, day);
  return ((total % 7) + 7) % 7;
}

export function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

export function formatStamp(p: StampParts): string {
  return `${p.year}/${pad2(p.month)}/${pad2(p.day)} ${pad2(p.hour)}:${pad2(p.minute)}:${pad2(p.second)}`;
}

export function clampDay(p: StampParts): StampParts {
  const max = daysInMonth(p.year, p.month);
  return p.day > max ? { ...p, day: max } : p;
}

// --- ここから、時刻を数直線に置く計算(タイムライン) ------------------------------------
// `db/stamp.py` の `plus_days` と同じ通算日(1 年 1 月 1 日が 1)。時・分・秒は日の端数にする

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

/** 通算日に時刻の端数を足した数。差がそのまま日数になる。 */
export function dayNumber(p: StampParts): number {
  return ordinalOf(p.year, p.month, p.day) + (p.hour * 3600 + p.minute * 60 + p.second) / 86400;
}

/** {@link dayNumber} の逆。秒より細かい端数は丸める。 */
export function fromDayNumber(n: number): StampParts {
  let ordinal = Math.floor(n);
  let seconds = Math.round((n - ordinal) * 86400);
  if (seconds >= 86400) {
    ordinal += 1;
    seconds -= 86400;
  }
  return { ...fromOrdinal(ordinal), hour: Math.floor(seconds / 3600), minute: Math.floor(seconds / 60) % 60, second: seconds % 60 };
}

/** `days` 日後(負なら前)。時・分・秒はそのまま。空なら空のまま。 */
export function shiftDays(value: unknown, days: number): string | null {
  const p = parseStamp(value);
  if (!p) return null;
  return formatStamp({ ...p, ...fromOrdinal(ordinalOf(p.year, p.month, p.day) + days) });
}
