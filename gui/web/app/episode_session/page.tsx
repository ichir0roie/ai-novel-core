"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import EpisodeWriter, { type EpisodeWriterHandle } from "@/components/EpisodeWriter";
import NameId from "@/components/NameId";
import { getEpisodeSession, getRecord, type SessionRecord } from "@/lib/api";
import { PageTitle } from "@/lib/meta";
import { T } from "@/lib/text";

const INTERVAL_MS = 3000;
const WRITE_KEY = "episode-session-write";

/** 手番の行を並べる列。文言の鍵も兼ねる */
const COLUMNS = ["request", "thought", "action", "speech", "aim"] as const;

/** 本文へ差し込む形。セリフは鉤括弧で括る(括ってあればそのまま) */
const insertable = (column: (typeof COLUMNS)[number], value: string) =>
  column === "speech" && !/^[「『]/.test(value) ? `「${value}」` : value;

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
  const [viewpoint, setViewpoint] = useState<number | null>(null);
  const [rows, setRows] = useState<SessionRecord[] | null>(null);
  const [fresh, setFresh] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [live, setLive] = useState(true);
  const [writing, setWriting] = useState(false);
  const writer = useRef<EpisodeWriterHandle>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);

  useEffect(() => {
    if (episodeId == null) return;
    getRecord("episode", episodeId)
      .then((result) => {
        setLabel(T.nameId(result.label, episodeId));
        setViewpoint((result.record.viewpoint_character_id as number | null) ?? null);
      })
      .catch(() => setLabel(T.idMark(episodeId)));
  }, [episodeId]);

  useEffect(() => {
    try {
      setWriting(localStorage.getItem(WRITE_KEY) === "1");
    } catch {
      // 使えない localStorage は、書く欄を閉じた状態として扱う
    }
  }, []);

  const toggleWriting = () => {
    const next = !writing;
    setWriting(next);
    try {
      localStorage.setItem(WRITE_KEY, next ? "1" : "0");
    } catch {
      // 保存できなくても、この画面の中では切り替えを保つ
    }
  };

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
    <div className={`page-fill${writing ? " session-split" : ""}`}>
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
        <button className={writing ? "primary" : undefined} onClick={toggleWriting} title={T.session.writeHint}>
          {writing ? T.session.closeWrite : T.session.write}
        </button>
      </div>
      {error && <div className="status error">{error}</div>}
      <div className="session-body">
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
                          COLUMNS.map((column) => {
                            const cell = row[column];
                            // 視点の決まった話では、視点人物でない人物の内心は地の文に書けない
                            const offView = column === "thought" && viewpoint != null && row.character?.id !== viewpoint;
                            return (
                              <td
                                key={column}
                                data-label={T.session[column]}
                                className={writing && offView && cell ? "session-offview" : undefined}
                                title={writing && offView && cell ? T.session.offViewHint : undefined}
                              >
                                {cell}
                                {/* 人物役への要求は語り部の指示なので、本文には差し込まない */}
                                {writing && column !== "request" && !offView && cell && (
                                  <InsertButton onClick={() => writer.current?.insert(insertable(column, cell))} />
                                )}
                              </td>
                            );
                          })
                        ) : (
                          <td colSpan={COLUMNS.length}>
                            {row.request}
                            {writing && row.request && <InsertButton onClick={() => writer.current?.insert(row.request)} />}
                          </td>
                        )}
                      </tr>
                    )}
                  </tbody>
                );
              })}
            </table>
          )}
        </div>
        {writing && <EpisodeWriter ref={writer} episodeId={episodeId} />}
      </div>
    </div>
  );
}

function InsertButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      className="ghost session-insert"
      title={T.session.insertHint}
      // 押しても本文の欄のカーソルを失わない
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      {T.session.insert}
    </button>
  );
}
