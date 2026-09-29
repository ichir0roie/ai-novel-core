"use client";

import { useParams, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useGeneratePanel } from "@/components/GeneratePanel";
import RecordForm, { emptyRecord } from "@/components/RecordForm";
import { invalidateAllOptions, invalidateOptions } from "@/components/ReferenceSelect";
import { createRecord, type Rec } from "@/lib/api";
import { useCopyFromLastEpisode } from "@/lib/lastEpisode";
import { PageTitle, useMeta, useTable } from "@/lib/meta";
import { useOpenPage } from "@/lib/nav";
import { T } from "@/lib/text";

/** クエリの中で、その列の型に読める値だけを初期値に取り込む(例: `?parent_idea_id=66` で子を足す)。 */
function initialValue(meta: NonNullable<ReturnType<typeof useTable>>, searchParams: URLSearchParams): Rec {
  const record = emptyRecord(meta);
  for (const column of meta.columns) {
    const raw = searchParams.get(column.key);
    if (raw === null || raw === "") continue;
    if (column.type === "integer" || column.type === "number") {
      const n = Number(raw);
      if (!Number.isNaN(n)) record[column.key] = n;
    } else if (column.type === "boolean") {
      record[column.key] = raw === "true";
    } else {
      record[column.key] = raw;
    }
  }
  return record;
}

export default function NewRecordPage() {
  const openPage = useOpenPage();
  const { table } = useParams<{ table: string }>();
  const searchParams = useSearchParams();
  const meta = useTable(table);
  const { reload } = useMeta();
  const [value, setValue] = useState<Rec | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (meta && value === null) setValue(initialValue(meta, searchParams));
  }, [meta, value, searchParams]);

  useCopyFromLastEpisode(value?.story_id, setValue, table === "episode");

  const generated = useCallback(
    (id: number) => {
      invalidateAllOptions();
      void reload();
      openPage(`/tables/${table}/${id}`);
    },
    [table, reload, openPage],
  );

  const generatePanel = useGeneratePanel({ table, meta, draft: value ?? {}, mode: "create", onDone: generated, disabled: busy });

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
      openPage(`/tables/${table}/${created.record.id}`);
      setBusy(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  return (
    <div className="page-fill">
      <PageTitle kind={meta.label} />
      <div className="panel fill">
        <RecordForm
          meta={meta}
          value={value}
          onChange={setValue}
          mode="create"
          generate={generatePanel?.body}
          titleNote={T.create.title(meta.label)}
          header={error && <div className="status error">{error}</div>}
          actions={
            <div className="actionbar">
              <div className="inner">
                <button onClick={() => openPage(`/tables/${table}`)} disabled={busy}>
                  {T.create.cancel}
                </button>
                <button className="primary" onClick={submit} disabled={busy}>
                  {T.create.add}
                </button>
                {generatePanel?.toggle}
                <span className="spacer" />
              </div>
            </div>
          }
        />
      </div>
    </div>
  );
}
