"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import RecordForm from "@/components/RecordForm";
import { invalidateOptions } from "@/components/ReferenceSelect";
import Related from "@/components/Related";
import StoryEpisodes from "@/components/StoryEpisodes";
import {
  deleteEpisode,
  diff,
  getEpisodeNeighbors,
  getRecord,
  updateRecord,
  type EpisodeNeighbors,
  type Rec,
  type RecordResponse,
} from "@/lib/api";
import { claudeSessionUrl } from "@/lib/claude";
import { PageTitle, useTable } from "@/lib/meta";
import { useOpenPage } from "@/lib/nav";
import { stampOrder } from "@/lib/stamp";
import { T } from "@/lib/text";

/** start が空の行を最後に並べる子リスト。人物・関係の来歴の空の start は「年未定」(`db/schema.py` の CharacterHistory.start)。
 * ほかの子リストの空の start は「初めから」なので先頭に置く。 */
const UNDATED_LAST: Record<string, string[]> = { character: ["histories"], character_relation: ["histories"] };

/** 期間ごとの行(各要素が start を持つ子リスト)を、その画面のためだけに start 昇順で並べ直す。 */
function sortChildListsByStart(table: string, record: Rec): Rec {
  const sorted: Rec = { ...record };
  for (const [key, rows] of Object.entries(record)) {
    if (Array.isArray(rows) && rows.length > 0 && rows.every((row) => row && typeof row === "object" && "start" in row)) {
      const undatedLast = UNDATED_LAST[table]?.includes(key) ?? false;
      const order = (row: Rec) => {
        const at = stampOrder(row.start);
        return undatedLast && at === -Infinity ? Infinity : at;
      };
      sorted[key] = [...rows].sort((a, b) => {
        const x = order(a as Rec);
        const y = order(b as Rec);
        return x === y ? 0 : x < y ? -1 : 1;
      });
    }
  }
  return sorted;
}

/** 記録のページから戻る一覧。話は同じ作品で絞った一覧に戻す。 */
function listHref(table: string, record: Rec): string {
  return table === "episode" && record.story_id != null ? `/tables/${table}?story_id=${record.story_id}` : `/tables/${table}`;
}

export default function RecordPage() {
  const openPage = useOpenPage();
  const { table, id } = useParams<{ table: string; id: string }>();
  const meta = useTable(table);
  const [loaded, setLoaded] = useState<RecordResponse | null>(null);
  const [value, setValue] = useState<Rec>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [neighbors, setNeighbors] = useState<EpisodeNeighbors | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const result = await getRecord(table, id);
      const record = sortChildListsByStart(table, result.record);
      setLoaded({ ...result, record });
      setValue(record);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [table, id]);

  useEffect(() => {
    void load();
  }, [load]);

  // 時刻・作品を直して保存したら並びが変わるので、保存した値(loaded)ごとに引き直す
  const savedStart = loaded?.record.start;
  const savedStoryId = loaded?.record.story_id;
  useEffect(() => {
    if (table !== "episode" || savedStoryId === undefined) return;
    let cancelled = false;
    getEpisodeNeighbors(id)
      .then((result) => !cancelled && setNeighbors(result))
      .catch(() => !cancelled && setNeighbors(null));
    return () => {
      cancelled = true;
    };
  }, [table, id, savedStart, savedStoryId]);

  const changes = loaded ? diff(loaded.record, value) : {};
  const dirty = Object.keys(changes).length > 0;

  /** 保存できたら true。変更が無ければ何もせず true */
  const save = async (thenBack: boolean): Promise<boolean> => {
    if (!dirty) return true;
    setBusy(true);
    setError(null);
    setSaved(null);
    try {
      const result = await updateRecord(table, id, changes);
      const record = sortChildListsByStart(table, result.record);
      setLoaded({ ...result, record });
      setValue(record);
      invalidateOptions(table);
      setSaved(T.record.saved(Object.keys(changes)));
      if (thenBack) openPage(listHref(table, record));
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return false;
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!loaded || !window.confirm(T.record.confirmDeleteEpisode(T.nameId(loaded.label, id)))) return;
    setBusy(true);
    setError(null);
    setSaved(null);
    try {
      await deleteEpisode(Number(id));
      invalidateOptions(table);
      openPage(listHref(table, loaded.record));
    } catch (e) {
      setError(T.record.deleteFailed(e instanceof Error ? e.message : String(e)));
      setBusy(false);
    }
  };

  if (!meta) return <div className="status info">{T.loading}</div>;

  return (
    <div className="page-fill">
      <PageTitle kind={meta.name} record={loaded && T.nameId(loaded.label, id)} />
      {!loaded && error && <div className="status error">{error}</div>}
      {loaded && (
        <div className="panel fill">
          <RecordForm
            meta={meta}
            value={value}
            onChange={setValue}
            mode="edit"
            titleNote={
              <>
                <Link href={listHref(table, loaded.record)}>{meta.name}</Link> / {T.idMark(id)}
                {table === "episode" && neighbors && (
                  <span className="episode-step">
                    {(
                      [
                        [neighbors.previous, T.record.previousEpisode, T.record.noPreviousEpisode],
                        [neighbors.next, T.record.nextEpisode, T.record.noNextEpisode],
                      ] as const
                    ).map(([episode, label, none]) => (
                      <button
                        key={label}
                        className="ghost"
                        disabled={!episode}
                        title={episode ? `${T.nameId(episode.title, episode.id)}${episode.start ? ` — ${episode.start}` : ""}` : none}
                        onClick={(e) => episode && openPage(`/tables/episode/${episode.id}`, e)}
                      >
                        {label}
                      </button>
                    ))}
                  </span>
                )}
              </>
            }
            header={
              <>
                {error && <div className="status error">{error}</div>}
                {saved && !error && <div className="status ok">{saved}</div>}
              </>
            }
            side={
              <Related
                related={loaded.related ?? {}}
                owner={{ table, id }}
                {...(table === "episode"
                  ? {
                      characterIds: (value.character_ids as number[] | null) ?? [],
                      onChangeCharacterIds: (ids: number[]) => setValue({ ...value, character_ids: ids }),
                      episodeStart: value.start,
                      episodeLocationId: value.location_id,
                    }
                  : {})}
              />
            }
            aside={table === "story" ? <StoryEpisodes storyId={id} /> : undefined}
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
                  {table === "episode" && (
                    <a
                      className="button-link"
                      href={claudeSessionUrl(
                        (String(loaded.record.main_text ?? "").trim() ? T.record.claudePromptRevise : T.record.claudePromptWrite)(
                          T.nameId(loaded.label, id),
                        ),
                      )}
                      target="_blank"
                      rel="noopener noreferrer"
                      title={T.record.openClaudeHint}
                    >
                      {T.record.openClaude}
                    </a>
                  )}
                  <span className="spacer" />
                  <span className="meta">{dirty ? T.record.changed(Object.keys(changes)) : T.record.noChanges}</span>
                  {table === "episode" && (
                    <button className="danger" onClick={() => void remove()} disabled={busy}>
                      {T.record.delete}
                    </button>
                  )}
                </div>
              </div>
            }
          />
        </div>
      )}
    </div>
  );
}
