import type { Labels, Rec } from "@/lib/api";
import { Spec } from "./Hint";
import { columnHint } from "@/lib/hint";
import { cellText, listColumns, NO_PREVIEW } from "@/lib/listColumns";
import { useTable } from "@/lib/meta";
import { useOpenPage } from "@/lib/nav";
import { T } from "@/lib/text";

/** 他のテーブルの行を、一覧画面と同じ列組み立てで表に出す(エピソード画面の関連の中身など)。 */
export default function ContextTable({ table, items, labels }: { table: string; items: Rec[]; labels: Labels }) {
  const openPage = useOpenPage();
  const meta = useTable(table);
  if (!meta) return <div className="status info">{T.loading}</div>;
  const columns = listColumns(meta);
  return (
    <div className="scroll-x">
      <table className="list">
        <thead>
          <tr>
            <th>id</th>
            <th>{T.list.name}</th>
            {columns.map((c) => (
              <th key={c.key}><Spec hint={columnHint(c)}>{c.key}</Spec></th>
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
              onClick={(e) => openPage(`/tables/${table}/${item.id}`, e)}
              onKeyDown={(e) => {
                if (e.key === "Enter") openPage(`/tables/${table}/${item.id}`);
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
    </div>
  );
}
