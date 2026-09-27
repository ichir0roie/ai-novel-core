"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getReviewSummary, type ReviewSummary } from "@/lib/api";
import { useMeta } from "@/lib/meta";

export default function Home() {
  const { tables, error, loading } = useMeta();
  const [summary, setSummary] = useState<ReviewSummary | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  useEffect(() => {
    getReviewSummary().then(setSummary).catch((e) => setSummaryError(e.message));
  }, []);

  return (
    <>
      <h1>レビュー</h1>
      {summaryError && <div className="status error">API に届かない: {summaryError}(uvicorn を起動しているか確かめる)</div>}
      <div className="cards">
        {summary?.tables.map((row) => (
          <Link key={row.table} href={`/review/${row.table}`} className="card">
            <div className="sub">{row.label}の未確認</div>
            <div className="count">{row.pending}</div>
            <div className="sub">承認 {row.approved} / 非承認 {row.rejected}</div>
          </Link>
        ))}
      </div>

      <h2>テーブル</h2>
      {error && <div className="status error">{error}</div>}
      {loading && <div className="status info">読み込み中…</div>}
      <div className="cards">
        {tables.map((table) => (
          <Link key={table.name} href={`/tables/${table.name}`} className="card">
            <div className="sub">
              {table.label} <code>{table.name}</code>
            </div>
            <div className="count">{table.count}</div>
          </Link>
        ))}
      </div>
    </>
  );
}
