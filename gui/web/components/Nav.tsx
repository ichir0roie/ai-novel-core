"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { getReviewSummary, type ReviewSummary } from "@/lib/api";
import { HIDDEN_TABLES } from "@/lib/hidden";
import { useMeta } from "@/lib/meta";
import { T } from "@/lib/text";

export default function Nav() {
  const pathname = usePathname();
  const { tables } = useMeta();
  const [summary, setSummary] = useState<ReviewSummary | null>(null);

  useEffect(() => {
    getReviewSummary().then(setSummary).catch(() => setSummary(null));
  }, [pathname]);

  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  return (
    <nav className="nav">
      <Link href="/" className={`brand ${isActive("/") ? "active" : ""}`}>{T.appName}</Link>
      <span className="group">
        {summary?.tables.map((row) => (
          <Link key={row.table} href={`/review/${row.table}`} className={isActive(`/review/${row.table}`) ? "active" : ""}>
            {T.nav.review(row.label)}{row.pending > 0 && <span className="badge">{row.pending}</span>}
          </Link>
        ))}
      </span>
      <span className="group">
        {tables.filter((table) => !HIDDEN_TABLES.has(table.name)).map((table) => (
          <Link key={table.name} href={`/tables/${table.name}`} className={isActive(`/tables/${table.name}`) ? "active" : ""}>
            {table.label}
          </Link>
        ))}
      </span>
      <span className="spacer" />
      <span className="group">
        <Link href="/interface" className={isActive("/interface") ? "active" : ""}>{T.nav.endpoints}</Link>
      </span>
    </nav>
  );
}
