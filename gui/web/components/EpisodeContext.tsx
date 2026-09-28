"use client";

import { useState } from "react";
import ContextTable from "@/components/ContextTable";
import Modal from "@/components/Modal";
import type { Labels, Rec } from "@/lib/api";
import { useMeta } from "@/lib/meta";
import { T } from "@/lib/text";

type ContextTableKey = "event" | "character" | "location" | "story";
type ContextBlock = { items: Rec[]; labels: Labels };
type Context = Partial<Record<ContextTableKey, ContextBlock>>;

const CATEGORY_KEYS: ContextTableKey[] = ["event", "character", "location", "story"];

/** 話の時期・場所に重なる出来事・人物・場所・作品(`related.context`)。表示ボタンで、その一覧をモーダルの表で見る。 */
export default function EpisodeContext({ context }: { context: Context }) {
  const { tables } = useMeta();
  const [open, setOpen] = useState<ContextTableKey | null>(null);

  const entries = CATEGORY_KEYS.filter((key) => (context[key]?.items.length ?? 0) > 0);
  if (entries.length === 0) return null;

  const labelOfTable = (key: string) => tables.find((table) => table.name === key)?.label ?? key;
  const active = open ? context[open] : null;

  return (
    <div className="panel related">
      <h2>{T.episodeContext.title}</h2>
      <ul>
        {entries.map((key) => (
          <li key={key} className="context-row">
            <span>
              {labelOfTable(key)} ({context[key]!.items.length})
            </span>
            <button type="button" onClick={() => setOpen(key)}>
              {T.episodeContext.show}
            </button>
          </li>
        ))}
      </ul>
      {open && active && (
        <Modal title={`${labelOfTable(open)} (${active.items.length})`} onClose={() => setOpen(null)} wide>
          <ContextTable table={open} items={active.items} labels={active.labels} />
        </Modal>
      )}
    </div>
  );
}
