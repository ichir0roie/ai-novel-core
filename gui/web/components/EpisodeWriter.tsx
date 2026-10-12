"use client";

import { useEffect, useImperativeHandle, useRef, useState, type Ref } from "react";
import EpisodeMaterials from "@/components/EpisodeMaterials";
import { getRecord, updateRecord, type Rec } from "@/lib/api";
import { claudeSessionUrl } from "@/lib/claude";
import { T } from "@/lib/text";

export type EpisodeWriterHandle = {
  /** カーソルの位置(選んだ範囲はそれと置き換える)に、行として差し込む */
  insert: (text: string) => void;
  /** 本文の中の `quote` を選んで見せる。見つからなければ false */
  reveal: (quote: string) => boolean;
};

type Props = {
  episodeId: number;
  /** 本文を送る先。省けば話の `main_text` を直す */
  save?: (text: string) => Promise<unknown>;
  ref?: Ref<EpisodeWriterHandle>;
};

const saveMainText = (episodeId: number) => (text: string) => updateRecord("episode", episodeId, { main_text: text });

/** 話の本文を自分で書く欄。上に材料を添え、本文(`main_text`)を Save(Ctrl+S)で保存する。 */
export default function EpisodeWriter({ episodeId, save: send = saveMainText(episodeId), ref }: Props) {
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
  // 保存は欄を閉じるときにも呼ぶので、描画をまたいで今の値を持つ
  const latest = useRef({ text: "", sent: null as string | null, saving: false, send });
  useEffect(() => {
    latest.current = { text, sent, saving, send };
  }, [text, sent, saving, send]);

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
    const { text: body, sent: last, saving: busy, send: post } = latest.current;
    if (last == null || body === last || busy) return;
    setSaving(true);
    try {
      await post(body);
      setSent(body);
      setSavedAt(new Date().toLocaleTimeString());
      setError(null);
    } catch (e) {
      setError(T.writer.saveFailed(e instanceof Error ? e.message : String(e)));
    } finally {
      setSaving(false);
    }
  };

  useEffect(
    () => () => {
      // 欄を閉じたときに、まだ送っていない分を送る(返りは待たない)
      const { text: body, sent: last, send: post } = latest.current;
      if (last != null && body !== last) void post(body);
    },
    [episodeId],
  );

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
      reveal: (quote: string) => {
        const area = areaRef.current;
        const start = quote ? text.indexOf(quote) : -1;
        if (!area || start < 0) return false;
        area.focus();
        area.setSelectionRange(start, start + quote.length);
        // textarea は選んだ所までスクロールしないので、同じ幅と字形の写しに手前の文を流して高さを測る
        const style = getComputedStyle(area);
        const mirror = document.createElement("div");
        for (const name of ["font", "lineHeight", "letterSpacing", "padding", "border", "boxSizing", "tabSize"] as const) {
          mirror.style[name] = style[name];
        }
        Object.assign(mirror.style, { position: "absolute", visibility: "hidden", whiteSpace: "pre-wrap", overflowWrap: "break-word", width: `${area.clientWidth}px` });
        mirror.textContent = text.slice(0, start);
        document.body.append(mirror);
        area.scrollTop = Math.max(0, mirror.scrollHeight - area.clientHeight / 3);
        mirror.remove();
        return true;
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
      <div className="writer-footer">
        <span className={`meta${dirty ? " writer-unsaved" : ""}`}>
          {saving ? T.writer.saving : dirty ? T.writer.unsaved : savedAt ? T.writer.savedAt(savedAt) : T.writer.saved}
        </span>
        <button className={dirty ? "primary" : undefined} onClick={() => void save()} disabled={!dirty || saving} title={T.writer.saveHint}>
          {T.writer.save}
        </button>
      </div>
    </div>
  );
}
