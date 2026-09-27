"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import GeneratePanel from "@/components/GeneratePanel";
import RecordForm from "@/components/RecordForm";
import { invalidateOptions } from "@/components/ReferenceSelect";
import Related from "@/components/Related";
import { diff, getRecord, updateRecord, type Rec, type RecordResponse } from "@/lib/api";
import { PageTitle, useTable } from "@/lib/meta";
import { stampOrder } from "@/lib/stamp";
import { T } from "@/lib/text";

/** 期間ごとの行(各要素が start を持つ子リスト)を、その画面のためだけに start 昇順で並べ直す。 */
function sortChildListsByStart(record: Rec): Rec {
  const sorted: Rec = { ...record };
  for (const [key, rows] of Object.entries(record)) {
    if (Array.isArray(rows) && rows.length > 0 && rows.every((row) => row && typeof row === "object" && "start" in row)) {
      sorted[key] = [...rows].sort((a, b) => stampOrder((a as Rec).start) - stampOrder((b as Rec).start));
    }
  }
  return sorted;
}

export default function RecordPage() {
  const { table, id } = useParams<{ table: string; id: string }>();
  const router = useRouter();
  const meta = useTable(table);
  const [loaded, setLoaded] = useState<RecordResponse | null>(null);
  const [value, setValue] = useState<Rec>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const result = await getRecord(table, id);
      const record = sortChildListsByStart(result.record);
      setLoaded({ ...result, record });
      setValue(record);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [table, id]);

  useEffect(() => {
    void load();
  }, [load]);

  const generated = useCallback(() => {
    invalidateOptions(table);
    setSaved(T.record.writtenByAi);
    void load();
  }, [table, load]);

  if (!meta) return <div className="status info">{T.loading}</div>;
  const changes = loaded ? diff(loaded.record, value) : {};
  const dirty = Object.keys(changes).length > 0;

  const save = async (thenBack: boolean) => {
    setBusy(true);
    setError(null);
    setSaved(null);
    try {
      const result = await updateRecord(table, id, changes);
      const record = sortChildListsByStart(result.record);
      setLoaded({ ...result, record });
      setValue(record);
      invalidateOptions(table);
      setSaved(T.record.saved(Object.keys(changes)));
      if (thenBack) router.push(`/tables/${table}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page-fill">
      <PageTitle kind={meta.label} record={loaded?.label} />
      <div className="hint">
        <Link href={`/tables/${table}`}>{meta.label}</Link> / id={id}
      </div>
      <h1>{loaded?.label ?? "…"}</h1>
      {error && <div className="status error">{error}</div>}
      {saved && !error && <div className="status ok">{saved}</div>}
      {loaded && (
        <div className="panel fill">
          <RecordForm
            meta={meta}
            value={value}
            onChange={setValue}
            mode="edit"
            side={<Related related={loaded.related ?? {}} owner={{ table, id }} />}
            actions={
              <div className="actionbar">
                <div className="inner">
                  <button onClick={() => loaded && setValue(loaded.record)} disabled={busy || !dirty}>
                    {T.record.revert}
                  </button>
                  <button onClick={() => save(true)} disabled={busy || !dirty}>
                    {T.record.saveAndBack}
                  </button>
                  <button className="primary" onClick={() => save(false)} disabled={busy || !dirty}>
                    {T.record.save}
                  </button>
                  <span className="spacer" />
                  <span className="meta">{dirty ? T.record.changed(Object.keys(changes)) : T.record.noChanges}</span>
                </div>
              </div>
            }
          />
        </div>
      )}
      {loaded && <GeneratePanel table={table} meta={meta} draft={value} mode="edit" onDone={generated} disabled={busy || dirty} />}
    </div>
  );
}
