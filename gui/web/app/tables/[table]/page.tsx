"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { labelOf, listRecords, type ColumnMeta, type Rec, type RecordList } from "@/lib/api";
import { useTable } from "@/lib/meta";

const PAGE = 50;
const HIDDEN = new Set(["id", "fact_check", "meme_seeded", "event_seeded", "polygon"]);

function cell(column: ColumnMeta, item: Rec, labels: RecordList["labels"]): string {
  const value = item[column.key];
  if (value == null) return "";
  if (column.references) return labelOf(labels, column.key, value);
  if (column.type === "boolean") return value ? "✓" : "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export default function TablePage() {
  const { table } = useParams<{ table: string }>();
  const router = useRouter();
  const search = useSearchParams();
  const meta = useTable(table);
  const [data, setData] = useState<RecordList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState(search.get("q") ?? "");

  const params = useMemo(() => {
    const p = new URLSearchParams(search.toString());
    if (!p.has("limit")) p.set("limit", String(PAGE));
    if (!p.has("order")) p.set("order", "desc");
    return p;
  }, [search]);

  useEffect(() => {
    setError(null);
    listRecords(table, params).then(setData).catch((e) => setError(e.message));
  }, [table, params]);

  const setParam = (key: string, value: string | null) => {
    const p = new URLSearchParams(search.toString());
    if (value === null || value === "") p.delete(key);
    else p.set(key, value);
    if (key !== "offset") p.delete("offset");
    router.push(`/tables/${table}?${p.toString()}`);
  };

  if (!meta) return <div className="status info">読み込み中…</div>;
  const columns = meta.columns
    .filter((c) => !c.section && !HIDDEN.has(c.key) && c.type !== "id_list" && !c.create_only && c.key !== meta.label_column)
    .slice(0, 7);
  const confirmColumn = meta.columns.find((c) => c.type === "confirm");
  const offset = Number(params.get("offset") ?? 0);
  const total = data?.total ?? 0;

  return (
    <>
      <h1>
        {meta.label} <code>{table}</code>
      </h1>
      <div className="toolbar">
        <form
          style={{ display: "contents" }}
          onSubmit={(e) => {
            e.preventDefault();
            setParam("q", q);
          }}
        >
          <input type="search" placeholder="名前・本文で探す" value={q} onChange={(e) => setQ(e.target.value)} />
          <button type="submit">探す</button>
        </form>
        {confirmColumn && (
          <span className="chips">
            {["", ...(confirmColumn.choices ?? [])].map((choice) => (
              <button key={choice} type="button" className={`chip ${(search.get("confirmed") ?? "") === choice ? "on" : ""}`} onClick={() => setParam("confirmed", choice)}>
                {choice || "すべて"}
              </button>
            ))}
          </span>
        )}
        <button type="button" onClick={() => setParam("order", params.get("order") === "desc" ? "asc" : "desc")}>
          id {params.get("order") === "desc" ? "↓" : "↑"}
        </button>
        <Link href={`/tables/${table}/new`}>
          <button type="button" className="primary">
            + 足す
          </button>
        </Link>
      </div>
      {error && <div className="status error">{error}</div>}
      <table className="list">
        <thead>
          <tr>
            <th>id</th>
            <th>名前</th>
            {columns.map((c) => (
              <th key={c.key} title={c.key}>
                {c.label}
              </th>
            ))}
            <th>本文</th>
          </tr>
        </thead>
        <tbody>
          {data?.items.map((item) => (
            <tr key={String(item.id)}>
              <td>
                <Link href={`/tables/${table}/${item.id}`}>{String(item.id)}</Link>
              </td>
              <td className="name">
                <Link href={`/tables/${table}/${item.id}`}>{String(item.label ?? "")}</Link>
              </td>
              {columns.map((c) => (
                <td key={c.key}>{cell(c, item, data.labels)}</td>
              ))}
              <td className="preview">{String(item.preview ?? "")}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="pager">
        <button disabled={offset <= 0} onClick={() => setParam("offset", String(Math.max(0, offset - PAGE)))}>
          前へ
        </button>
        <span>
          {total === 0 ? 0 : offset + 1}〜{Math.min(offset + PAGE, total)} / {total} 件
        </span>
        <button disabled={offset + PAGE >= total} onClick={() => setParam("offset", String(offset + PAGE))}>
          次へ
        </button>
      </div>
    </>
  );
}
