"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import EpisodeWriter, { type EpisodeWriterHandle } from "@/components/EpisodeWriter";
import { getRecord, readEntrance, runEntrance } from "@/lib/api";
import { claudeSessionUrl } from "@/lib/claude";
import { PageTitle } from "@/lib/meta";
import { T } from "@/lib/text";

const INTERVAL_MS = 1000;

/** `episode_comment.record.ReactionRecord` */
type Reaction = {
  id: number;
  diff_id: number;
  character: { id: number; name: string | null } | null;
  stance: string;
  quote: string | null;
  text: string;
  created_at: string;
};

export default function EpisodeCommentPage() {
  const search = useSearchParams();
  const episodeId = Number(search.get("episode")) || null;
  const [label, setLabel] = useState<string | null>(null);
  const [reactions, setReactions] = useState<Reaction[]>([]);
  const [fresh, setFresh] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [live, setLive] = useState(true);
  const writer = useRef<EpisodeWriterHandle>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  // 止めて再開しても、持っている反応の続きから引く
  const lastId = useRef(0);

  useEffect(() => {
    if (episodeId == null) return;
    getRecord("episode", episodeId)
      .then((result) => setLabel(T.nameId(result.label, episodeId)))
      .catch(() => setLabel(T.idMark(episodeId)));
  }, [episodeId]);

  // 前の要求が返ってから次を待つので、API が遅くても要求は重ならない
  useEffect(() => {
    if (episodeId == null || !live) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;
    const poll = async () => {
      try {
        const result = await readEntrance("episode_comment.read_reactions_since.ReadReactionsSince", {
          episode_id: episodeId,
          after_reaction_id: lastId.current,
        });
        const added = result.result as Reaction[];
        if (!stopped && added.length > 0) {
          // 初めに引いた分は、届いたばかりの印を付けない
          setFresh(lastId.current === 0 ? new Set() : new Set(added.map((reaction) => reaction.id)));
          lastId.current = added[added.length - 1].id;
          setReactions((held) => [...held, ...added]);
        }
        if (!stopped) setError(null);
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

  // 一番下を見ているときだけ、届いた反応へ送る
  useLayoutEffect(() => {
    const list = listRef.current;
    if (list && stickToBottom.current) list.scrollTop = list.scrollHeight;
  }, [reactions]);

  if (episodeId == null) return <div className="status error">{T.comment.noEpisode}</div>;

  const saveDraft = (text: string) =>
    runEntrance("episode_comment.save_draft.SaveDraft", { episode_id: episodeId, main_text: text });

  const close = async () => {
    if (!window.confirm(T.comment.confirmClose)) return;
    try {
      await runEntrance("episode_comment.close_comment.CloseComment", { episode_id: episodeId });
      setNotice(T.comment.closed);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const reveal = (quote: string) => {
    if (!writer.current?.reveal(quote)) setNotice(T.comment.quoteMissing);
  };

  return (
    <div className="page-fill">
      <PageTitle kind={T.comment.title} record={label} />
      <div className="toolbar session-toolbar">
        <h1>
          {T.comment.title} — <Link href={`/tables/episode/${episodeId}`}>{label ?? T.idMark(episodeId)}</Link>
        </h1>
        <span className={`session-live${live ? " on" : ""}`}>{live ? T.comment.live : T.comment.paused}</span>
        <span className="meta">{T.comment.count(reactions.length)}</span>
        <button onClick={() => setLive(!live)}>{live ? T.comment.pause : T.comment.resume}</button>
        <a
          className="button-link"
          href={claudeSessionUrl(T.comment.claudePromptStart(String(episodeId)))}
          target="_blank"
          rel="noopener noreferrer"
          title={T.comment.startHint}
        >
          {T.comment.start}
        </a>
        <button onClick={() => void close()} title={T.comment.closeHint}>
          {T.comment.close}
        </button>
      </div>
      {error && <div className="status error">{error}</div>}
      {notice && (
        <div className="status info" onClick={() => setNotice(null)}>
          {notice}
        </div>
      )}
      <div className="comment-body">
        <div
          className="comment-list"
          ref={listRef}
          onScroll={(e) => {
            const list = e.currentTarget;
            stickToBottom.current = list.scrollHeight - list.scrollTop - list.clientHeight < 40;
          }}
        >
          {reactions.length === 0 && <div className="status info">{T.comment.empty}</div>}
          {reactions.map((reaction) => (
            <div key={reaction.id} className={`comment-item${fresh.has(reaction.id) ? " fresh" : ""}`}>
              <div className="comment-head">
                <span className="meta">{new Date(reaction.created_at).toLocaleTimeString()}</span>
                <span className="comment-who">{reaction.character ? (reaction.character.name ?? T.idMark(reaction.character.id)) : T.comment.narrator}</span>
                <span className={`comment-stance${reaction.stance === "反対" || reaction.stance === "修正案" ? " against" : ""}`}>
                  {reaction.stance}
                </span>
              </div>
              {reaction.quote && (
                <button className="comment-quote" onClick={() => reveal(reaction.quote ?? "")}>
                  {reaction.quote}
                </button>
              )}
              <div className="comment-text">{reaction.text}</div>
            </div>
          ))}
        </div>
        <EpisodeWriter episodeId={episodeId} save={saveDraft} ref={writer} />
      </div>
    </div>
  );
}
