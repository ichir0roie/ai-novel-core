"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import CommandPalette, { type Destination } from "@/components/CommandPalette";
import { PickerModal, PickerToggle } from "@/components/Picker";
import { useOptions } from "@/components/ReferenceSelect";
import { HIDDEN_TABLES } from "@/lib/hidden";
import { TABLES } from "@/lib/meta";
import { selectStory, useSelectedStoryId } from "@/lib/selectedStory";
import { T } from "@/lib/text";

/** 画面の隅に小さな丸いメニューボタンを常に浮かべ(デスクトップは左上、スマホは親指の届く右下)、クリックしたときだけ
 * メニューを開く。開いたメニューは、外をクリックする、Esc、リンクを押す、のいずれかで閉じる。
 * Ctrl+K(Mac は ⌘K)では、行き先の名前を打ち込んで飛ぶ検索付きのメニューを開く。 */
export default function Nav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  // 作品を選ぶモーダルは、メニューの外のクリックで閉じたメニューと一緒に消えないよう、メニューの外に開く
  const [pickingStory, setPickingStory] = useState(false);
  const storyId = useSelectedStoryId();
  const stories = useOptions(open || pickingStory ? "story" : null);
  const storyChoices = stories.map((o) => ({ value: o.id, label: T.nameId(o.label, o.id) }));
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
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
  const visibleTables = TABLES.filter((table) => !HIDDEN_TABLES.has(table.name));
  const destinations: Destination[] = [
    { href: "/", label: T.appName },
    ...visibleTables.map((table) => ({ href: `/tables/${table.name}`, label: table.name })),
    { href: "/timeline", label: T.nav.timeline },
    { href: "/event_timeline", label: T.nav.eventTimeline },
    { href: "/overview", label: T.nav.overview },
    { href: "/maps", label: T.nav.maps },
    { href: "/relations", label: T.nav.relations },
    { href: "/expansions", label: T.nav.expansions },
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
            {visibleTables.map((table) => (
              <Link key={table.name} href={`/tables/${table.name}`} className={isActive(`/tables/${table.name}`) ? "active" : ""}>
                {table.name}
              </Link>
            ))}
          </span>
          <span className="group">
            <Link href="/timeline" className={isActive("/timeline") ? "active" : ""}>{T.nav.timeline}</Link>
            <Link href="/event_timeline" className={isActive("/event_timeline") ? "active" : ""}>{T.nav.eventTimeline}</Link>
            <Link href="/overview" className={isActive("/overview") ? "active" : ""}>{T.nav.overview}</Link>
            <Link href="/maps" className={isActive("/maps") ? "active" : ""}>{T.nav.maps}</Link>
            <Link href="/relations" className={isActive("/relations") ? "active" : ""}>{T.nav.relations}</Link>
            <Link href="/expansions" className={isActive("/expansions") ? "active" : ""}>{T.nav.expansions}</Link>
            <Link href="/interface" className={isActive("/interface") ? "active" : ""}>{T.nav.endpoints}</Link>
            <span className="hint">{T.nav.searchHint}</span>
          </span>
          <span className="group nav-story">
            <span>{T.nav.story}</span>
            <PickerToggle
              label={storyChoices.find((c) => c.value === storyId)?.label ?? (storyId === null ? T.none : T.idMark(storyId))}
              empty={storyId === null}
              onClick={() => {
                setOpen(false);
                setPickingStory(true);
              }}
            />
            <span className="hint">{T.nav.storyHint}</span>
          </span>
        </div>
      )}
      {pickingStory && (
        <PickerModal
          title={T.nav.storyTitle}
          choices={storyChoices}
          value={storyId}
          emptyLabel={T.none}
          onPick={(id) => id !== storyId && selectStory(id)}
          onClose={() => setPickingStory(false)}
        />
      )}
      {paletteOpen && <CommandPalette destinations={destinations} onClose={() => setPaletteOpen(false)} />}
    </nav>
  );
}
