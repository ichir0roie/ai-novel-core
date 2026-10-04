import type { ChildListMeta, ColumnMeta } from "./api";

/** 列にかざしたときの仕様。1 行目に列名と型(参照なら指す先のテーブル)、2 行目に `db/schema.py` の comment。 */
export function columnHint(column: ColumnMeta): string {
  const kind = column.references ? `→ ${column.references}${column.type === "id_list" ? "[]" : ""}` : column.type;
  return [`${column.key} (${kind})`, column.comment].filter(Boolean).join("\n");
}

/** 子の一覧にかざしたときの仕様。1 行目に名前と子の行のテーブル、2 行目に `db/schema.py` の relationship の doc。 */
export function childListHint(meta: ChildListMeta): string {
  return [`${meta.name} (→ ${meta.table}[])`, meta.comment].filter(Boolean).join("\n");
}

/** 複数の列をまとめて一つの項目に出すとき(期間の start ~ end など)の仕様。 */
export function columnsHint(columns: (ColumnMeta | undefined)[]): string {
  return columns.filter((column): column is ColumnMeta => column !== undefined).map(columnHint).join("\n\n");
}
