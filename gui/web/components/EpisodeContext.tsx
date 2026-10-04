"use client";

import { useState } from "react";
import ContextTable from "@/components/ContextTable";
import EpisodeCharacterRelations from "@/components/EpisodeCharacterRelations";
import EpisodeCharacters from "@/components/EpisodeCharacters";
import Modal from "@/components/Modal";
import type { Labels, Rec } from "@/lib/api";
import { T } from "@/lib/text";

type ContextTableKey = "event" | "story";
type ContextBlock = { items: Rec[]; labels: Labels };
type Context = Partial<Record<ContextTableKey, ContextBlock>>;

const CATEGORY_KEYS: ContextTableKey[] = ["event", "story"];

type CharactersProps = {
  characterIds: number[];
  onChangeCharacterIds: (ids: number[]) => void;
  episodeStart: unknown;
  episodeLocationId: unknown;
};

/** 話の時期・場所に重なる出来事・作品(`related.context`、閲覧専用)。種類ごとのボタンを横に並べ、
 * 押すとその一覧をモーダルの表で見る。episode のときだけ、同じ行に編集できる登場人物のボタンも並べ、
 * その下に登場人物の歳(押すと登場人物どうしの関係)を出す(`characterIds`/`onChangeCharacterIds`/`episodeStart` を渡したときだけ出す)。 */
export default function EpisodeContext({
  context, characterIds, onChangeCharacterIds, episodeStart, episodeLocationId,
}: { context: Context } & Partial<CharactersProps>) {
  const [open, setOpen] = useState<ContextTableKey | null>(null);

  const entries = CATEGORY_KEYS.filter((key) => (context[key]?.items.length ?? 0) > 0);
  const showCharacters = characterIds !== undefined && onChangeCharacterIds !== undefined;
  if (entries.length === 0 && !showCharacters) return null;

  const active = open ? context[open] : null;

  return (
    <div className="panel related context-bar">
      <span className="context-title">{T.episodeContext.title}</span>
      {entries.map((key) => (
        <button key={key} type="button" onClick={() => setOpen(key)}>
          {key} ({context[key]!.items.length})
        </button>
      ))}
      {showCharacters && (
        <EpisodeCharacters
          characterIds={characterIds!}
          onChange={onChangeCharacterIds!}
          episodeStart={episodeStart}
          episodeLocationId={episodeLocationId}
          summary={false}
        />
      )}
      {showCharacters && <EpisodeCharacterRelations characterIds={characterIds!} start={episodeStart} collapsible />}
      {open && active && (
        <Modal title={`${open} (${active.items.length})`} onClose={() => setOpen(null)} wide>
          <ContextTable table={open} items={active.items} labels={active.labels} />
        </Modal>
      )}
    </div>
  );
}
