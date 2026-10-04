"use client";

import type { RecordList, TableMeta } from "@/lib/api";
import { Spec } from "./Hint";
import { columnHint } from "@/lib/hint";
import { cellText, listColumns, NO_PREVIEW } from "@/lib/listColumns";
import { T } from "@/lib/text";

export type SortOrder = "asc" | "desc";

type ClickLike = { ctrlKey: boolean; metaKey: boolean };

type Selection = {
  selected: Set<number>;
  onToggle: (id: number) => void;
  onToggleAll: () => void;
};

type Props = {
  meta: TableMeta;
  data: RecordList | null;
  sort: string;
  order: SortOrder;
  onSort: (key: string) => void;
  /** 行(選べる一覧では名前の文字)を開く。Enter で開くときは e が無い */
  onOpen: (id: string, e?: ClickLike) => void;
  /** 参照列のセルを押したとき、その値で絞り込む。渡さなければ参照列もただの文字 */
  onFilter?: (key: string, value: string) => void;
  /** 渡すと行を選べる一覧にする(行のクリックは選ぶだけ) */
  selection?: Selection;
};

/** 見出しをクリックした列で並べるときの次の並び。同じ列なら向きを返し、別の列なら昇順から(既定の列は既定の向きから) */
export function nextSort(meta: TableMeta, sort: string, order: SortOrder, key: string): { sort: string; order: SortOrder } {
  if (key === sort) return { sort: key, order: order === "asc" ? "desc" : "asc" };
  return { sort: key, order: key === meta.sort ? meta.order : "asc" };
}

/** 一覧の表(id・名前・`listColumns` の列・本文のプレビュー)。 */
export default function ListTable({ meta, data, sort, order, onSort, onOpen, onFilter, selection }: Props) {
  const table = meta.name;
  const columns = listColumns(meta);
  const pageIds = (data?.items ?? []).map((item) => Number(item.id));
  const allSelected = pageIds.length > 0 && pageIds.every((id) => selection?.selected.has(id));

  const sortHeader = (key: string, label: string) => {
    const column = meta.columns.find((c) => c.key === key);
    return (
    <th key={key} className={`sortable ${key === sort ? "sorted" : ""}`} onClick={() => onSort(key)}>
      {column ? <Spec hint={columnHint(column)}>{label}</Spec> : label}
      {key === sort ? (order === "asc" ? " ↑" : " ↓") : ""}
    </th>
    );
  };

  return (
    <div className="scroll-x">
      <table className="list">
        <thead>
          <tr>
            {sortHeader("id", "id")}
            {meta.label_column ? sortHeader(meta.label_column, T.list.name) : <th>{T.list.name}</th>}
            {columns.map((c) => sortHeader(c.key, c.key))}
            {!NO_PREVIEW.has(table) && <th>{T.list.text}</th>}
            {selection && (
              <th className="check">
                <input type="checkbox" title={T.list.selectAll} checked={allSelected} onChange={selection.onToggleAll} />
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {data?.items.map((item) => (
            <tr
              key={String(item.id)}
              className={selection?.selected.has(Number(item.id)) ? "row selected" : "row"}
              tabIndex={0}
              // まとめて消せる一覧では、行のクリックは選ぶだけにして、詳細へは名前の文字から飛ぶ
              onClick={(e) => (selection ? selection.onToggle(Number(item.id)) : onOpen(String(item.id), e))}
              onKeyDown={(e) => {
                if (e.key === "Enter") onOpen(String(item.id));
              }}
            >
              <td>{String(item.id)}</td>
              <td className="name">
                {selection ? (
                  <span
                    className="open"
                    onClick={(e) => {
                      e.stopPropagation();
                      onOpen(String(item.id), e);
                    }}
                  >
                    {String(item.label ?? "")}
                  </span>
                ) : (
                  String(item.label ?? "")
                )}
              </td>
              {columns.map((c) => (
                <td key={c.key}>
                  {onFilter && c.references && item[c.key] != null ? (
                    // 参照列は、その値で一覧を絞り込む(作品の欄なら、その作品の話だけを並べる)
                    <span
                      className="ref"
                      title={T.list.filterBy(c.key)}
                      onClick={(e) => {
                        e.stopPropagation();
                        onFilter(c.key, String(item[c.key]));
                      }}
                    >
                      {cellText(c, item, data.labels)}
                    </span>
                  ) : (
                    cellText(c, item, data.labels)
                  )}
                </td>
              ))}
              {!NO_PREVIEW.has(table) && <td className="preview">{String(item.preview ?? "")}</td>}
              {selection && (
                <td className="check">
                  <input
                    type="checkbox"
                    title={T.list.select}
                    checked={selection.selected.has(Number(item.id))}
                    // 行のクリックでも切り替わるので、二度切り替わらないよう止める
                    onClick={(e) => e.stopPropagation()}
                    onChange={() => selection.onToggle(Number(item.id))}
                  />
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Pager({ offset, size, total, onOffset }: { offset: number; size: number; total: number; onOffset: (offset: number) => void }) {
  return (
    <div className="pager">
      <button disabled={offset <= 0} onClick={() => onOffset(Math.max(0, offset - size))}>
        {T.list.prev}
      </button>
      <span>{T.list.range(total === 0 ? 0 : offset + 1, Math.min(offset + size, total), total)}</span>
      <button disabled={offset + size >= total} onClick={() => onOffset(offset + size)}>
        {T.list.next}
      </button>
    </div>
  );
}
