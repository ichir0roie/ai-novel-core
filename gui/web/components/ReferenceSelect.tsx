"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import Modal from "./Modal";
import { PickerModal, PickerToggle } from "./Picker";
import { getOptions, type Option } from "@/lib/api";
import { T } from "@/lib/text";

const cache = new Map<string, Promise<Option[]>>();
// 取り置きを捨てたとき、いま出ている選択欄にも読み直させる
const listeners = new Set<(table: string | null) => void>();

/** 参照先のテーブルの選択肢。テーブルごとに一度だけ読み、取り置きを捨てられたら読み直す。 */
export function useOptions(table: string | null | undefined): Option[] {
  const [options, setOptions] = useState<Option[]>([]);
  const [version, setVersion] = useState(0);
  useEffect(() => {
    const listener = (changed: string | null) => {
      if (changed === null || changed === table) setVersion((v) => v + 1);
    };
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }, [table]);
  useEffect(() => {
    if (!table) return;
    if (!cache.has(table)) cache.set(table, getOptions(table).then((r) => r.items));
    let alive = true;
    cache.get(table)!.then((items) => alive && setOptions(items)).catch(() => cache.delete(table));
    return () => {
      alive = false;
    };
  }, [table, version]);
  return options;
}

export function invalidateOptions(table: string) {
  cache.delete(table);
  for (const listener of listeners) listener(table);
}

/** AI の生成は他のテーブルにも行を足す(話のプロット補完が人物・場所を作るなど)ので、全部の取り置きを捨てる。 */
export function invalidateAllOptions() {
  cache.clear();
  for (const listener of listeners) listener(null);
}

type Props = {
  table: string;
  value: number | null;
  nullable: boolean;
  onChange: (value: number | null) => void;
  disabled?: boolean;
  // 絞り込み欄が空のときに出す選択肢の id。null・省略なら全部出す
  defaultIds?: number[] | null;
  // 選ぶモーダルの見出し(欄の名前)
  title?: string;
};

/** 参照先の行を一つ選ぶ欄。ボタンに今の行を出し、押すとモーダルで大きく並べて選ぶ。 */
export default function ReferenceSelect({ table, value, nullable, onChange, disabled, defaultIds, title }: Props) {
  const options = useOptions(table);
  const [open, setOpen] = useState(false);
  const choices = useMemo(() => options.map((o) => ({ value: o.id, label: `${o.id}: ${o.label}` })), [options]);
  const current = choices.find((c) => c.value === value);

  return (
    <div className="picker">
      <PickerToggle
        label={current?.label ?? (value !== null ? `id ${value}` : nullable ? T.none : T.select)}
        empty={value === null}
        onClick={() => setOpen(true)}
        disabled={disabled}
      />
      {value !== null && <RecordLink table={table} id={value} />}
      {open && (
        <PickerModal
          title={title ?? T.select}
          choices={choices}
          value={value}
          onPick={onChange}
          onClose={() => setOpen(false)}
          emptyLabel={nullable ? T.none : undefined}
          suggested={defaultIds}
        />
      )}
    </div>
  );
}

/** 選んだ行のページへ飛ぶリンク。選択欄の横に置く。 */
export function RecordLink({ table, id, label }: { table: string; id: number; label?: string }) {
  return (
    <Link href={`/tables/${table}/${id}`} className="record-link" title={T.openRecord}>
      {label ?? T.openRecord}
    </Link>
  );
}

type MultiProps = {
  table: string;
  value: number[];
  onChange: (value: number[]) => void;
  title?: string;
};

/** 参照先の行をいくつか選ぶ欄。ボタンの横に選んだ名前を並べ、押すとモーダルのチェック欄で選ぶ。 */
export function ReferenceMultiSelect({ table, value, onChange, title }: MultiProps) {
  const options = useOptions(table);
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const q = filter.trim();
  const selected = options.filter((o) => value.includes(o.id));
  const shown = options.filter((o) => !q || o.label.includes(q) || String(o.id) === q || value.includes(o.id));
  const toggle = (id: number) => onChange(value.includes(id) ? value.filter((v) => v !== id) : [...value, id]);
  return (
    <div className="picker">
      <PickerToggle label={T.picker.count(value.length)} empty={value.length === 0} onClick={() => setOpen(true)} />
      <span className="picker-summary">{selected.map((o) => o.label).join(" / ")}</span>
      {open && (
        <Modal
          title={title ?? T.select}
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
              <label key={o.id} className={`picker-option ${value.includes(o.id) ? "selected" : ""}`}>
                <input type="checkbox" checked={value.includes(o.id)} onChange={() => toggle(o.id)} />
                {o.id}: {o.label}
              </label>
            ))}
          </div>
          {shown.length === 0 && <span className="hint">{T.noCandidates}</span>}
        </Modal>
      )}
    </div>
  );
}
