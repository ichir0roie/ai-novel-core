"use client";

import { useState } from "react";
import type { ColumnMeta } from "@/lib/api";
import MarkdownField from "./MarkdownField";
import PlainTextField from "./PlainTextField";
import ReferenceSelect, { ReferenceMultiSelect } from "./ReferenceSelect";
import StampInput from "./StampInput";
import TreeReferenceSelect from "./TreeReferenceSelect";
import { T } from "@/lib/text";

// 親子を持つテーブル(場所・アイデア)は、プルダウンではなくツリーで選ばせる
const TREE_REFERENCE_TABLES = new Set(["location", "idea"]);

/** 子の行の列のうち、自由記述で長い文になりがちな列名(体格・口調・方言・呼び名の注釈など)。
 * 単純な一行入力ではなく textarea にする。読み取り専用表示(ChildListEditor)でも同じ集合を
 * 「1 項目 1 行のまま出す」列として使うので、ここで共有する。 */
export const CHILD_FREEFORM_TEXT_KEYS = new Set(["build", "tone", "dialect", "detail"]);

type Props = {
  column: ColumnMeta;
  value: unknown;
  onChange: (value: unknown) => void;
  compact?: boolean;
  disabled?: boolean;
};

const STATUS_CLASS: Record<string, string> = { 承認: "approve", 非承認: "reject", 未確認: "pending" };

function JsonInput({ value, onChange, disabled }: { value: unknown; onChange: (v: unknown) => void; disabled?: boolean }) {
  const [text, setText] = useState(value == null ? "" : JSON.stringify(value, null, 2));
  const [error, setError] = useState<string | null>(null);
  // 親が値を差し替えたら(読み直し・戻す)、表示中の文字列も追従させる
  const [shown, setShown] = useState(value);
  if (shown !== value) {
    setShown(value);
    setText(value == null ? "" : JSON.stringify(value, null, 2));
  }
  const commit = () => {
    if (text.trim() === "") {
      setError(null);
      onChange(null);
      return;
    }
    try {
      onChange(JSON.parse(text));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };
  return (
    <>
      <textarea className="mono" value={text} onChange={(e) => setText(e.target.value)} onBlur={commit} disabled={disabled} />
      {error && <span className="error">{T.invalidJson(error)}</span>}
    </>
  );
}

export default function FieldInput({ column, value, onChange, compact, disabled }: Props) {
  const readonly = disabled || column.readonly;
  if (readonly) {
    return <div className="readonly">{value == null ? "—" : Array.isArray(value) || typeof value === "object" ? JSON.stringify(value) : String(value)}</div>;
  }

  if (column.type === "id_list" && column.references) {
    return <ReferenceMultiSelect table={column.references} value={(value as number[] | null) ?? []} onChange={onChange} />;
  }
  if (column.references && TREE_REFERENCE_TABLES.has(column.references)) {
    return <TreeReferenceSelect table={column.references} value={(value as number | null) ?? null} nullable={column.nullable} onChange={onChange} />;
  }
  if (column.references) {
    return <ReferenceSelect table={column.references} value={(value as number | null) ?? null} nullable={column.nullable} onChange={onChange} />;
  }
  if (column.type === "confirm") {
    return (
      <div className="segment">
        {(column.choices ?? []).map((choice) => (
          <button key={choice} type="button" className={`${value === choice ? "on" : ""} ${STATUS_CLASS[choice] ?? ""}`} onClick={() => onChange(choice)}>
            {choice}
          </button>
        ))}
      </div>
    );
  }
  if (column.choices) {
    // 値がまだ無ければ、選択肢の既定値(column.default)を初期選択にする(何も選ばず実行すれば、
    // 入口側もこの既定値を使うので見た目と動きが揃う)
    const shown = (value as string | null) ?? column.default ?? "";
    return (
      <select value={shown} onChange={(e) => onChange(e.target.value === "" ? null : e.target.value)}>
        <option value="">{column.nullable ? column.comment ?? T.none : T.select}</option>
        {column.choices.map((choice) => (
          <option key={choice} value={choice}>
            {choice === column.default ? `${choice} (default)` : choice}
          </option>
        ))}
      </select>
    );
  }
  if (column.type === "boolean") {
    return (
      <label className="check">
        <input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} />
        {value ? T.yes : T.no}
      </label>
    );
  }
  if (column.type === "integer" || column.type === "number") {
    return (
      <input
        type="number"
        step={column.type === "integer" ? 1 : "any"}
        value={value == null ? "" : String(value)}
        onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
      />
    );
  }
  if (column.type === "json") {
    return <JsonInput value={value} onChange={onChange} />;
  }
  if (column.type === "stamp") {
    return <StampInput value={(value as string | null) ?? null} onChange={onChange} disabled={disabled} />;
  }
  if (column.section && !compact) {
    return column.markdown === false ? (
      <PlainTextField value={(value as string | null) ?? null} onChange={onChange} />
    ) : (
      <MarkdownField value={(value as string | null) ?? null} onChange={onChange} />
    );
  }
  if (!compact && CHILD_FREEFORM_TEXT_KEYS.has(column.key)) {
    return (
      <textarea
        value={(value as string | null) ?? ""}
        onChange={(e) => onChange(e.target.value === "" && column.nullable ? null : e.target.value)}
      />
    );
  }
  return <input type="text" value={(value as string | null) ?? ""} onChange={(e) => onChange(e.target.value === "" && column.nullable ? null : e.target.value)} />;
}
