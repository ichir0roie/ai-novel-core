import { labelOf } from "./api";
import type { ColumnMeta, Labels, Rec, TableMeta } from "./api";

// 一覧のテーブルには出さない列(id は別で出す。他は座標・フラグなど見ても意味が薄い)
const HIDDEN = new Set(["id", "meme_seeded", "event_seeded", "polygon"]);
// 話の一覧は作品の詳細から開く前提なので、作品の列は出さない
const HIDDEN_BY_TABLE: Record<string, string[]> = { episode: ["story_id"] };
// 本文のプレビュー列を出さないテーブル
export const NO_PREVIEW = new Set(["episode"]);

export function listColumns(meta: TableMeta): ColumnMeta[] {
  const hidden = new Set([...HIDDEN, ...(HIDDEN_BY_TABLE[meta.name] ?? [])]);
  return meta.columns
    .filter((c) => !c.section && !hidden.has(c.key) && c.type !== "id_list" && !c.create_only && c.key !== meta.label_column)
    .slice(0, 7);
}

export function cellText(column: ColumnMeta, item: Rec, labels: Labels | undefined): string {
  const value = item[column.key];
  if (value == null) return "";
  if (column.references) return labelOf(labels, column.key, value);
  if (column.type === "boolean") return value ? "✓" : "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
