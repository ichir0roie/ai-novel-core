"use client";

import type { Rec, TableMeta } from "@/lib/api";
import ChildListEditor from "./ChildListEditor";
import FieldInput from "./FieldInput";

type Props = {
  meta: TableMeta;
  value: Rec;
  onChange: (value: Rec) => void;
  mode: "create" | "edit";
};

/** スキーマの列の情報(`/api/tables`)から組み立てるフォーム。値は親が持つ。 */
export default function RecordForm({ meta, value, onChange, mode }: Props) {
  const set = (key: string, v: unknown) => onChange({ ...value, [key]: v });
  const columns = meta.columns.filter((column) => (mode === "create" ? column.key !== "id" && !column.readonly : !column.create_only));
  const plain = columns.filter((c) => !c.section);
  const sections = columns.filter((c) => c.section);

  return (
    <div>
      <div className="form">
        {plain.map((column) => (
          <div key={column.key} className={`field ${column.type === "id_list" || column.type === "json" ? "wide" : ""}`}>
            <label title={column.comment ?? ""}>
              {column.label}
              <span className="key">{column.key}</span>
              {column.required && <span className="hint">必須</span>}
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
          <ChildListEditor meta={child} rows={(value[child.name] as Rec[] | undefined) ?? []} onChange={(rows) => set(child.name, rows)} />
        </div>
      ))}
      {sections.map((column) => (
        <div key={column.key} className="field wide" style={{ marginTop: "1rem" }}>
          <label title={column.comment ?? ""}>
            {column.label}
            <span className="key">{column.key}</span>
          </label>
          <FieldInput column={column} value={value[column.key]} onChange={(v) => set(column.key, v)} />
        </div>
      ))}
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
