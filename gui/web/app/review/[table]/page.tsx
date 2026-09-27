"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import RecordForm from "@/components/RecordForm";
import Related from "@/components/Related";
import { decideReview, diff, getReviewNext, type ConfirmStatus, type Rec, type ReviewNext } from "@/lib/api";
import { PageTitle, useTable } from "@/lib/meta";
import { T } from "@/lib/text";

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
      setDone(T.review.done(id, decision));
      await load(decision ? 0 : id - 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (busy || !next?.record) return;
      if (e.ctrlKey || e.metaKey) {
        if (e.key === "Enter") {
          e.preventDefault();
          void decide("承認");
        }
        if (e.key === "Backspace") {
          e.preventDefault();
          void decide("非承認");
        }
        return;
      }
      const target = e.target as HTMLElement | null;
      const typing =
        !!target &&
        (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT" || target.isContentEditable);
      if (typing) return;
      if (e.key === "a" || e.key === "A") {
        e.preventDefault();
        void decide("承認");
      }
      if (e.key === "r" || e.key === "R") {
        e.preventDefault();
        void decide("非承認");
      }
      if (e.key === "s" || e.key === "S") {
        e.preventDefault();
        void load((next?.record?.id as number) ?? 0);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (!meta) return <div className="status info">{T.loading}</div>;

  return (
    <div className="page-fill">
      <PageTitle kind={meta.label} record={next?.label} />
      <h1>{T.review.title(meta.label)}</h1>
      {error && <div className="status error">{error}</div>}
      {done && !error && <div className="status ok">{done}</div>}
      {next && !next.record && (
        <div className="panel">
          {T.review.noneLeft(meta.label)}<Link href={`/tables/${table}?confirmed=非承認`} target="_blank" rel="noopener noreferrer">{T.review.rejectedList}</Link> /{" "}
          <Link href={`/tables/${table}`} target="_blank" rel="noopener noreferrer">{T.review.tableList(meta.label)}</Link>
        </div>
      )}
      {next?.record && (
        <div className="panel fill">
          <div className="hint" style={{ marginBottom: "0.5rem" }}>
            id={String(next.record.id)}{" "}
            <Link href={`/tables/${table}/${next.record.id}`} target="_blank" rel="noopener noreferrer">{T.openRecord}</Link>
          </div>
          <RecordForm
            meta={meta}
            value={value}
            onChange={setValue}
            mode="edit"
            side={<Related related={next.related ?? {}} />}
            actions={
              <div className="actionbar">
                <div className="inner">
                  <button className="danger" disabled={busy} onClick={() => decide("非承認")}>
                    {T.review.reject}
                  </button>
                  <button disabled={busy} onClick={() => void load((next?.record?.id as number) ?? 0)}>
                    {T.review.skip}
                  </button>
                  <button disabled={busy} onClick={() => decide(null)}>
                    {T.review.saveOnly}
                  </button>
                  <button className="primary" disabled={busy} onClick={() => decide("承認")}>
                    {T.review.approve}
                  </button>
                  <span className="spacer" />
                  <span className="meta">
                    {T.review.remaining(next?.remaining ?? "…")} <span className="kbd">A</span> {T.review.keyApprove}{" "}
                    <span className="kbd">R</span> {T.review.keyReject}{" "}
                    <span className="kbd">S</span> {T.review.keySkip}
                  </span>
                </div>
              </div>
            }
          />
        </div>
      )}
    </div>
  );
}
