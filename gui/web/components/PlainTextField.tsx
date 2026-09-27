"use client";

import { useState } from "react";
import { T } from "@/lib/text";

type Props = {
  value: string | null;
  onChange: (value: string) => void;
};

/** 本文の欄(マークダウンではなく純粋なテキスト)。表示中はそのままの文字のプレビュー、
 * クリックすると編集(textarea)に切り替わり、フォーカスが外れるとまたプレビューに戻る。 */
export default function PlainTextField({ value, onChange }: Props) {
  const [editing, setEditing] = useState(false);
  const text = value ?? "";

  if (editing) {
    return (
      <textarea
        className="section"
        autoFocus
        value={text}
        onChange={(e) => onChange(e.target.value)}
        onBlur={() => setEditing(false)}
      />
    );
  }
  return (
    <div className="section plain-preview" onClick={() => setEditing(true)}>
      {text === "" ? <span className="hint">{T.record.emptySection}</span> : text}
    </div>
  );
}
