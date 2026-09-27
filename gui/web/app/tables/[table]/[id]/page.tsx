"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import RecordForm from "@/components/RecordForm";
import { invalidateOptions } from "@/components/ReferenceSelect";
import Related from "@/components/Related";
import { diff, getRecord, updateRecord, type Rec, type RecordResponse } from "@/lib/api";
import { useTable } from "@/lib/meta";

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
      setLoaded(result);
      setValue(result.record);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [table, id]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!meta) return <div className="status info">読み込み中…</div>;
  const changes = loaded ? diff(loaded.record, value) : {};
  const dirty = Object.keys(changes).length > 0;

  const save = async (thenBack: boolean) => {
    setBusy(true);
    setError(null);
    setSaved(null);
    try {
      const result = await updateRecord(table, id, changes);
      setLoaded(result);
      setValue(result.record);
      invalidateOptions(table);
      setSaved(`保存した(${Object.keys(changes).join(", ")})`);
      if (thenBack) router.push(`/tables/${table}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="hint">
        <Link href={`/tables/${table}`}>{meta.label}</Link> / id={id}
      </div>
      <h1>{loaded?.label ?? "…"}</h1>
      {error && <div className="status error">{error}</div>}
      {saved && !error && <div className="status ok">{saved}</div>}
      {loaded && (
        <>
          <div className="panel">
            <RecordForm meta={meta} value={value} onChange={setValue} mode="edit" />
          </div>
          <Related related={loaded.related ?? {}} />
        </>
      )}
      <div className="actionbar">
        <div className="inner">
          <span className="meta">{dirty ? `変更: ${Object.keys(changes).join(", ")}` : "変更なし"}</span>
          <span className="spacer" />
          <button onClick={() => loaded && setValue(loaded.record)} disabled={busy || !dirty}>
            戻す
          </button>
          <button onClick={() => save(true)} disabled={busy || !dirty}>
            保存して一覧へ
          </button>
          <button className="primary" onClick={() => save(false)} disabled={busy || !dirty}>
            保存
          </button>
        </div>
      </div>
    </>
  );
}
