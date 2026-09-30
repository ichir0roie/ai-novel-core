"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import CommandPalette, { type Destination } from "@/components/CommandPalette";
import { getReviewSummary, type ReviewSummary } from "@/lib/api";
import { HIDDEN_TABLES } from "@/lib/hidden";
import { useMeta } from "@/lib/meta";
import { T } from "@/lib/text";

/** 画面の隅に小さな丸いメニューボタンを常に浮かべ(デスクトップは左上、スマホは親指の届く右下)、クリックしたときだけ
 * メニューを開く。開いたメニューは、外をクリックする、Esc、リンクを押す、のいずれかで閉じる。
 * Ctrl+K(Mac は ⌘K)では、行き先の名前を打ち込んで飛ぶ検索付きのメニューを開く。 */
export default function Nav() {
  const pathname = usePathname();
  const { tables } = useMeta();
  const [summary, setSummary] = useState<ReviewSummary | null>(null);
  const [open, setOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    getReviewSummary().then(setSummary).catch(() => setSummary(null));
    setOpen(false);
    setPaletteOpen(false);
  }, [pathname]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(false);
        setPaletteOpen((value) => !value);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));
  const reviews = summary?.tables ?? [];
  const visibleTables = tables.filter((table) => !HIDDEN_TABLES.has(table.name));
  const destinations: Destination[] = [
    { href: "/", label: T.appName },
    ...reviews.map((row) => ({ href: `/review/${row.table}`, label: T.nav.review(row.label) })),
    ...visibleTables.map((table) => ({ href: `/tables/${table.name}`, label: table.label })),
    { href: "/interface", label: T.nav.endpoints },
  ];

  return (
    <nav ref={ref} className="nav">
      <button
        type="button"
        className={`nav-fab ${open ? "open" : ""}`}
        onClick={() => setOpen((value) => !value)}
        aria-label={T.nav.menu}
        aria-expanded={open}
      >
        <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
          <path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
      </button>
      {open && (
        <div
          className="nav-panel"
          onClick={(e) => {
            // 今いるページのリンクでもページは変わらないので、押したら閉じる
            if ((e.target as HTMLElement).closest("a")) setOpen(false);
          }}
        >
          <Link href="/" className={`brand ${isActive("/") ? "active" : ""}`}>{T.appName}</Link>
          <span className="group">
            {reviews.map((row) => (
              <Link key={row.table} href={`/review/${row.table}`} className={isActive(`/review/${row.table}`) ? "active" : ""}>
                {T.nav.review(row.label)}{row.pending > 0 && <span className="badge">{row.pending}</span>}
              </Link>
            ))}
          </span>
          <span className="group">
            {visibleTables.map((table) => (
              <Link key={table.name} href={`/tables/${table.name}`} className={isActive(`/tables/${table.name}`) ? "active" : ""}>
                {table.label}
              </Link>
            ))}
          </span>
          <span className="group">
            <Link href="/interface" className={isActive("/interface") ? "active" : ""}>{T.nav.endpoints}</Link>
            <span className="hint">{T.nav.searchHint}</span>
          </span>
        </div>
      )}
      {paletteOpen && <CommandPalette destinations={destinations} onClose={() => setPaletteOpen(false)} />}
    </nav>
  );
}
