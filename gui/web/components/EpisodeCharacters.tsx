"use client";

import { useMemo, useState } from "react";
import CharacterSheetModal from "@/components/CharacterSheetModal";
import Modal from "@/components/Modal";
import NameId from "@/components/NameId";
import { useOptions } from "@/components/ReferenceSelect";
import { useStoryCharacterIds } from "@/lib/storyCharacters";
import { ageAt } from "@/lib/stamp";
import { T } from "@/lib/text";

/** 選択肢の表示名に、分かれば歳を添える(`Option.born` と episode の `start` から計算)。 */
function labelWithAge(label: string, born: string | null | undefined, at: unknown): string {
  const age = ageAt(born ?? null, at);
  return age === null ? label : `${label}(${age})`;
}

type Props = {
  characterIds: number[];
  onChange: (ids: number[]) => void;
  episodeStart: unknown;
  episodeStoryId: unknown;
  /** ボタンの横に名前を並べるか。話のページでは下に関係ごと並べる(`EpisodeCharacterRelations`)ので出さない */
  summary?: boolean;
  /** 選ぶモーダルの見出し。出来事の当事者を選ぶときに替える */
  modalTitle?: string;
};

/** 話の登場人物(`episode_character`)と、出来事の当事者(`event_character`)。ボタンで、押すとモーダルで追加削除する。
 * その場で API へは保存せず、ページの編集中の値(`value.character_ids`)を更新するだけ(Save でまとめて保存)。
 * 候補は、検索欄が空なら同じ作品(`story_id`)の話と、話の期間の出来事に出てくる人物だけを、出てくる回数の多い順に並べる
 * (選んだ人物はいつも出し、作品に出てこなければ後ろに並べる)。検索語を入れたら全人物から探す。
 * 作品が空か読めないとき、作品にまだ誰も出てこないときは絞らない。
 * 並んだ名前(`summary`)を押すと、その人物を話の開始の時点で見るモーダル(`CharacterSheetModal`)を開く。 */
export default function EpisodeCharacters({
  characterIds,
  onChange,
  episodeStart,
  episodeStoryId,
  summary = true,
  modalTitle = T.episodeCharacters.modalTitle,
}: Props) {
  const options = useOptions("character");
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const [viewing, setViewing] = useState<number | null>(null);
  const storyCharacterIds = useStoryCharacterIds(episodeStoryId, open);

  const byId = useMemo(() => new Map(options.map((o) => [o.id, o])), [options]);
  const selected = characterIds.map((id) => byId.get(id)).filter((o): o is NonNullable<typeof o> => o != null);

  const q = filter.trim();
  const shown = useMemo(() => {
    if (q) return options.filter((o) => characterIds.includes(o.id) || o.label.includes(q) || String(o.id) === q);
    if (storyCharacterIds === null || storyCharacterIds.length === 0) return options;
    const rank = new Map(storyCharacterIds.map((id, i) => [id, i]));
    // sort は安定なので、作品に出てこない選んだ人物は元の並びのまま後ろに残る
    return options.filter((o) => characterIds.includes(o.id) || rank.has(o.id))
      .sort((a, b) => (rank.get(a.id) ?? Infinity) - (rank.get(b.id) ?? Infinity));
  }, [options, characterIds, q, storyCharacterIds]);
  const toggle = (id: number) => onChange(characterIds.includes(id) ? characterIds.filter((v) => v !== id) : [...characterIds, id]);

  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        {T.episodeCharacters.button(characterIds.length)}
      </button>
      {summary && (
        <span className="episode-characters-summary">
          {selected.length > 0
            ? selected.map((o, i) => (
                <span key={o.id}>
                  {i > 0 && " / "}
                  <button type="button" className="character-open" onClick={() => setViewing(o.id)}>
                    <NameId name={labelWithAge(o.label, o.born, episodeStart)} id={o.id} />
                  </button>
                </span>
              ))
            : T.episodeCharacters.none}
        </span>
      )}
      {viewing !== null && <CharacterSheetModal characterId={viewing} time={episodeStart} onClose={() => setViewing(null)} />}
      {open && (
        <Modal
          title={modalTitle}
          onClose={() => setOpen(false)}
          wide
          actions={
            <>
              <span className="spacer" />
              <button type="button" className="primary" onClick={() => setOpen(false)}>
                {T.picker.done}
              </button>
            </>
          }
        >
          <input type="text" className="picker-filter" placeholder={T.filter} value={filter} autoFocus onChange={(e) => setFilter(e.target.value)} />
          <div className="picker-grid">
            {shown.map((o) => (
              <label key={o.id} className={`picker-option ${characterIds.includes(o.id) ? "selected" : ""}`}>
                <input type="checkbox" checked={characterIds.includes(o.id)} onChange={() => toggle(o.id)} />
                <NameId name={labelWithAge(o.label, o.born, episodeStart)} id={o.id} />
              </label>
            ))}
          </div>
          {shown.length === 0 && <span className="hint">{T.noCandidates}</span>}
        </Modal>
      )}
    </>
  );
}
