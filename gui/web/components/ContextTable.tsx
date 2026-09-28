import type { Labels, Rec } from "@/lib/api";
import { cellText, listColumns, NO_PREVIEW } from "@/lib/listColumns";
import { useTable } from "@/lib/meta";
import { openInNewTab } from "@/lib/nav";
import { T } from "@/lib/text";

/** 他のテーブルの行を、一覧画面と同じ列組み立てで表に出す(エピソード画面の関連の中身など)。 */
export default function ContextTable({ table, items, labels }: { table: string; items: Rec[]; labels: Labels }) {
  const meta = useTable(table);
  if (!meta) return <div className="status info">{T.loading}</div>;
  const columns = listColumns(meta);
  return (
    <table className="list">
      <thead>
        <tr>
          <th>id</th>
          <th>{T.list.name}</th>
          {columns.map((c) => (
            <th key={c.key}>{c.label}</th>
          ))}
          {!NO_PREVIEW.has(table) && <th>{T.list.text}</th>}
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr
            key={String(item.id)}
            className="row"
            tabIndex={0}
            onClick={() => openInNewTab(`/tables/${table}/${item.id}`)}
            onKeyDown={(e) => {
              if (e.key === "Enter") openInNewTab(`/tables/${table}/${item.id}`);
            }}
          >
            <td>{String(item.id)}</td>
            <td className="name">{String(item.label ?? "")}</td>
            {columns.map((c) => (
              <td key={c.key}>{cellText(c, item, labels)}</td>
            ))}
            {!NO_PREVIEW.has(table) && <td className="preview">{String(item.preview ?? "")}</td>}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
