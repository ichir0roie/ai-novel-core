"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { T } from "@/lib/text";

type Props = {
  value: string | null;
  onChange: (value: string) => void;
};

/** 本文の欄。表示中はマークダウンのプレビュー、クリックすると編集(textarea)に切り替わり、
 * フォーカスが外れるとまたプレビューに戻る。 */
export default function MarkdownField({ value, onChange }: Props) {
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
    <div className="section markdown-preview" onClick={() => setEditing(true)}>
      {text === "" ? (
        <span className="hint">{T.record.emptySection}</span>
      ) : (
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
      )}
    </div>
  );
}
