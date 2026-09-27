"use client";

import { Fragment, type ReactNode } from "react";
import type { ChildListMeta, Rec } from "@/lib/api";
import FieldInput from "./FieldInput";
import { T } from "@/lib/text";

/** スキーマに無い、行から計算するだけの読み取り専用の列(居場所の期間から出す年齢など)。指定した列の右に挿む。 */
export type ExtraColumn = { key: string; label: string; after: string; render: (row: Rec) => ReactNode };

type Props = {
  meta: ChildListMeta;
  rows: Rec[];
  onChange: (rows: Rec[]) => void;
  extraColumns?: ExtraColumn[];
};

/** 子の行(期間ごとのパラメータなど)。並びで行が決まるので、行の入れ替えはしない。 */
export default function ChildListEditor({ meta, rows, onChange, extraColumns = [] }: Props) {
  const update = (index: number, key: string, value: unknown) =>
    onChange(rows.map((row, i) => (i === index ? { ...row, [key]: value } : row)));
  const remove = (index: number) => onChange(rows.filter((_, i) => i !== index));
  const add = () => onChange([...rows, Object.fromEntries(meta.columns.map((c) => [c.key, c.type === "boolean" ? false : null]))]);
  const extrasAfter = (key: string) => extraColumns.filter((extra) => extra.after === key);

  return (
    <div className="childlist">
      <div className="scroll-x">
        <table>
          <thead>
            <tr>
              <th />
              {meta.columns.map((column) => (
                <Fragment key={column.key}>
                  <th title={column.comment ?? column.key}>{column.label}</th>
                  {extrasAfter(column.key).map((extra) => (
                    <th key={extra.key} className="hint">
                      {extra.label}
                    </th>
                  ))}
                </Fragment>
              ))}
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index}>
                <td className="rowhead">{index + 1}</td>
                {meta.columns.map((column) => (
                  <Fragment key={column.key}>
                    <td>
                      <FieldInput column={column} value={row[column.key]} onChange={(v) => update(index, column.key, v)} compact />
                    </td>
                    {extrasAfter(column.key).map((extra) => (
                      <td key={extra.key} className="readonly">
                        {extra.render(row)}
                      </td>
                    ))}
                  </Fragment>
                ))}
                <td>
                  <button type="button" className="ghost" onClick={() => remove(index)} title={T.childList.removeRow}>
                    ×
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button type="button" onClick={add} style={{ marginTop: "0.4rem" }}>
        {T.childList.addRow}
      </button>
    </div>
  );
}
