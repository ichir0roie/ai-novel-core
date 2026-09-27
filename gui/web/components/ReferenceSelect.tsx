"use client";

import { useEffect, useMemo, useState } from "react";
import { getOptions, type Option } from "@/lib/api";
import { T } from "@/lib/text";

const cache = new Map<string, Promise<Option[]>>();

/** 参照先のテーブルの選択肢。テーブルごとに一度だけ読む。 */
export function useOptions(table: string | null | undefined): Option[] {
  const [options, setOptions] = useState<Option[]>([]);
  useEffect(() => {
    if (!table) return;
    if (!cache.has(table)) cache.set(table, getOptions(table).then((r) => r.items));
    let alive = true;
    cache.get(table)!.then((items) => alive && setOptions(items)).catch(() => cache.delete(table));
    return () => {
      alive = false;
    };
  }, [table]);
  return options;
}

export function invalidateOptions(table: string) {
  cache.delete(table);
}

type Props = {
  table: string;
  value: number | null;
  nullable: boolean;
  onChange: (value: number | null) => void;
  disabled?: boolean;
};

export default function ReferenceSelect({ table, value, nullable, onChange, disabled }: Props) {
  const options = useOptions(table);
  const [filter, setFilter] = useState("");
  const shown = useMemo(() => {
    const q = filter.trim();
    const list = q ? options.filter((o) => o.label.includes(q) || String(o.id) === q) : options;
    // 今の値が絞り込みで消えないようにする
    if (value !== null && !list.some((o) => o.id === value)) {
      const current = options.find((o) => o.id === value);
      if (current) return [current, ...list];
    }
    return list;
  }, [options, filter, value]);

  return (
    <div style={{ display: "flex", gap: "0.3rem" }}>
      <input type="text" placeholder={T.filter} value={filter} onChange={(e) => setFilter(e.target.value)} style={{ maxWidth: "8rem" }} disabled={disabled} />
      <select value={value ?? ""} onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))} disabled={disabled}>
        <option value="">{nullable ? T.none : T.select}</option>
        {shown.map((o) => (
          <option key={o.id} value={o.id}>
            {o.id}: {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

type MultiProps = {
  table: string;
  value: number[];
  onChange: (value: number[]) => void;
};

export function ReferenceMultiSelect({ table, value, onChange }: MultiProps) {
  const options = useOptions(table);
  const [filter, setFilter] = useState("");
  const q = filter.trim();
  const shown = options.filter((o) => !q || o.label.includes(q) || value.includes(o.id));
  const toggle = (id: number) => onChange(value.includes(id) ? value.filter((v) => v !== id) : [...value, id]);
  return (
    <div>
      <input type="text" placeholder={T.filter} value={filter} onChange={(e) => setFilter(e.target.value)} style={{ marginBottom: "0.3rem" }} />
      <div className="multi">
        {shown.map((o) => (
          <label key={o.id}>
            <input type="checkbox" checked={value.includes(o.id)} onChange={() => toggle(o.id)} />
            {o.id}: {o.label}
          </label>
        ))}
        {shown.length === 0 && <span className="hint">{T.noCandidates}</span>}
      </div>
    </div>
  );
}
