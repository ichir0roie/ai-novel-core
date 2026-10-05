"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  createRecord,
  deleteCharacterSkill,
  diff,
  getRecord,
  listAllRecords,
  updateRecord,
  type Rec,
} from "@/lib/api";
import { childListHint, columnHint } from "@/lib/hint";
import { useTable } from "@/lib/meta";
import { T } from "@/lib/text";
import ChildListEditor from "./ChildListEditor";
import { AutoGrowTextarea } from "./FieldInput";
import { Spec } from "./Hint";
import Modal from "./Modal";
import { invalidateOptions } from "./ReferenceSelect";

/** 一枚のスキル。`saved` は読んだ・保存したときの値で、まだ足していないスキルは null */
type Draft = { key: number; saved: Rec | null; value: Rec };

const EDITABLE = ["name", "text", "histories"] as const;

/** 足す・直すときに送る欄。足すときは人物と全部の欄を、直すときは変わった欄だけを送る */
function changesOf(draft: Draft): Rec {
  const value = Object.fromEntries(EDITABLE.map((key) => [key, draft.value[key]]));
  return draft.saved ? diff(draft.saved, value) : value;
}

let nextKey = 0;

type Props = { characterId: number; characterName: string; onClose: () => void };

/** 人物のスキルを並べ、その場で直す・足す・消す。直す・足すは保存でまとめて送り、消すはその場で消す。 */
export default function SkillsModal({ characterId, characterName, onClose }: Props) {
  const meta = useTable("character_skill");
  const histories = meta?.child_lists.find((child) => child.name === "histories");
  const nameColumn = meta?.columns.find((column) => column.key === "name");
  const textColumn = meta?.columns.find((column) => column.key === "text");
  const [drafts, setDrafts] = useState<Draft[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      // 一覧には本文が無いので、一枚ずつ読む(同じ時の GET は一回にまとまる)
      const ids = (await listAllRecords("character_skill", { character_id: String(characterId) })).map((row) => Number(row.id));
      const records = await Promise.all(ids.map((id) => getRecord("character_skill", id)));
      if (!cancelled) setDrafts(records.map(({ record }) => ({ key: nextKey++, saved: record, value: record })));
    })().catch((e) => !cancelled && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      cancelled = true;
    };
  }, [characterId]);

  const changed = (drafts ?? []).filter((draft) => Object.keys(changesOf(draft)).length > 0);

  const edit = (key: number, field: string, v: unknown) => {
    setDone(null);
    setDrafts((prev) => prev && prev.map((draft) => (draft.key === key ? { ...draft, value: { ...draft.value, [field]: v } } : draft)));
  };

  const add = () => {
    setDone(null);
    setDrafts((prev) => [...(prev ?? []), { key: nextKey++, saved: null, value: { name: "", text: "", histories: [] } }]);
  };

  const remove = async (draft: Draft) => {
    if (!draft.saved) {
      setDrafts((prev) => prev && prev.filter((d) => d.key !== draft.key));
      return;
    }
    const id = Number(draft.saved.id);
    if (!window.confirm(T.record.confirmDeleteSkill(T.nameId(draft.saved.name, id)))) return;
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      await deleteCharacterSkill(id);
      invalidateOptions("character_skill");
      setDrafts((prev) => prev && prev.filter((d) => d.key !== draft.key));
    } catch (e) {
      setError(T.record.deleteFailed(e instanceof Error ? e.message : String(e)));
    } finally {
      setBusy(false);
    }
  };

  /** 変わったスキルを一枚ずつ送る。途中で落ちたら、そこまでに送れたものは保存したものとして残す */
  const save = async () => {
    setBusy(true);
    setError(null);
    setDone(null);
    let count = 0;
    try {
      for (const draft of changed) {
        const changes = changesOf(draft);
        const { record } = draft.saved
          ? await updateRecord("character_skill", Number(draft.saved.id), changes)
          : await createRecord("character_skill", { ...changes, character_id: characterId });
        setDrafts((prev) => prev && prev.map((d) => (d.key === draft.key ? { ...d, saved: record, value: record } : d)));
        count += 1;
      }
      setDone(T.skills.saved(count));
    } catch (e) {
      setError(T.skills.failed(e instanceof Error ? e.message : String(e)));
    } finally {
      if (count > 0) invalidateOptions("character_skill");
      setBusy(false);
    }
  };

  const close = () => {
    if (changed.length > 0 && !window.confirm(T.skills.confirmDiscard(changed.length))) return;
    onClose();
  };

  return (
    <Modal
      title={T.skills.title(characterName)}
      onClose={close}
      wide
      actions={
        <>
          <button type="button" onClick={add} disabled={busy || drafts === null}>
            {T.skills.add}
          </button>
          <span className="meta">{changed.length > 0 ? T.skills.changes(changed.length) : T.record.noChanges}</span>
          <span className="spacer" />
          {error && <span className="status error">{error}</span>}
          {done && !error && <span className="status ok">{done}</span>}
          <button type="button" onClick={close}>
            {T.close}
          </button>
          <button type="button" className="primary" onClick={() => void save()} disabled={busy || changed.length === 0}>
            {T.record.save}
          </button>
        </>
      }
    >
      {drafts === null || !histories ? (
        !error && <div className="status info">{T.loading}</div>
      ) : (
        <div className="skills">
          {drafts.length === 0 && <div className="hint">{T.skills.none}</div>}
          {drafts.map((draft) => (
            <div key={draft.key} className={`skill-card ${Object.keys(changesOf(draft)).length > 0 ? "changed" : ""}`}>
              <div className="skill-head">
                <input
                  type="text"
                  className="skill-name"
                  autoFocus={!draft.saved}
                  value={(draft.value.name as string | null) ?? ""}
                  placeholder={`name (${T.required})`}
                  data-hint={nameColumn ? columnHint(nameColumn) : undefined}
                  onChange={(e) => edit(draft.key, "name", e.target.value)}
                />
                {draft.saved ? (
                  <Link href={`/tables/character_skill/${draft.saved.id}`} className="hint" target="_blank" title={T.skills.openRecord}>
                    {T.idMark(draft.saved.id)} ↗
                  </Link>
                ) : (
                  <span className="hint">{T.skills.unsaved}</span>
                )}
                <span className="spacer" />
                <button type="button" className="danger" onClick={() => void remove(draft)} disabled={busy}>
                  {T.record.delete}
                </button>
              </div>
              <label className="skill-label">
                <Spec hint={textColumn ? columnHint(textColumn) : ""}>text</Spec>
              </label>
              <AutoGrowTextarea value={(draft.value.text as string | null) ?? ""} onChange={(v) => edit(draft.key, "text", v)} />
              <label className="skill-label">
                <Spec hint={childListHint(histories)}>histories</Spec>
              </label>
              <ChildListEditor
                meta={histories}
                rows={(draft.value.histories as Rec[] | undefined) ?? []}
                onChange={(rows) => edit(draft.key, "histories", rows)}
                newRowKnowers={[{ knower_id: characterId, location_id: null, start: null }]}
              />
            </div>
          ))}
        </div>
      )}
    </Modal>
  );
}
