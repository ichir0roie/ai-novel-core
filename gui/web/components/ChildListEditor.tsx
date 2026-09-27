"use client";

import type { ChildListMeta, Rec } from "@/lib/api";
import FieldInput from "./FieldInput";

type Props = {
  meta: ChildListMeta;
  rows: Rec[];
  onChange: (rows: Rec[]) => void;
};

/** 子の行(期間ごとのパラメータなど)。並びで行が決まるので、行の入れ替えはしない。 */
export default function ChildListEditor({ meta, rows, onChange }: Props) {
  const update = (index: number, key: string, value: unknown) =>
    onChange(rows.map((row, i) => (i === index ? { ...row, [key]: value } : row)));
  const remove = (index: number) => onChange(rows.filter((_, i) => i !== index));
  const add = () => onChange([...rows, Object.fromEntries(meta.columns.map((c) => [c.key, c.type === "boolean" ? false : null]))]);

  return (
    <div className="childlist">
      <div className="scroll-x">
        <table>
          <thead>
            <tr>
              <th />
              {meta.columns.map((column) => (
                <th key={column.key} title={column.comment ?? column.key}>
                  {column.label}
                </th>
              ))}
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index}>
                <td className="rowhead">{index + 1}</td>
                {meta.columns.map((column) => (
                  <td key={column.key}>
                    <FieldInput column={column} value={row[column.key]} onChange={(v) => update(index, column.key, v)} compact />
                  </td>
                ))}
                <td>
                  <button type="button" className="ghost" onClick={() => remove(index)} title="この行を消す">
                    ×
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button type="button" onClick={add} style={{ marginTop: "0.4rem" }}>
        + 行を足す
      </button>
    </div>
  );
}
