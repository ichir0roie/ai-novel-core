"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { T } from "@/lib/text";

export type Destination = { href: string; label: string };

type Props = {
  destinations: Destination[];
  onClose: () => void;
};

/** Ctrl+K(Mac は ⌘K)で開く、行き先の名前を打ち込んで飛ぶメニュー。↑↓ で選び Enter で飛ぶ。背景クリックか Escape で閉じる。 */
export default function CommandPalette({ destinations, onClose }: Props) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const listRef = useRef<HTMLUListElement>(null);

  const matches = useMemo(() => {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    return destinations.filter((destination) => {
      const text = `${destination.label} ${destination.href}`.toLowerCase();
      return words.every((word) => text.includes(word));
    });
  }, [destinations, query]);

  useEffect(() => setCursor(0), [query]);

  useEffect(() => {
    listRef.current?.children[cursor]?.scrollIntoView({ block: "nearest" });
  }, [cursor]);

  const go = (destination: Destination | undefined) => {
    if (!destination) return;
    onClose();
    router.push(destination.href);
  };

  return (
    <div className="palette-backdrop" onClick={onClose}>
      <div className="palette" role="dialog" aria-label={T.nav.search} onClick={(e) => e.stopPropagation()}>
        <input
          autoFocus
          value={query}
          placeholder={T.nav.search}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setCursor((value) => Math.min(value + 1, matches.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setCursor((value) => Math.max(value - 1, 0));
            } else if (e.key === "Enter") {
              e.preventDefault();
              go(matches[cursor]);
            } else if (e.key === "Escape") {
              onClose();
            }
          }}
        />
        <ul ref={listRef}>
          {matches.map((destination, index) => (
            <li key={destination.href} className={index === cursor ? "on" : ""}>
              <button type="button" onMouseMove={() => setCursor(index)} onClick={() => go(destination)}>
                {destination.label}
              </button>
            </li>
          ))}
          {matches.length === 0 && <li className="none">{T.nav.noMatch}</li>}
        </ul>
      </div>
    </div>
  );
}
