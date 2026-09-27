"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import RecordForm from "@/components/RecordForm";
import Related from "@/components/Related";
import { decideReview, diff, getReviewNext, type ConfirmStatus, type Rec, type ReviewNext } from "@/lib/api";
import { useTable } from "@/lib/meta";

export default function ReviewPage() {
  const { table } = useParams<{ table: string }>();
  const meta = useTable(table);
  const [next, setNext] = useState<ReviewNext | null>(null);
  const [initial, setInitial] = useState<Rec>({});
  const [value, setValue] = useState<Rec>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const load = useCallback(
    async (after = 0) => {
      setBusy(true);
      setError(null);
      try {
        const result = await getReviewNext(table, after);
        setNext(result);
        const record = result.record ?? {};
        setInitial(record);
        setValue(record);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [table],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const decide = async (decision: ConfirmStatus | null) => {
    if (!next?.record) return;
    const id = next.record.id as number;
    setBusy(true);
    setError(null);
    try {
      const changes = diff(initial, value);
      delete changes.confirmed;
      await decideReview(table, id, decision ?? (initial.confirmed as ConfirmStatus), changes);
      setDone(`id=${id} を${decision ?? "保存"}${decision ? "に" : ""}した`);
      await load(decision ? 0 : id - 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || busy) return;
      if (e.key === "Enter") {
        e.preventDefault();
        void decide("承認");
      }
      if (e.key === "Backspace") {
        e.preventDefault();
        void decide("非承認");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (!meta) return <div className="status info">読み込み中…</div>;

  return (
    <>
      <h1>{meta.label}のレビュー</h1>
      {error && <div className="status error">{error}</div>}
      {done && !error && <div className="status ok">{done}</div>}
      {next && !next.record && (
        <div className="panel">
          未確認の{meta.label}はもう無い。<Link href={`/tables/${table}?confirmed=非承認`}>非承認の一覧</Link> /{" "}
          <Link href={`/tables/${table}`}>{meta.label}の一覧</Link>
        </div>
      )}
      {next?.record && (
        <>
          <div className="panel">
            <div className="hint" style={{ marginBottom: "0.5rem" }}>
              id={String(next.record.id)}{" "}
              <Link href={`/tables/${table}/${next.record.id}`}>詳細を開く</Link>
            </div>
            <RecordForm meta={meta} value={value} onChange={setValue} mode="edit" />
          </div>
          <Related related={next.related ?? {}} />
        </>
      )}
      <div className="actionbar">
        <div className="inner">
          <span className="meta">
            残り {next?.remaining ?? "…"} 件
            {next?.record && (
              <>
                {" "}
                <span className="kbd">Ctrl+Enter</span> 承認 <span className="kbd">Ctrl+BS</span> 非承認
              </>
            )}
          </span>
          <span className="spacer" />
          <button className="danger" disabled={busy || !next?.record} onClick={() => decide("非承認")}>
            非承認
          </button>
          <button disabled={busy || !next?.record} onClick={() => void load((next?.record?.id as number) ?? 0)}>
            スキップ
          </button>
          <button disabled={busy || !next?.record} onClick={() => decide(null)}>
            保存だけ
          </button>
          <button className="primary" disabled={busy || !next?.record} onClick={() => decide("承認")}>
            承認
          </button>
        </div>
      </div>
    </>
  );
}
