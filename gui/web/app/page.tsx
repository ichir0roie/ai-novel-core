"use client";

import Link from "next/link";
import { HIDDEN_TABLES } from "@/lib/hidden";
import { PageTitle, useMeta } from "@/lib/meta";
import { T } from "@/lib/text";

export default function Home() {
  const { tables, error, loading } = useMeta();
  return (
    <>
      <PageTitle kind={T.home.title} />
      <h1>{T.home.title}</h1>
      {error && <div className="status error">{error}</div>}
      {loading && <div className="status info">{T.loading}</div>}
      <div className="cards">
        {tables.filter((table) => !HIDDEN_TABLES.has(table.name)).map((table) => (
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
