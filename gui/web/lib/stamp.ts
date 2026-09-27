/** "11579/03/02 10:00:00" 形式の Stamp(`db/stamp.py` の `Stamp`)を扱う小さなヘルパー。年は桁数が可変なので、文字列比較ではなく区切りで割って数に直す。 */

type StampParts = { year: number; month: number; day: number; hour: number; minute: number; second: number };

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
