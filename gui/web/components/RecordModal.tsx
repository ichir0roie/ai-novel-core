"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Modal from "@/components/Modal";
import RecordForm, { emptyRecord } from "@/components/RecordForm";
import { invalidateOptions } from "@/components/ReferenceSelect";
import { createRecord, diff, getRecord, updateRecord, type Rec, type RecordResponse } from "@/lib/api";
import { useCopyFromLastEpisode } from "@/lib/lastEpisode";
import { useTable } from "@/lib/meta";
import { T } from "@/lib/text";

type Props = {
  table: string;
  /** 直す行。省けば `initial` を初期値に足す */
  id?: number;
  /** 足すときの初期値(空の欄に重ねる) */
  initial?: Rec;
  onClose: () => void;
  onSaved: () => void;
};

/** 行の編集・追加を、ページを離れずにモーダルで行う(タイムラインから開く)。
 * AI の生成・推敲や話の登場人物の編集はページの方にしか無いので、ページへ移るリンクを添える。 */
export default function RecordModal({ table, id, initial, onClose, onSaved }: Props) {
  const meta = useTable(table);
  const [loaded, setLoaded] = useState<RecordResponse | null>(null);
  const [value, setValue] = useState<Rec | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const creating = id === undefined;

  useEffect(() => {
    if (!creating) {
      getRecord(table, id)
        .then((result) => {
          setLoaded(result);
          setValue(result.record);
        })
        .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    }
  }, [table, id, creating]);

  useEffect(() => {
    if (creating && meta && value === null) setValue({ ...emptyRecord(meta), ...initial });
  }, [creating, meta, value, initial]);

  useCopyFromLastEpisode(value?.story_id, setValue, creating && table === "episode");

  const changes = loaded && value ? diff(loaded.record, value) : {};
  const dirty = creating || Object.keys(changes).length > 0;

  const save = async () => {
    if (!value) return;
    setBusy(true);
    setError(null);
    try {
      if (creating) {
        const data: Rec = {};
        for (const [key, v] of Object.entries(value)) {
          if (v !== null && !(Array.isArray(v) && v.length === 0 && key !== "parameters")) data[key] = v;
        }
        await createRecord(table, data);
      } else {
        await updateRecord(table, id, changes);
      }
      invalidateOptions(table);
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  const pageUrl = creating
    ? `/tables/${table}/new?${new URLSearchParams(
        Object.entries(initial ?? {}).filter(([, v]) => v != null).map(([k, v]) => [k, String(v)]),
      )}`
    : `/tables/${table}/${id}`;
  const title = !meta ? T.loading : creating ? T.create.title(meta.label) : T.timeline.edit(meta.label, loaded?.label || `id=${id}`);

  return (
    <Modal
      title={title}
      onClose={onClose}
      wide
      actions={
        <>
          <Link href={pageUrl}>{T.timeline.openPage}</Link>
          <span className="spacer" />
          {!creating && (
            <button onClick={() => loaded && setValue(loaded.record)} disabled={busy || !dirty}>
              {T.record.revert}
            </button>
          )}
          <button onClick={onClose} disabled={busy}>
            {T.create.cancel}
          </button>
          <button className="primary" onClick={save} disabled={busy || !dirty || !value}>
            {creating ? T.create.add : T.record.save}
          </button>
        </>
      }
    >
      {!meta || !value ? (
        error ? <div className="status error">{error}</div> : <div className="status info">{T.loading}</div>
      ) : (
        <div className="record-modal">
          <RecordForm
            meta={meta}
            value={value}
            onChange={setValue}
            mode={creating ? "create" : "edit"}
            titleNote={!creating && `id=${id}`}
            header={error && <div className="status error">{error}</div>}
          />
        </div>
      )}
    </Modal>
  );
}
