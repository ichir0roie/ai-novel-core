"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import NameId from "@/components/NameId";
import { getEpisodeSession, getRecord, type SessionRecord } from "@/lib/api";
import { PageTitle } from "@/lib/meta";
import { T } from "@/lib/text";

const INTERVAL_MS = 3000;

/** 手番の行を並べる列。文言の鍵も兼ねる */
const COLUMNS = ["request", "thought", "action", "speech", "aim"] as const;

/** 一手を待つ手番の行。語りの行(人物の無い行)は手番でない */
const isPending = (row: SessionRecord) => row.character != null && row.action == null && !row.closing;

/** 持っている行から、次に引く行の境目。まだ一手の入っていない行は後から書き込まれるので、その手前から引き直す */
function afterIdOf(rows: SessionRecord[]): number | null {
  if (rows.length === 0) return null;
  const pending = rows.find(isPending);
  return pending ? pending.id - 1 : rows[rows.length - 1].id;
}

/** 前に持っていた行と比べて、増えたか中身の変わった行の id */
function changedIds(before: SessionRecord[], after: SessionRecord[]): Set<number> {
  const old = new Map(before.map((row) => [row.id, JSON.stringify(row)]));
  return new Set(after.filter((row) => old.get(row.id) !== JSON.stringify(row)).map((row) => row.id));
}

export default function EpisodeSessionPage() {
  const search = useSearchParams();
  const episodeId = Number(search.get("episode")) || null;
  const [label, setLabel] = useState<string | null>(null);
  const [rows, setRows] = useState<SessionRecord[] | null>(null);
  const [fresh, setFresh] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [live, setLive] = useState(true);
  const listRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);

  useEffect(() => {
    if (episodeId == null) return;
    getRecord("episode", episodeId)
      .then((result) => setLabel(T.nameId(result.label, episodeId)))
      .catch(() => setLabel(T.idMark(episodeId)));
  }, [episodeId]);

  // 止めて再開しても、持っている行の続きから引く
  const held = useRef<SessionRecord[] | null>(null);

  // 前の要求が返ってから次を待つので、API が遅くても要求は重ならない
  useEffect(() => {
    if (episodeId == null || !live) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;

    const poll = async () => {
      try {
        const before = held.current ?? [];
        const afterId = afterIdOf(before);
        const result = await getEpisodeSession(episodeId, afterId);
        let next = [...before.filter((row) => afterId != null && row.id <= afterId), ...result.records];
        // 持っている行より手前が消えた(手番からの回し直し)ときは、数が食い違うので全部を引き直す
        if (next.length !== result.count) next = (await getEpisodeSession(episodeId, null)).records;
        if (stopped) return;
        const changed = changedIds(before, next);
        if (held.current == null || changed.size > 0 || next.length !== before.length) {
          setFresh(held.current == null ? new Set() : changed);
          setRows(next);
          held.current = next;
        }
        setUpdatedAt(new Date().toLocaleTimeString());
        setError(null);
      } catch (e) {
        if (!stopped) setError(e instanceof Error ? e.message : String(e));
      }
      if (!stopped) timer = setTimeout(() => void poll(), INTERVAL_MS);
    };
    void poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [episodeId, live]);

  // 一番下を見ているときだけ、増えた行へ送る(上を読み返しているときは動かさない)
  useLayoutEffect(() => {
    const list = listRef.current;
    if (list && stickToBottom.current) list.scrollTop = list.scrollHeight;
  }, [rows]);

  if (episodeId == null) return <div className="status error">{T.session.noEpisode}</div>;

  const current = rows?.find(isPending)?.id;
  // 見聞きする人物は id だけで返るので、手番の行に出た名前を当てる
  const names = new Map((rows ?? []).flatMap((row) => (row.character ? [[row.character.id, row.character.name]] : [])));

  return (
    <div className="page-fill">
      <PageTitle kind={T.session.title} record={label} />
      <div className="toolbar session-toolbar">
        <h2>
          {T.session.title} — <Link href={`/tables/episode/${episodeId}`}>{label ?? T.idMark(episodeId)}</Link>
        </h2>
        <span className="spacer" />
        <span className={`session-live${live ? " on" : ""}`}>{live ? T.session.live : T.session.paused}</span>
        {updatedAt && <span className="meta">{T.session.updatedAt(updatedAt)}</span>}
        {rows && <span className="meta">{T.session.count(rows.length)}</span>}
        <button onClick={() => setLive(!live)}>{live ? T.session.pause : T.session.resume}</button>
      </div>
      {error && <div className="status error">{error}</div>}
      <div
        className="session-list"
        ref={listRef}
        onScroll={(e) => {
          const list = e.currentTarget;
          stickToBottom.current = list.scrollHeight - list.scrollTop - list.clientHeight < 40;
        }}
      >
        {rows == null && <div className="status info">{T.loading}</div>}
        {rows?.length === 0 && <div className="status info">{T.session.empty}</div>}
        {rows != null && rows.length > 0 && (
          <table className="session-table">
            <thead>
              <tr>
                {COLUMNS.map((column) => (
                  <th key={column}>{T.session[column]}</th>
                ))}
              </tr>
            </thead>
            {rows.map((row) => {
              const state =
                row.character == null
                  ? "narration"
                  : row.closing
                    ? "closing"
                    : row.action != null
                      ? "played"
                      : row.id === current
                        ? "waiting"
                        : "queued";
              return (
                // 一手が入ったら描き直し、色の変わるのを出す
                <tbody key={`${row.id}:${row.action != null}`} className={`session-row ${state}${fresh.has(row.id) ? " fresh" : ""}`}>
                  <tr>
                    <td colSpan={COLUMNS.length} className="session-head">
                      <span className="meta">{T.idMark(row.id)}</span>
                      {row.character ? (
                        <Link href={`/tables/character/${row.character.id}`}>
                          <NameId name={row.character.name} id={row.character.id} />
                        </Link>
                      ) : (
                        <span className="session-narrator">{T.session.narration}</span>
                      )}
                      {row.time && <span className="meta">{row.time}</span>}
                      {row.witnesses.length > 0 && (
                        <span className="meta">
                          {T.session.witnesses(row.witnesses.map((w) => names.get(w.character_id) ?? T.idMark(w.character_id)))}
                        </span>
                      )}
                      {state !== "played" && state !== "narration" && (
                        <span className="session-state">
                          {state === "closing" ? T.session.closing : state === "waiting" ? T.session.waiting : T.session.queued}
                        </span>
                      )}
                    </td>
                  </tr>
                  {/* 語りの行は場面だけなので、列を分けずに一つの欄へ書く */}
                  {!row.closing && (
                    <tr>
                      {row.character ? (
                        COLUMNS.map((column) => <td key={column}>{row[column]}</td>)
                      ) : (
                        <td colSpan={COLUMNS.length}>{row.request}</td>
                      )}
                    </tr>
                  )}
                </tbody>
              );
            })}
          </table>
        )}
      </div>
    </div>
  );
}
