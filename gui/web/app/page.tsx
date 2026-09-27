"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getReviewSummary, type ReviewSummary } from "@/lib/api";
import { HIDDEN_TABLES } from "@/lib/hidden";
import { PageTitle, useMeta } from "@/lib/meta";
import { T } from "@/lib/text";

export default function Home() {
  const { tables, error, loading } = useMeta();
  const [summary, setSummary] = useState<ReviewSummary | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  useEffect(() => {
    getReviewSummary().then(setSummary).catch((e) => setSummaryError(e.message));
  }, []);

  return (
    <>
      <PageTitle kind={T.home.title} />
      <h1>{T.home.title}</h1>
      {summaryError && <div className="status error">{T.cannotReachApi(summaryError)}</div>}
      <div className="cards">
        {summary?.tables.map((row) => (
          <Link key={row.table} href={`/review/${row.table}`} target="_blank" rel="noopener noreferrer" className="card">
            <div className="sub">{T.home.pending(row.label)}</div>
            <div className="count">{row.pending}</div>
            <div className="sub">{T.home.counts(row.approved, row.rejected)}</div>
          </Link>
        ))}
      </div>

      <h2>{T.home.tables}</h2>
      {error && <div className="status error">{error}</div>}
      {loading && <div className="status info">{T.loading}</div>}
      <div className="cards">
        {tables.filter((table) => !HIDDEN_TABLES.has(table.name)).map((table) => (
          <Link key={table.name} href={`/tables/${table.name}`} target="_blank" rel="noopener noreferrer" className="card">
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
