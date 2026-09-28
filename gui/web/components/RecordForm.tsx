"use client";

import { useState, type ReactNode } from "react";
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
  /** 見出しの名前(label_column の欄。クリックで直せる)の右に添えるもの(テーブル名・id など) */
  titleNote?: ReactNode;
  /** 見出しの下に置くもの(保存の結果・エラーなど) */
  header?: ReactNode;
  /** 左の欄の末尾に置くもの(関連の一覧など) */
  side?: ReactNode;
  /** 左の欄の一番下に置く保存系のボタン列 */
  actions?: ReactNode;
  /** 「AI で作成」のパネル。本文の欄の下に置き、本文が空でカーソルも無いあいだだけ右側の大半を使って開く */
  generate?: ReactNode;
};

/** 見出しとして出す名前の欄。クリックすると入力欄になり、Enter・Esc・フォーカスが外れると見出しに戻る。 */
function EditableTitle({ value, placeholder, onChange }: { value: string; placeholder: string; onChange: (value: string) => void }) {
  const [editing, setEditing] = useState(false);
  if (editing) {
    return (
      <input
        type="text"
        className="title-input"
        autoFocus
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        onBlur={() => setEditing(false)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === "Escape") e.currentTarget.blur();
        }}
      />
    );
  }
  return (
    <h1 className={`title-editable ${value ? "" : "empty"}`} title={T.record.clickToEdit} onClick={() => setEditing(true)}>
      {value || placeholder}
    </h1>
  );
}

function isBlank(value: unknown): boolean {
  return value === null || value === undefined || (typeof value === "string" && value.trim() === "");
}

/** スキーマの列の情報(`/api/tables`)から組み立てるフォーム。値は親が持つ。
 * 本文(section の列)は右半分で、他の欄と side・actions は左半分に並べる。左右それぞれが独立にスクロールする。狭い画面では縦に積む。 */
export default function RecordForm({ meta, value, onChange, mode, titleNote, header, side, actions, generate }: Props) {
  const set = (key: string, v: unknown) => onChange({ ...value, [key]: v });
  const columns = meta.columns.filter((column) => (mode === "create" ? column.key !== "id" && !column.readonly : !column.create_only));
  // 名前の欄は見出しで直し、id は見出しの横に出すので、フォームには並べない
  const titleColumn = columns.find((c) => c.key === meta.label_column && c.type === "string" && !c.section && !c.readonly);
  const plain = columns.filter((c) => !c.section && c !== titleColumn && c.key !== "id");
  const sections = columns.filter((c) => c.section && !c.side);
  const sideSections = columns.filter((c) => c.section && c.side);
  const [textFocused, setTextFocused] = useState(false);
  // 本文を書いている(カーソルがある・中身がある)あいだは閉じる。閉じていても帯を押せば開ける
  const [forceOpen, setForceOpen] = useState(false);
  const writing = textFocused || sections.some((c) => !isBlank(value[c.key]));
  const generateOpen = !writing || forceOpen;

  return (
    <div className={`record ${sections.length ? "split" : ""}`}>
      <div className="record-side">
        <div className="record-header">
          <div className="title-line">
            {titleColumn && (
              <EditableTitle
                value={(value[titleColumn.key] as string | null) ?? ""}
                placeholder={titleColumn.required ? `${titleColumn.label} (${T.required})` : titleColumn.label}
                onChange={(v) => set(titleColumn.key, v === "" && titleColumn.nullable ? null : v)}
              />
            )}
            {titleNote && <span className="hint">{titleNote}</span>}
          </div>
          {header}
        </div>
        <div className="form">
          {plain.map((column) => (
            <div key={column.key} className={`field ${column.type === "id_list" || column.type === "json" ? "wide" : ""}`}>
              <label title={column.comment ?? ""}>
                {column.label}
                <span className="key">{column.key}</span>
                {column.required && <span className="hint">{T.required}</span>}
              </label>
              <FieldInput column={column} value={value[column.key]} onChange={(v) => set(column.key, v)} />
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
        {sideSections.map((column) => (
          <div key={column.key} className="field section side" style={{ marginTop: "1rem" }}>
            <label title={column.comment ?? ""}>
              {column.label}
              <span className="key">{column.key}</span>
            </label>
            <FieldInput column={column} value={value[column.key]} onChange={(v) => set(column.key, v)} />
          </div>
        ))}
        {sections.length === 0 && generate && <div className="generate-body">{generate}</div>}
        {actions && <div className="record-actions">{actions}</div>}
      </div>
      {sections.length > 0 && (
        <div className="record-text">
          {sections.map((column) => (
            <div
              key={column.key}
              className="field section"
              onFocus={() => {
                setTextFocused(true);
                setForceOpen(false);
              }}
              onBlur={(e) => {
                if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setTextFocused(false);
              }}
            >
              <label title={column.comment ?? ""}>
                {column.label}
                <span className="key">{column.key}</span>
              </label>
              <FieldInput column={column} value={value[column.key]} onChange={(v) => set(column.key, v)} />
            </div>
          ))}
          {generate && (
            <div className={`record-generate ${generateOpen ? "open" : "closed"}`}>
              {writing && (
                <button type="button" className="generate-toggle" onClick={() => setForceOpen(!forceOpen)}>
                  {T.generate.toggle(generateOpen)}
                </button>
              )}
              <div className="generate-body">{generate}</div>
            </div>
          )}
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
