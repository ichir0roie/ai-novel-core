/** "11579/03/02 10:00:00" 形式の Stamp(`db/stamp.py` の `Stamp`)を扱う小さなヘルパー。年は桁数が可変なので、文字列比較ではなく区切りで割って数に直す。 */

export type StampParts = { year: number; month: number; day: number; hour: number; minute: number; second: number };

export function parseStamp(value: unknown): StampParts | null {
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
