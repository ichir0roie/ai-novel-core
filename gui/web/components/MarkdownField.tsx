"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AutoGrowTextarea } from "./FieldInput";
import { T } from "@/lib/text";

type Props = {
  value: string | null;
  onChange: (value: string) => void;
  /** 枠いっぱい(既定)ではなく、中身の行数ぶんの高さにする(すぐ下に一覧を続けて出す欄向け)。 */
  autoHeight?: boolean;
  /** 初めは枠に収まる行数だけを出し、クリックで全文を開閉する。編集は編集ボタンからだけ入る。 */
  collapsible?: boolean;
};

/** 本文の欄。表示中はマークダウンのプレビュー、クリックすると編集(textarea)に切り替わり、
 * フォーカスが外れるとまたプレビューに戻る。 */
export default function MarkdownField({ value, onChange, autoHeight, collapsible }: Props) {
  const [editing, setEditing] = useState(false);
  const text = value ?? "";

  if (editing) {
    return autoHeight || collapsible ? (
      <AutoGrowTextarea className="section" autoFocus value={text} onChange={onChange} onBlur={() => setEditing(false)} />
    ) : (
      <textarea
        className="section"
        autoFocus
        value={text}
        onChange={(e) => onChange(e.target.value)}
        onBlur={() => setEditing(false)}
      />
    );
  }
  if (collapsible) return <CollapsiblePreview text={text} onEdit={() => setEditing(true)} />;
  return (
    <div className={`section markdown-preview ${autoHeight ? "auto" : ""}`} onClick={() => setEditing(true)}>
      {text === "" ? (
        <span className="hint">{T.record.emptySection}</span>
      ) : (
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
      )}
    </div>
  );
}

/** 畳んだプレビュー。はみ出すかは幅と中身で変わるので、描いたあとの高さで見る。 */
function CollapsiblePreview({ text, onEdit }: { text: string; onEdit: () => void }) {
  const [open, setOpen] = useState(false);
  const [clipped, setClipped] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || open) return;
    const measure = () => setClipped(el.scrollHeight > el.clientHeight + 1);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [text, open]);
  const empty = text === "";
  const toggle = !empty && (open || clipped);

  return (
    <div className="markdown-collapsible">
      <div
        ref={ref}
        className={`section markdown-preview auto ${open ? "open" : "closed"} ${clipped && !open ? "clipped" : ""} ${toggle ? "toggle" : ""}`}
        title={toggle ? (open ? T.record.collapse : T.record.expand) : undefined}
        onClick={() => {
          if (empty) onEdit();
          else if (toggle) setOpen(!open);
        }}
      >
        {empty ? <span className="hint">{T.record.emptySection}</span> : <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>}
      </div>
      <button type="button" className="ghost markdown-edit" onClick={onEdit}>
        {T.record.edit}
      </button>
    </div>
  );
}
