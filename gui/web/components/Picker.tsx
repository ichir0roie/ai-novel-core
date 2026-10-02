"use client";

import { useState } from "react";
import Modal from "./Modal";
import { T } from "@/lib/text";

// これより選択肢が多ければ、絞り込み欄を出し、幅の広いモーダルに並べる
const MANY = 12;

/** プルダウンの代わりに置くボタン。今の値を出し、押すと選ぶモーダルを開く。 */
export function PickerToggle({ label, empty, onClick, disabled }: { label: string; empty?: boolean; onClick: () => void; disabled?: boolean }) {
  return (
    <button type="button" className={`picker-toggle ${empty ? "empty" : ""}`} onClick={onClick} disabled={disabled} title={label}>
      <span className="picker-label">{label}</span>
      <span className="picker-caret">▾</span>
    </button>
  );
}

export type Choice<V> = { value: V; label: string };

type Props<V> = {
  title: string;
  choices: Choice<V>[];
  value: V | null;
  onPick: (value: V | null) => void;
  onClose: () => void;
  /** 渡せば、先頭に「選ばない」(null)のボタンをこの名前で置く */
  emptyLabel?: string;
  /** 絞り込み欄が空のときに出す選択肢。null・省略なら全部出す(今の値はいつも出す) */
  suggested?: V[] | null;
};

/** 一つを選ぶモーダル。選択肢を大きなボタンで並べ、押すと選んで閉じる。 */
export function PickerModal<V>({ title, choices, value, onPick, onClose, emptyLabel, suggested }: Props<V>) {
  const [filter, setFilter] = useState("");
  const many = choices.length > MANY;
  const q = filter.trim();
  const shown = choices.filter((c) =>
    c.value === value || (q ? c.label.includes(q) || String(c.value) === q : !suggested || suggested.includes(c.value)));
  const pick = (v: V | null) => {
    onPick(v);
    onClose();
  };

  return (
    <Modal title={title} onClose={onClose} wide={many}>
      {many && <input type="text" className="picker-filter" placeholder={T.filter} value={filter} autoFocus onChange={(e) => setFilter(e.target.value)} />}
      <div className="picker-grid">
        {emptyLabel !== undefined && !q && (
          <button type="button" className={`picker-option none ${value === null ? "selected" : ""}`} onClick={() => pick(null)}>
            {emptyLabel}
          </button>
        )}
        {shown.map((c) => (
          <button key={String(c.value)} type="button" className={`picker-option ${c.value === value ? "selected" : ""}`} onClick={() => pick(c.value)}>
            {c.label}
          </button>
        ))}
      </div>
      {shown.length === 0 && <span className="hint">{T.noCandidates}</span>}
    </Modal>
  );
}

/** 選択肢(文字列)を一つ選ぶ欄。プルダウンの代わりに、ボタンからモーダルで選ぶ。 */
export function ChoicePicker<V>({ title, choices, value, onChange, emptyLabel, placeholder, disabled }: {
  title: string;
  choices: Choice<V>[];
  value: V | null;
  onChange: (value: V | null) => void;
  emptyLabel?: string;
  /** 値が無いときにボタンへ出す文字 */
  placeholder: string;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const current = choices.find((c) => c.value === value);
  return (
    <>
      <PickerToggle label={current?.label ?? placeholder} empty={!current} onClick={() => setOpen(true)} disabled={disabled} />
      {open && (
        <PickerModal title={title} choices={choices} value={value} onPick={onChange} onClose={() => setOpen(false)} emptyLabel={emptyLabel} />
      )}
    </>
  );
}
