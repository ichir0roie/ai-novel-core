"use client";

import { useMemo, useState } from "react";
import type { Rec } from "@/lib/api";
import NameId from "./NameId";
import { PickerModal } from "./Picker";
import { useOptions } from "./ReferenceSelect";
import { T } from "@/lib/text";

/** 子の行の知る相手(`knowers`。知る人物か知る場所のどちらか一方と、知った時刻)。
 * 札を編集中でなくても足し外しでき、その場で API へは保存せず、ページの編集中の値を直すだけ(Save でまとめて保存)。
 * 足せるのは人物だけ。場所の知る相手・知った時刻は今ある行のまま残す。 */
export default function KnowerList({ knowers, onChange }: { knowers: Rec[]; onChange: (knowers: Rec[]) => void }) {
  const characters = useOptions("character");
  const locations = useOptions("location");
  const [open, setOpen] = useState(false);
  const characterLabels = useMemo(() => new Map(characters.map((o) => [o.id, o.label])), [characters]);
  const locationLabels = useMemo(() => new Map(locations.map((o) => [o.id, o.label])), [locations]);
  const knownIds = new Set(knowers.map((knower) => knower.knower_id));
  const choices = characters.filter((o) => !knownIds.has(o.id)).map((o) => ({ value: o.id, label: T.nameId(o.label, o.id) }));

  const add = (id: number | null) => {
    if (id !== null) onChange([...knowers, { knower_id: id, location_id: null, start: null }]);
  };
  const remove = (index: number) => onChange(knowers.filter((_, i) => i !== index));

  return (
    // 札を押すと編集に入るので、ここでの操作は札へ伝えない
    <div className="flow-knowers" onClick={(e) => e.stopPropagation()}>
      <span className="flow-flag">{T.knowers.label}</span>
      {knowers.map((knower, index) => {
        // 知る人物と知る場所はどちらか一方だけを持つ(`KnowerRow`)
        const characterId = knower.knower_id as number | null;
        const locationId = knower.location_id as number;
        return (
          <span key={index} className="knower-chip">
            {characterId !== null ? (
              <NameId name={characterLabels.get(characterId)} id={characterId} />
            ) : (
              <>
                {T.knowers.location}
                <NameId name={locationLabels.get(locationId)} id={locationId} />
              </>
            )}
            {knower.start != null && <span className="hint">{T.knowers.since(String(knower.start).split(" ")[0])}</span>}
            <button type="button" className="ghost" onClick={() => remove(index)} title={T.knowers.remove}>
              ×
            </button>
          </span>
        );
      })}
      <button type="button" onClick={() => setOpen(true)}>
        {T.knowers.add}
      </button>
      {open && <PickerModal title={T.knowers.pickTitle} choices={choices} value={null} onPick={add} onClose={() => setOpen(false)} />}
    </div>
  );
}
