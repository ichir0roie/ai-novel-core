"use client";

import { useEffect, useImperativeHandle, useRef, useState, type Ref } from "react";
import { getRecord, updateRecord } from "@/lib/api";
import { T } from "@/lib/text";

export type EpisodeWriterHandle = {
  /** カーソルの位置(選んだ範囲はそれと置き換える)に、行として差し込む */
  insert: (text: string) => void;
};

type Props = {
  episodeId: number;
  ref?: Ref<EpisodeWriterHandle>;
};

/** 話の本文を自分で書く欄。プロットを上に添え、本文(`main_text`)だけを保存する。 */
export default function EpisodeWriter({ episodeId, ref }: Props) {
  const [plot, setPlot] = useState<string | null>(null);
  const [savedText, setSavedText] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const areaRef = useRef<HTMLTextAreaElement>(null);
  // 差し込んだあとのカーソルの位置。値が描き直されてから置く
  const caret = useRef<number | null>(null);

  useEffect(() => {
    let alive = true;
    getRecord("episode", episodeId)
      .then((result) => {
        if (!alive) return;
        const main = String(result.record.main_text ?? "");
        setPlot(String(result.record.plot_text ?? ""));
        setSavedText(main);
        setText(main);
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [episodeId]);

  const dirty = savedText != null && text !== savedText;

  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  useEffect(() => {
    const area = areaRef.current;
    if (area && caret.current != null) {
      area.focus();
      area.setSelectionRange(caret.current, caret.current);
      caret.current = null;
    }
  }, [text]);

  useImperativeHandle(
    ref,
    () => ({
      insert: (line: string) => {
        const area = areaRef.current;
        const start = area?.selectionStart ?? text.length;
        const end = area?.selectionEnd ?? text.length;
        const before = text.slice(0, start);
        const after = text.slice(end);
        // 前後の文と同じ行に繋がらないよう、段落の頭と終わりで切る
        const head = before === "" || before.endsWith("\n") ? "" : "\n";
        const tail = after.startsWith("\n") ? "" : "\n";
        const inserted = head + line + tail;
        caret.current = start + inserted.length;
        setText(before + inserted + after);
      },
    }),
    [text],
  );

  const save = async () => {
    if (!dirty || busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = await updateRecord("episode", episodeId, { main_text: text });
      const main = String(result.record.main_text ?? "");
      setSavedText(main);
      setText(main);
      setSavedAt(new Date().toLocaleTimeString());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (savedText == null) {
    return <div className="writer">{error ? <div className="status error">{error}</div> : <div className="status info">{T.loading}</div>}</div>;
  }

  return (
    <div className="writer">
      {plot !== "" && (
        <details className="writer-plot" open>
          <summary>{T.writer.plot}</summary>
          <div className="writer-plot-text">{plot}</div>
        </details>
      )}
      <div className="toolbar writer-toolbar">
        <span className="meta">{T.writer.letters(text.length)}</span>
        <span className="meta">{dirty ? T.writer.unsaved : savedAt ? T.writer.savedAt(savedAt) : T.writer.noChanges}</span>
        <span className="spacer" />
        <button onClick={() => setText(savedText)} disabled={busy || !dirty}>
          {T.writer.revert}
        </button>
        <button className="primary" onClick={() => void save()} disabled={busy || !dirty} title={T.writer.saveHint}>
          {T.writer.save}
        </button>
      </div>
      {error && <div className="status error">{error}</div>}
      <textarea
        ref={areaRef}
        className="writer-text"
        value={text}
        placeholder={T.writer.placeholder}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if ((e.ctrlKey || e.metaKey) && e.key === "s") {
            e.preventDefault();
            void save();
          }
        }}
      />
    </div>
  );
}
