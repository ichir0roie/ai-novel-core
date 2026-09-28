"use client";

import { useState } from "react";
import ContextTable from "@/components/ContextTable";
import EpisodeCharacters from "@/components/EpisodeCharacters";
import Modal from "@/components/Modal";
import type { Labels, Rec } from "@/lib/api";
import { useMeta } from "@/lib/meta";
import { T } from "@/lib/text";

type ContextTableKey = "event" | "character" | "location" | "story";
type ContextBlock = { items: Rec[]; labels: Labels };
type Context = Partial<Record<ContextTableKey, ContextBlock>>;

const CATEGORY_KEYS: ContextTableKey[] = ["event", "character", "location", "story"];

type CharactersProps = {
  characterIds: number[];
  onChangeCharacterIds: (ids: number[]) => void;
  episodeStart: unknown;
};

/** 話の時期・場所に重なる出来事・人物・場所・作品(`related.context`、閲覧専用)。種類ごとのボタンを横に並べ、
 * 押すとその一覧をモーダルの表で見る。episode のときだけ、同じ行に編集できる登場人物のボタンも並べる
 * (`characterIds`/`onChangeCharacterIds`/`episodeStart` を渡したときだけ出す)。 */
export default function EpisodeContext({
  context, characterIds, onChangeCharacterIds, episodeStart,
}: { context: Context } & Partial<CharactersProps>) {
  const { tables } = useMeta();
  const [open, setOpen] = useState<ContextTableKey | null>(null);

  const entries = CATEGORY_KEYS.filter((key) => (context[key]?.items.length ?? 0) > 0);
  const showCharacters = characterIds !== undefined && onChangeCharacterIds !== undefined;
  if (entries.length === 0 && !showCharacters) return null;

  const labelOfTable = (key: string) => tables.find((table) => table.name === key)?.label ?? key;
  const active = open ? context[open] : null;

  return (
    <div className="panel related context-bar">
      <span className="context-title">{T.episodeContext.title}</span>
      {entries.map((key) => (
        <button key={key} type="button" onClick={() => setOpen(key)}>
          {labelOfTable(key)} ({context[key]!.items.length})
        </button>
      ))}
      {showCharacters && (
        <EpisodeCharacters
          characterIds={characterIds!}
          onChange={onChangeCharacterIds!}
          episodeStart={episodeStart}
        />
      )}
      {open && active && (
        <Modal title={`${labelOfTable(open)} (${active.items.length})`} onClose={() => setOpen(null)} wide>
          <ContextTable table={open} items={active.items} labels={active.labels} />
        </Modal>
      )}
    </div>
  );
}
