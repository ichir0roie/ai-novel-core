"use client";

import { useEffect, useImperativeHandle, useRef, useState, type Ref } from "react";
import EpisodeMaterials from "@/components/EpisodeMaterials";
import { getRecord, updateRecord, type Rec } from "@/lib/api";
import { useSaveShortcut } from "@/lib/saving";
import { T } from "@/lib/text";

export type EpisodeWriterHandle = {
  /** カーソルの位置(選んだ範囲はそれと置き換える)に、行として差し込む */
  insert: (text: string) => void;
};

type Props = {
  episodeId: number;
  /** 本文を送る先。省けば話の `main_text` を直す */
  save?: (text: string) => Promise<unknown>;
  /**
   * 語り部が本文に書き足している間は true にする(作者と語り部が代わる代わる書くとき)。true の間は書けず、本文を読み直し続ける。
   * 省けば、いつでも書ける
   */
  locked?: boolean;
  ref?: Ref<EpisodeWriterHandle>;
};

const SYNC_MS = 3000;

const saveMainText = (episodeId: number) => (text: string) => updateRecord("episode", episodeId, { main_text: text });

/** 話の本文を自分で書く欄。上に材料を添え、本文(`main_text`)を Save(Ctrl+S)で保存する。 */
export default function EpisodeWriter({ episodeId, save: send = saveMainText(episodeId), locked, ref }: Props) {
  const [episode, setEpisode] = useState<Rec | null>(null);
  const [text, setText] = useState("");
  // 最後に保存へ送った本文。保存すると改行が整えられて返るが、書いている欄は置き換えない(カーソルと打ちかけの文を崩さない)
  const [sent, setSent] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  // 語り部の番が明けて、語り部の書き足した本文を読み直している間。読み終えるまで書かせない
  const [syncing, setSyncing] = useState(false);
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

  // 語り部の番の間は本文を読み直し続け、番が明けたら一度読み直してから書かせる(語り部の書き足しを古い本文で上書きしない)
  useEffect(() => {
    if (locked == null) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;
    if (!locked) setSyncing(true);
    const pull = async () => {
      try {
        const result = await getRecord("episode", episodeId);
        const main = String(result.record.main_text ?? "");
        const { text: body, sent: last } = latest.current;
        if (!stopped && body === last && main !== last) {
          setSent(main);
          setText(main);
        }
      } catch (e) {
        if (!stopped) setError(e instanceof Error ? e.message : String(e));
      }
      if (stopped) return;
      if (locked) timer = setTimeout(() => void pull(), SYNC_MS);
      else setSyncing(false);
    };
    void pull();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [episodeId, locked]);

  const readOnly = Boolean(locked) || syncing;
  const dirty = sent != null && text !== sent;

  const save = async () => {
    const { text: body, sent: last, saving: busy, send: post } = latest.current;
    if (last == null || body === last || busy || readOnly) return;
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

  useSaveShortcut(() => void save());

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
      </div>
      {error && <div className="status error">{error}</div>}
      <textarea
        ref={areaRef}
        className="writer-text"
        value={text}
        placeholder={T.writer.placeholder}
        readOnly={readOnly}
        onChange={(e) => setText(e.target.value)}
      />
      <div className="writer-footer">
        <span className={`meta${dirty ? " writer-unsaved" : ""}`}>
          {readOnly
            ? T.writer.locked
            : saving
              ? T.writer.saving
              : dirty
                ? T.writer.unsaved
                : savedAt
                  ? T.writer.savedAt(savedAt)
                  : T.writer.saved}
        </span>
        <button
          className={dirty ? "primary" : undefined}
          onClick={() => void save()}
          disabled={!dirty || saving || readOnly}
          title={T.writer.saveHint}
        >
          {T.writer.save}
        </button>
      </div>
    </div>
  );
}
