"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { getReviewSummary, runSync, type ReviewSummary } from "@/lib/api";
import { useMeta } from "@/lib/meta";

export default function Nav() {
  const pathname = usePathname();
  const { tables, reload } = useMeta();
  const [summary, setSummary] = useState<ReviewSummary | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    getReviewSummary().then(setSummary).catch(() => setSummary(null));
  }, [pathname]);

  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  const sync = async () => {
    setSyncing(true);
    setMessage(null);
    try {
      const result = await runSync();
      const conflicts = Array.isArray(result.conflicts) ? result.conflicts.length : 0;
      const written = Array.isArray(result.written) ? result.written.length : 0;
      setMessage(`同期: 書き出し ${written} 件、衝突 ${conflicts} 件`);
      await reload();
    } catch (e) {
      setMessage(`同期に失敗: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSyncing(false);
    }
  };

  return (
    <nav className="nav">
      <Link href="/" className={`brand ${isActive("/") ? "active" : ""}`}>novel db</Link>
      <span className="group">
        {summary?.tables.map((row) => (
          <Link key={row.table} href={`/review/${row.table}`} className={isActive(`/review/${row.table}`) ? "active" : ""}>
            {row.label}レビュー{row.pending > 0 && <span className="badge">{row.pending}</span>}
          </Link>
        ))}
      </span>
      <span className="group">
        {tables.map((table) => (
          <Link key={table.name} href={`/tables/${table.name}`} className={isActive(`/tables/${table.name}`) ? "active" : ""}>
            {table.label}
          </Link>
        ))}
      </span>
      <span className="spacer" />
      {message && <span className="nav-message" style={{ color: "var(--muted)", fontSize: "0.85rem" }}>{message}</span>}
      <button onClick={sync} disabled={syncing} title="db と worlds/ の md を同期する(SyncDb)">
        {syncing ? "同期中…" : "md と同期"}
      </button>
    </nav>
  );
}
