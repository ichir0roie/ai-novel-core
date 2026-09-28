"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { getReviewSummary, type ReviewSummary } from "@/lib/api";
import { HIDDEN_TABLES } from "@/lib/hidden";
import { useMeta } from "@/lib/meta";
import { T } from "@/lib/text";

/** 画面の上端に薄い帯だけを常に出し、そこへマウスを寄せる(hover)かクリックすると、
 * メニューが上から大きく降りてきて中身の上に重なって開く。
 * 開いたときは、カーソルがメニューから離れる、メニューの外をクリックする、Esc、リンクをクリックする、
 * のいずれかで閉じる。 */
export default function Nav() {
  const pathname = usePathname();
  const { tables } = useMeta();
  const [summary, setSummary] = useState<ReviewSummary | null>(null);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    getReviewSummary().then(setSummary).catch(() => setSummary(null));
    setOpen(false);
    // クリックしたリンクにフォーカスが残ると CSS の :focus-within で開いたままになるため外す
    if (ref.current && document.activeElement instanceof HTMLElement && ref.current.contains(document.activeElement)) {
      document.activeElement.blur();
    }
  }, [pathname]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  return (
    <nav ref={ref} className={`nav ${open ? "open" : ""}`} onMouseLeave={() => setOpen(false)}>
      <div className="nav-bar">
        <button type="button" className="nav-handle" onClick={() => setOpen((v) => !v)} aria-label={T.nav.menu} aria-expanded={open} />
      </div>
      <div
        className="nav-drawer"
        onClickCapture={(e) => {
          if ((e.target as HTMLElement).closest("a")) {
            setOpen(false);
            (e.target as HTMLElement).blur();
          }
        }}
      >
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
        <span className="group">
          <Link href="/interface" className={isActive("/interface") ? "active" : ""}>{T.nav.endpoints}</Link>
        </span>
      </div>
    </nav>
  );
}
