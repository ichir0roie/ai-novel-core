"use client";

import { useEffect, useMemo, useState } from "react";
import Modal from "@/components/Modal";
import { useOptions } from "@/components/ReferenceSelect";
import { getPlaceCharacters } from "@/lib/api";
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
  episodePlaceId: unknown;
};

/** 話の登場人物(`episode_character`)。「time & place」の行に並ぶボタンで、押すとモーダルで追加削除する。
 * その場で API へは保存せず、ページの編集中の値(`value.character_ids`)を更新するだけ(Save でまとめて保存)。
 * 候補は、検索欄が空ならフォームの場所(`place_id`)に時刻(`start`)にいる人物だけ、検索語を入れたら全人物から探す
 * (選んだ人物はいつも出す)。場所・時刻が空か読めないときは絞らない。 */
export default function EpisodeCharacters({ characterIds, onChange, episodeStart, episodePlaceId }: Props) {
  const options = useOptions("character");
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const [placeCharacterIds, setPlaceCharacterIds] = useState<number[] | null>(null);

  const placeId = typeof episodePlaceId === "number" ? episodePlaceId : null;
  const start = typeof episodeStart === "string" && episodeStart.trim() ? episodeStart : null;
  useEffect(() => {
    setPlaceCharacterIds(null);
    if (!open || placeId === null || start === null) return;
    let alive = true;
    getPlaceCharacters(placeId, start)
      .then((r) => alive && setPlaceCharacterIds(r.character_ids))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [open, placeId, start]);

  const byId = useMemo(() => new Map(options.map((o) => [o.id, o])), [options]);
  const selected = characterIds.map((id) => byId.get(id)).filter((o): o is NonNullable<typeof o> => o != null);

  const q = filter.trim();
  const shown = options.filter((o) =>
    characterIds.includes(o.id) || (q ? o.label.includes(q) : placeCharacterIds === null || placeCharacterIds.includes(o.id)));
  const toggle = (id: number) => onChange(characterIds.includes(id) ? characterIds.filter((v) => v !== id) : [...characterIds, id]);

  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        {T.episodeCharacters.button(characterIds.length)}
      </button>
      <span className="episode-characters-summary">
        {selected.length > 0
          ? selected.map((o) => labelWithAge(o.label, o.born, episodeStart)).join(" / ")
          : T.episodeCharacters.none}
      </span>
      {open && (
        <Modal title={T.episodeCharacters.modalTitle} onClose={() => setOpen(false)}>
          <input type="text" placeholder={T.filter} value={filter} onChange={(e) => setFilter(e.target.value)} style={{ marginBottom: "0.3rem" }} />
          <div className="multi">
            {shown.map((o) => (
              <label key={o.id}>
                <input type="checkbox" checked={characterIds.includes(o.id)} onChange={() => toggle(o.id)} />
                {labelWithAge(`${o.id}: ${o.label}`, o.born, episodeStart)}
              </label>
            ))}
            {shown.length === 0 && <span className="hint">{T.noCandidates}</span>}
          </div>
        </Modal>
      )}
    </>
  );
}
