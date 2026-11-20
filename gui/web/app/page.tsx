"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getTableCounts } from "@/lib/api";
import { HIDDEN_TABLES } from "@/lib/hidden";
import { PageTitle, TABLES } from "@/lib/meta";
import PageHelp from "@/components/PageHelp";
import { T } from "@/lib/text";

export default function Home() {
  const [counts, setCounts] = useState<Record<string, number> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getTableCounts()
      .then((result) => setCounts(result.counts))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  return (
    <>
      <PageTitle kind={T.home.title} />
      <div className="page-heading">
        <h1>{T.home.title}</h1>
        <PageHelp page={T.home.title} help={T.help.home} />
      </div>
      {error && <div className="status error">{error}</div>}
      <div className="cards">
        {TABLES.filter((table) => !HIDDEN_TABLES.has(table.name)).map((table) => (
          <Link key={table.name} href={`/tables/${table.name}`} className="card">
            <div className="sub">
              <code>{table.name}</code>
            </div>
            <div className="count">{counts?.[table.name] ?? "…"}</div>
          </Link>
        ))}
      </div>
    </>
  );
}
