"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import GeneratePanel from "@/components/GeneratePanel";
import RecordForm, { emptyRecord } from "@/components/RecordForm";
import { invalidateOptions } from "@/components/ReferenceSelect";
import { createRecord, type Rec } from "@/lib/api";
import { PageTitle, useMeta, useTable } from "@/lib/meta";
import { T } from "@/lib/text";

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

  const generated = useCallback(
    (id: number) => {
      invalidateOptions(table);
      void reload();
      router.push(`/tables/${table}/${id}`);
    },
    [table, reload, router],
  );

  if (!meta || value === null) return <div className="status info">{T.loading}</div>;

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
    <div className="page-fill">
      <PageTitle kind={meta.label} />
      <h1>{T.create.title(meta.label)}</h1>
      {error && <div className="status error">{error}</div>}
      <div className="panel fill">
        <RecordForm meta={meta} value={value} onChange={setValue} mode="create" />
      </div>
      <GeneratePanel table={table} meta={meta} draft={value} mode="create" onDone={generated} disabled={busy} />
      <div className="actionbar">
        <div className="inner">
          <span className="spacer" />
          <button onClick={() => router.push(`/tables/${table}`)} disabled={busy}>
            {T.create.cancel}
          </button>
          <button className="primary" onClick={submit} disabled={busy}>
            {T.create.add}
          </button>
        </div>
      </div>
    </div>
  );
}
