"use client";

import { useMemo, useState } from "react";
import CharacterSheetModal from "@/components/CharacterSheetModal";
import Modal from "@/components/Modal";
import { useOptions } from "@/components/ReferenceSelect";
import { useLocationCharacterIds } from "@/lib/locationCharacters";
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
  episodeLocationId: unknown;
  /** ボタンの横に名前を並べるか。話のページでは下に関係ごと並べる(`EpisodeCharacterRelations`)ので出さない */
  summary?: boolean;
};

/** 話の登場人物(`episode_character`)。「time & place」の行に並ぶボタンで、押すとモーダルで追加削除する。
 * その場で API へは保存せず、ページの編集中の値(`value.character_ids`)を更新するだけ(Save でまとめて保存)。
 * 候補は、検索欄が空ならフォームの場所(`location_id`)に時刻(`start`)にいる人物だけ、検索語を入れたら全人物から探す
 * (選んだ人物はいつも出す)。場所・時刻が空か読めないときは絞らない。
 * 並んだ名前(`summary`)を押すと、その人物を話の開始の時点で見るモーダル(`CharacterSheetModal`)を開く。 */
export default function EpisodeCharacters({ characterIds, onChange, episodeStart, episodeLocationId, summary = true }: Props) {
  const options = useOptions("character");
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const [viewing, setViewing] = useState<number | null>(null);
  const locationCharacterIds = useLocationCharacterIds(episodeLocationId, episodeStart, open);

  const byId = useMemo(() => new Map(options.map((o) => [o.id, o])), [options]);
  const selected = characterIds.map((id) => byId.get(id)).filter((o): o is NonNullable<typeof o> => o != null);

  const q = filter.trim();
  const shown = options.filter((o) =>
    characterIds.includes(o.id) || (q ? o.label.includes(q) : locationCharacterIds === null || locationCharacterIds.includes(o.id)));
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
                    {labelWithAge(o.label, o.born, episodeStart)}
                  </button>
                </span>
              ))
            : T.episodeCharacters.none}
        </span>
      )}
      {viewing !== null && <CharacterSheetModal characterId={viewing} time={episodeStart} onClose={() => setViewing(null)} />}
      {open && (
        <Modal
          title={T.episodeCharacters.modalTitle}
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
                {labelWithAge(`${o.id}: ${o.label}`, o.born, episodeStart)}
              </label>
            ))}
          </div>
          {shown.length === 0 && <span className="hint">{T.noCandidates}</span>}
        </Modal>
      )}
    </>
  );
}
