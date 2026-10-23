"use client";

import { useCallback, useEffect, useState } from "react";
import { getRecord, listRecords, updateRecord, type RecordList } from "@/lib/api";
import { T } from "@/lib/text";

// 書き方の行は数十行なので、一覧は一度に全部引く
const ALL = new URLSearchParams({ limit: "500", sort: "id", order: "asc" });

/** 範囲ごとの指示(style_preference)の行を左の一覧から選び、右で本文を直す画面。 */
export default function StylePreferenceEditor() {
  const [data, setData] = useState<RecordList | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [saved, setSaved] = useState("");
  const [text, setText] = useState("");
  const [status, setStatus] = useState<{ kind: "info" | "error"; message: string } | null>(null);

  const loadList = useCallback(() => listRecords("style_preference", ALL).then(setData), []);
  const loadRow = useCallback(async (id: number) => {
    const { record } = await getRecord("style_preference", id);
    const value = String(record.text ?? "");
    setSaved(value);
    setText(value);
  }, []);

  useEffect(() => {
    loadList().catch((e) => setStatus({ kind: "error", message: e.message }));
  }, [loadList]);

  const dirty = text !== saved;

  const select = (id: number) => {
    if (id === selectedId) return;
    if (dirty && !window.confirm(T.styleEditor.discard)) return;
    setSelectedId(id);
    setStatus(null);
    loadRow(id).catch((e) => setStatus({ kind: "error", message: e.message }));
  };

  const save = async () => {
    if (selectedId === null || !dirty) return;
    try {
      await updateRecord("style_preference", selectedId, { text });
      setSaved(text);
      setStatus({ kind: "info", message: T.record.saved(["text"]) });
      await loadList();
    } catch (e) {
      setStatus({ kind: "error", message: e instanceof Error ? e.message : String(e) });
    }
  };

  /** 変更を捨て、db の今の一覧と行を読み直す */
  const revert = async () => {
    setStatus(null);
    try {
      await loadList();
      if (selectedId !== null) await loadRow(selectedId);
    } catch (e) {
      setStatus({ kind: "error", message: e instanceof Error ? e.message : String(e) });
    }
  };

  const reload = () => {
    if (dirty && !window.confirm(T.styleEditor.discard)) return;
    void revert();
  };

  const items = data?.items ?? [];
  const current = items.find((item) => Number(item.id) === selectedId);

  return (
    <div className="style-editor">
      <div className="style-editor-list">
        <table>
          <thead>
            <tr>
              <th>id</th>
              <th>scope</th>
              <th>{T.list.text}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr
                key={String(item.id)}
                className={Number(item.id) === selectedId ? "selected" : ""}
                onClick={() => select(Number(item.id))}
              >
                <td>{String(item.id)}</td>
                <td>{String(item.scope ?? "")}</td>
                <td className="preview">{String(item.preview ?? "")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="style-editor-body">
        {selectedId === null ? (
          <div className="hint">{T.styleEditor.pick}</div>
        ) : (
          <>
            <div className="hint">
              {T.idMark(selectedId)} {String(current?.scope ?? "")}
            </div>
            <textarea className="section" value={text} onChange={(e) => setText(e.target.value)} />
          </>
        )}
        {status && <div className={`status ${status.kind}`}>{status.message}</div>}
        <div className="toolbar">
          <button type="button" className="primary" disabled={!dirty} onClick={save}>
            {T.record.save}
          </button>
          <button type="button" onClick={() => void revert()}>
            {T.record.revert}
          </button>
          <button type="button" onClick={reload}>
            {T.styleEditor.reload}
          </button>
          <span className="hint">{dirty ? T.styleEditor.unsaved : ""}</span>
        </div>
      </div>
    </div>
  );
}
