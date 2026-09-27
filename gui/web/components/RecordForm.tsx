"use client";

import type { ReactNode } from "react";
import type { Rec, TableMeta } from "@/lib/api";
import ChildListEditor, { type ExtraColumn } from "./ChildListEditor";
import FieldInput from "./FieldInput";
import { ageAt } from "@/lib/stamp";
import { T } from "@/lib/text";

/** 期間ごとの居場所・パラメータの開始・終了それぞれの隣に、その時点の人物の年齢を出す(人物の start が生年)。 */
function ageColumns(birth: unknown): ExtraColumn[] {
  return [
    { key: "start_age", after: "start", label: T.record.ageAt, render: (row) => formatAge(ageAt(birth, row.start)) },
    { key: "end_age", after: "end", label: T.record.ageAt, render: (row) => formatAge(ageAt(birth, row.end)) },
  ];
}

function formatAge(age: number | null): string {
  return age === null ? "—" : String(age);
}

type Props = {
  meta: TableMeta;
  value: Rec;
  onChange: (value: Rec) => void;
  mode: "create" | "edit";
  /** 左の欄の末尾に置くもの(関連の一覧など) */
  side?: ReactNode;
  /** 左の欄の一番下に置く保存系のボタン列 */
  actions?: ReactNode;
};

/** スキーマの列の情報(`/api/tables`)から組み立てるフォーム。値は親が持つ。
 * 本文(section の列)は右半分で、他の欄と side・actions は左半分に並べる。左右それぞれが独立にスクロールする。狭い画面では縦に積む。 */
export default function RecordForm({ meta, value, onChange, mode, side, actions }: Props) {
  const set = (key: string, v: unknown) => onChange({ ...value, [key]: v });
  const columns = meta.columns.filter((column) => (mode === "create" ? column.key !== "id" && !column.readonly : !column.create_only));
  const plain = columns.filter((c) => !c.section);
  const sections = columns.filter((c) => c.section);

  return (
    <div className={`record ${sections.length ? "split" : ""}`}>
      <div className="record-side">
        <div className="form">
          {plain.map((column) => (
            <div key={column.key} className={`field ${column.type === "id_list" || column.type === "json" ? "wide" : ""}`}>
              <label title={column.comment ?? ""}>
                {column.label}
                <span className="key">{column.key}</span>
                {column.required && <span className="hint">{T.required}</span>}
              </label>
              <FieldInput column={column} value={value[column.key]} onChange={(v) => set(column.key, v)} />
              {column.comment && column.comment !== column.label && <span className="hint">{column.comment}</span>}
            </div>
          ))}
        </div>
        {meta.child_lists.map((child) => (
          <div key={child.name} className="field wide" style={{ marginTop: "1rem" }}>
            <label>
              {child.label}
              <span className="key">{child.name}</span>
            </label>
            <ChildListEditor
              meta={child}
              rows={(value[child.name] as Rec[] | undefined) ?? []}
              onChange={(rows) => set(child.name, rows)}
              extraColumns={child.name === "places" || child.name === "parameters" ? ageColumns(value.start) : undefined}
              readOnly={child.name === "places" || child.name === "parameters"}
            />
          </div>
        ))}
        {side}
        {actions && <div className="record-actions">{actions}</div>}
      </div>
      {sections.length > 0 && (
        <div className="record-text">
          {sections.map((column) => (
            <div key={column.key} className="field section">
              <label title={column.comment ?? ""}>
                {column.label}
                <span className="key">{column.key}</span>
              </label>
              <FieldInput column={column} value={value[column.key]} onChange={(v) => set(column.key, v)} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** 足すときの初期値。boolean は false、それ以外は空。 */
export function emptyRecord(meta: TableMeta): Rec {
  const record: Rec = {};
  for (const column of meta.columns) {
    if (column.key === "id" || column.readonly) continue;
    record[column.key] = column.type === "boolean" ? false : column.type === "id_list" ? [] : null;
  }
  for (const child of meta.child_lists) record[child.name] = [];
  return record;
}
