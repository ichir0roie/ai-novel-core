"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Modal from "@/components/Modal";
import RecordForm, { emptyRecord } from "@/components/RecordForm";
import { invalidateOptions } from "@/components/ReferenceSelect";
import { createRecord, type Rec } from "@/lib/api";
import { useCopyFromLastEpisode } from "@/lib/lastEpisode";
import { useTable } from "@/lib/meta";
import { T } from "@/lib/text";

type Props = {
  table: string;
  /** 足すときの初期値(空の欄に重ねる) */
  initial?: Rec;
  onClose: () => void;
  onSaved: () => void;
};

/** 行の追加を、ページを離れずにモーダルで行う(タイムラインの空いた所から開く)。
 * AI の生成や話の登場人物の編集はページの方にしか無いので、ページへ移るリンクを添える。 */
export default function RecordModal({ table, initial, onClose, onSaved }: Props) {
  const meta = useTable(table);
  const [value, setValue] = useState<Rec | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (meta && value === null) setValue({ ...emptyRecord(meta), ...initial });
  }, [meta, value, initial]);

  useCopyFromLastEpisode(value?.story_id, setValue, table === "episode");

  const save = async () => {
    if (!value) return;
    setBusy(true);
    setError(null);
    try {
      const data: Rec = {};
      for (const [key, v] of Object.entries(value)) {
        if (v !== null && !(Array.isArray(v) && v.length === 0 && key !== "parameters")) data[key] = v;
      }
      await createRecord(table, data);
      invalidateOptions(table);
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  const pageUrl = `/tables/${table}/new?${new URLSearchParams(
    Object.entries(initial ?? {}).filter(([, v]) => v != null).map(([k, v]) => [k, String(v)]),
  )}`;
  const title = meta ? T.create.title(meta.label) : T.loading;

  return (
    <Modal
      title={title}
      onClose={onClose}
      wide
      actions={
        <>
          <Link href={pageUrl}>{T.timeline.openPage}</Link>
          <span className="spacer" />
          <button onClick={onClose} disabled={busy}>
            {T.create.cancel}
          </button>
          <button className="primary" onClick={save} disabled={busy || !value}>
            {T.create.add}
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
            mode="create"
            header={error && <div className="status error">{error}</div>}
          />
        </div>
      )}
    </Modal>
  );
}
