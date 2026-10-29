"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import FullscreenText from "@/components/FullscreenText";
import InstructionModal from "@/components/InstructionModal";
import KnowledgeModal from "@/components/KnowledgeModal";
import RecordForm from "@/components/RecordForm";
import { invalidateOptions, prefetchOptions } from "@/components/ReferenceSelect";
import Related from "@/components/Related";
import StoryEpisodes from "@/components/StoryEpisodes";
import {
  deleteCharacterSkill,
  deleteEpisode,
  deleteIdeaDetachingChildren,
  diff,
  getRecord,
  listAllRecords,
  updateRecord,
  type EpisodeNeighbors,
  type Rec,
  type RecordResponse,
} from "@/lib/api";
import { receiveLocationCharacterIds } from "@/lib/locationCharacters";
import { PageTitle, referencedTables, tableMeta } from "@/lib/meta";
import { useOpenPage } from "@/lib/openPage";
import { useSaveShortcut } from "@/lib/saving";
import { stampOrder } from "@/lib/stamp";
import { T } from "@/lib/text";

/** start が空の行を最後に並べる子リスト。人物・関係・スキルの来歴の空の start は「年未定」(`db/schema.py` の CharacterHistory.start)。
 * ほかの子リストの空の start は「初めから」なので先頭に置く。 */
const UNDATED_LAST: Record<string, string[]> = {
  character: ["histories"], character_relation: ["histories"], character_skill: ["histories"],
};

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

/** 行と一緒に返る関連のうち、ほかの欄が引き直さずに使うものを渡す。 */
function receiveRelated(table: string, result: RecordResponse) {
  const ids = result.related?.location_character_ids;
  if (table === "episode" && Array.isArray(ids)) receiveLocationCharacterIds(result.record.location_id, result.record.start, ids as number[]);
}

/** 記録のページから戻る一覧。話は同じ作品で、スキルは同じ人物で絞った一覧に戻す。 */
function listHref(table: string, record: Rec): string {
  if (table === "episode" && record.story_id != null) return `/tables/${table}?story_id=${record.story_id}`;
  if (table === "character_skill" && record.character_id != null) return `/tables/${table}?character_id=${record.character_id}`;
  return `/tables/${table}`;
}

export default function RecordPage() {
  const router = useRouter();
  const openPage = useOpenPage();
  const { table, id } = useParams<{ table: string; id: string }>();
  const meta = tableMeta(table);
  const [loaded, setLoaded] = useState<RecordResponse | null>(null);
  const [value, setValue] = useState<Rec>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [organizing, setOrganizing] = useState(false);
  const [instructing, setInstructing] = useState(false);
  // 狭い画面の話の画面では、プロット・本文を押すと画面全体に広げて直す。広げている欄の名前
  const [fullscreen, setFullscreen] = useState<string | null>(null);
  // 作品・話の AI への指示は、ふだんは欄に出さず、ボタンからモーダルで直す
  const hasInstruction = table === "story" || table === "episode";

  const load = useCallback(async () => {
    setError(null);
    // 選択欄の選択肢を行と同じときに読み始め、行と一緒に `/api/batch` の一回で受ける
    const meta = tableMeta(table);
    if (meta) prefetchOptions(referencedTables(meta));
    try {
      const result = await getRecord(table, id);
      const record = sortChildListsByStart(table, result.record);
      receiveRelated(table, result);
      setLoaded({ ...result, record });
      setValue(record);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [table, id]);

  useEffect(() => {
    void load();
  }, [load]);

  // 前後の話は行と一緒に返る(保存の返事にも、直した時刻・作品での並びが入る)
  const neighbors = (loaded?.related?.neighbors as EpisodeNeighbors | undefined) ?? null;

  const changes = loaded ? diff(loaded.record, value) : {};
  const dirty = Object.keys(changes).length > 0;

  /** 保存できたら true。only を渡すとその欄の変更だけを送り、ほかの欄の変更は画面に残す */
  const save = (thenBack: boolean, only?: string[]): Promise<boolean> =>
    send(only ? Object.fromEntries(Object.entries(changes).filter(([key]) => only.includes(key))) : changes, thenBack);

  /** sending の欄だけを送る。送らない欄の変更は画面に残す。送るものが無ければ何もせず true */
  const send = async (sending: Rec, thenBack: boolean): Promise<boolean> => {
    if (Object.keys(sending).length === 0) return true;
    const kept = Object.fromEntries(Object.entries(changes).filter(([key]) => !(key in sending)));
    setBusy(true);
    setError(null);
    setSaved(null);
    try {
      const result = await updateRecord(table, id, sending);
      const record = sortChildListsByStart(table, result.record);
      receiveRelated(table, result);
      setLoaded({ ...result, record });
      setValue({ ...record, ...kept });
      invalidateOptions(table);
      setSaved(T.record.saved(Object.keys(sending)));
      if (thenBack) router.push(listHref(table, record));
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return false;
    } finally {
      setBusy(false);
    }
  };

  /** 画面の変更を捨て、db の今の行を読み直す。ほかの人・AI の段が直した分も入る */
  const revert = async () => {
    setBusy(true);
    setSaved(null);
    try {
      await load();
    } finally {
      setBusy(false);
    }
  };

  useSaveShortcut(() => void save(false), loaded !== null && !busy);

  const remove = async () => {
    if (!loaded) return;
    const label = T.nameId(loaded.label, id);
    setError(null);
    setSaved(null);
    let childIds: number[] = [];
    if (table === "idea") {
      try {
        childIds = (await listAllRecords("idea", { parent_idea_id: id })).map((child) => Number(child.id));
      } catch (e) {
        setError(T.record.deleteFailed(e instanceof Error ? e.message : String(e)));
        return;
      }
    }
    const message =
      table === "episode"
        ? T.record.confirmDeleteEpisode(label)
        : table === "character_skill"
          ? T.record.confirmDeleteSkill(label)
          : T.record.confirmDeleteIdea(label, childIds.length);
    if (!window.confirm(message)) return;
    setBusy(true);
    try {
      if (table === "episode") await deleteEpisode(Number(id));
      else if (table === "character_skill") await deleteCharacterSkill(Number(id));
      else await deleteIdeaDetachingChildren(Number(id), childIds);
      invalidateOptions(table);
      router.push(listHref(table, loaded.record));
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
            hidden={hasInstruction ? ["instruction"] : undefined}
            onOpenSection={table === "episode" ? setFullscreen : undefined}
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
                owner={{ table, id, label: T.nameId(loaded.label, id) }}
                {...(table === "episode"
                  ? {
                      characterIds: (value.character_ids as number[] | null) ?? [],
                      onChangeCharacterIds: (ids: number[]) => setValue({ ...value, character_ids: ids }),
                      episodeStart: value.start,
                      episodeLocationId: value.location_id,
                      // 地図は保存した行から引くので、作品も保存した値で渡す
                      episodeStoryId: loaded.record.story_id,
                    }
                  : {})}
              />
            }
            aside={table === "story" ? <StoryEpisodes storyId={id} /> : undefined}
            actions={
              <div className="actionbar">
                <div className="inner">
                  <button onClick={() => void revert()} disabled={busy}>
                    {T.record.revert}
                  </button>
                  <button onClick={() => save(true)} disabled={busy || !dirty}>
                    {T.record.saveAndBack}
                  </button>
                  <button className="primary" onClick={() => save(false)} disabled={busy || !dirty}>
                    {T.record.save}
                  </button>
                  {hasInstruction && (
                    <button onClick={() => setInstructing(true)} disabled={busy}>
                      {T.instruction.open(((loaded.record.instruction as string | null) ?? "").length)}
                    </button>
                  )}
                  {table === "character" && (
                    // 自分の芯・来歴の知る相手も直すので、画面の編集中の値と食い違わないよう保存してから開く
                    <button onClick={() => setOrganizing(true)} disabled={busy || dirty} title={dirty ? T.knowledge.openDisabled : undefined}>
                      {T.knowledge.open}
                    </button>
                  )}
                  <span className="spacer" />
                  <span className="meta">{dirty ? T.record.changed(Object.keys(changes)) : T.record.noChanges}</span>
                  {(table === "episode" || table === "idea" || table === "character_skill") && (
                    <button className="danger" onClick={() => void remove()} disabled={busy}>
                      {T.record.delete}
                    </button>
                  )}
                </div>
              </div>
            }
          />
          {fullscreen && (
            <FullscreenText
              title={T.record.sectionTitles[fullscreen] ?? fullscreen}
              value={(value[fullscreen] as string | null) ?? ""}
              onChange={(text) => setValue({ ...value, [fullscreen]: text })}
              onBack={() => setFullscreen(null)}
              onSave={() => {
                setFullscreen(null);
                void save(false);
              }}
            />
          )}
          {instructing && (
            <InstructionModal
              value={(loaded.record.instruction as string | null) ?? ""}
              error={error}
              onClose={() => setInstructing(false)}
              onSave={(text) => send({ instruction: text }, false)}
            />
          )}
          {organizing && (
            <KnowledgeModal
              characterId={Number(id)}
              characterName={T.nameId(loaded.label, id)}
              onClose={() => setOrganizing(false)}
              onSaved={() => void load()}
            />
          )}
        </div>
      )}
    </div>
  );
}
