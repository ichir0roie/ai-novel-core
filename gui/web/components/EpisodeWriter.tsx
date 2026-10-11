"use client";

import { useEffect, useImperativeHandle, useRef, useState, type Ref } from "react";
import EpisodeMaterials from "@/components/EpisodeMaterials";
import { getRecord, updateRecord, type Rec } from "@/lib/api";
import { claudeSessionUrl } from "@/lib/claude";
import { T } from "@/lib/text";

/** 書いている本文を保存する間隔 */
const AUTOSAVE_MS = 5000;

export type EpisodeWriterHandle = {
  /** カーソルの位置(選んだ範囲はそれと置き換える)に、行として差し込む */
  insert: (text: string) => void;
};

type Props = {
  episodeId: number;
  ref?: Ref<EpisodeWriterHandle>;
};

/** 話の本文を自分で書く欄。上に材料を添え、本文(`main_text`)だけを 5 秒ごとに保存する。 */
export default function EpisodeWriter({ episodeId, ref }: Props) {
  const [episode, setEpisode] = useState<Rec | null>(null);
  const [text, setText] = useState("");
  // 最後に保存へ送った本文。保存すると改行が整えられて返るが、書いている欄は置き換えない(カーソルと打ちかけの文を崩さない)
  const [sent, setSent] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const areaRef = useRef<HTMLTextAreaElement>(null);
  // 差し込んだあとのカーソルの位置。値が描き直されてから置く
  const caret = useRef<number | null>(null);
  // 保存はタイマーと離れるときにも呼ぶので、描画をまたいで今の値を持つ
  const latest = useRef({ text: "", sent: null as string | null, saving: false });
  useEffect(() => {
    latest.current = { text, sent, saving };
  }, [text, sent, saving]);

  useEffect(() => {
    let alive = true;
    getRecord("episode", episodeId)
      .then((result) => {
        if (!alive) return;
        const main = String(result.record.main_text ?? "");
        setEpisode(result.record);
        setSent(main);
        setText(main);
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [episodeId]);

  const dirty = sent != null && text !== sent;

  const save = async () => {
    const { text: body, sent: last, saving: busy } = latest.current;
    if (last == null || body === last || busy) return;
    setSaving(true);
    try {
      await updateRecord("episode", episodeId, { main_text: body });
      setSent(body);
      setSavedAt(new Date().toLocaleTimeString());
      setError(null);
    } catch (e) {
      // 次の間隔でまた送る
      setError(T.writer.saveFailed(e instanceof Error ? e.message : String(e)));
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => {
    const timer = setInterval(() => void save(), AUTOSAVE_MS);
    return () => {
      clearInterval(timer);
      // 欄を閉じたときに、まだ送っていない分を送る(返りは待たない)
      const { text: body, sent: last } = latest.current;
      if (last != null && body !== last) void updateRecord("episode", episodeId, { main_text: body });
    };
    // save は latest から今の値を読むので、間隔を張り直さない
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [episodeId]);

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

  if (episode == null || sent == null) {
    return <div className="writer">{error ? <div className="status error">{error}</div> : <div className="status info">{T.loading}</div>}</div>;
  }

  return (
    <div className="writer">
      <EpisodeMaterials episode={episode} />
      <div className="toolbar writer-toolbar">
        <span className="meta">{T.writer.letters(text.length)}</span>
        <span className="meta">
          {saving ? T.writer.saving : dirty ? T.writer.unsaved : savedAt ? T.writer.savedAt(savedAt) : T.writer.autosave}
        </span>
        <span className="spacer" />
        {/* 後工程は保存した本文を読むので、送っていない分があるうちは開かない */}
        <a
          className={`button-link${dirty || saving || text.trim() === "" ? " disabled" : ""}`}
          href={claudeSessionUrl(T.writer.claudePromptFinish(String(episodeId)))}
          target="_blank"
          rel="noopener noreferrer"
          title={T.writer.finishHint}
          aria-disabled={dirty || saving || text.trim() === ""}
          onClick={(e) => (dirty || saving || text.trim() === "") && e.preventDefault()}
        >
          {T.writer.finish}
        </a>
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
