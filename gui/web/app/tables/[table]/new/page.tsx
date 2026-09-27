"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import RecordForm, { emptyRecord } from "@/components/RecordForm";
import { invalidateOptions } from "@/components/ReferenceSelect";
import { createRecord, type Rec } from "@/lib/api";
import { useMeta, useTable } from "@/lib/meta";

export default function NewRecordPage() {
  const { table } = useParams<{ table: string }>();
  const router = useRouter();
  const meta = useTable(table);
  const { reload } = useMeta();
  const [value, setValue] = useState<Rec | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (meta && value === null) setValue(emptyRecord(meta));
  }, [meta, value]);

  if (!meta || value === null) return <div className="status info">読み込み中…</div>;

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const data: Rec = {};
      for (const [key, v] of Object.entries(value)) {
        if (v !== null && !(Array.isArray(v) && v.length === 0 && key !== "parameters")) data[key] = v;
      }
      const created = await createRecord(table, data);
      invalidateOptions(table);
      void reload();
      router.push(`/tables/${table}/${created.record.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  return (
    <>
      <h1>{meta.label}を足す</h1>
      {error && <div className="status error">{error}</div>}
      <div className="panel">
        <RecordForm meta={meta} value={value} onChange={setValue} mode="create" />
      </div>
      <div className="actionbar">
        <div className="inner">
          <span className="spacer" />
          <button onClick={() => router.push(`/tables/${table}`)} disabled={busy}>
            やめる
          </button>
          <button className="primary" onClick={submit} disabled={busy}>
            足す
          </button>
        </div>
      </div>
    </>
  );
}
