"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import RecordForm, { emptyRecord } from "@/components/RecordForm";
import { invalidateOptions } from "@/components/ReferenceSelect";
import { createRecord, type Rec, type TableMeta } from "@/lib/api";
import { useCopyFromPreviousEpisode } from "@/lib/previousEpisode";
import { PageTitle, tableMeta } from "@/lib/meta";
import { useOpenPage } from "@/lib/openPage";
import { useSaveShortcut } from "@/lib/saving";
import { CalendarProvider, useArgsScope } from "@/lib/scope";
import { selectedStoryId } from "@/lib/selectedStory";
import PageHelp from "@/components/PageHelp";
import { T } from "@/lib/text";

// 作品に属する行。足すときの作品は、画面が選んでいる作品から始める
const STORY_TABLES = new Set(["character", "idea", "location"]);

/** 時刻の欄を持つ表か(子の一覧の欄も見る)。暦の表(`custom_stamp`)の始まりは西暦で数えるので、暦を読まない */
function hasStamps(meta: TableMeta): boolean {
  if (meta.name === "custom_stamp") return false;
  return [...meta.columns, ...meta.child_lists.flatMap((child) => child.columns)].some((column) => column.type === "stamp");
}

/** クエリの中で、その列の型に読める値だけを初期値に取り込む(例: `?parent_idea_id=66` で子を足す)。id の並びはカンマで区切る。 */
function initialValue(meta: TableMeta, searchParams: URLSearchParams): Rec {
  const record = emptyRecord(meta);
  if (STORY_TABLES.has(meta.name) && "story_id" in record) record.story_id = selectedStoryId();
  for (const column of meta.columns) {
    const raw = searchParams.get(column.key);
    if (raw === null || raw === "") continue;
    if (column.type === "integer" || column.type === "number") {
      const n = Number(raw);
      if (!Number.isNaN(n)) record[column.key] = n;
    } else if (column.type === "id_list") {
      const ids = raw.split(",").map(Number);
      if (ids.every((n) => Number.isInteger(n))) record[column.key] = ids;
    } else if (column.type === "boolean") {
      record[column.key] = raw === "true";
    } else {
      record[column.key] = raw;
    }
  }
  return record;
}

export default function NewRecordPage() {
  const router = useRouter();
  const openPage = useOpenPage();
  const { table } = useParams<{ table: string }>();
  const searchParams = useSearchParams();
  const meta = tableMeta(table);
  const [value, setValue] = useState<Rec | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (meta && value === null) setValue(initialValue(meta, searchParams));
  }, [meta, value, searchParams]);

  useCopyFromPreviousEpisode(value?.story_id, value?.start, setValue, table === "episode");
  // 足す行の時刻は、API が行の欄(作品・人物など)から決める作品の暦で読む。暦が読めるまで欄を出さない
  const scope = useArgsScope(meta && hasStamps(meta) ? value : null);

  const submit = async () => {
    if (value === null) return;
    setBusy(true);
    setError(null);
    try {
      const data: Rec = {};
      for (const [key, v] of Object.entries(value)) {
        if (v !== null && !(Array.isArray(v) && v.length === 0 && key !== "parameters")) data[key] = v;
      }
      const created = await createRecord(table, data);
      invalidateOptions(table);
      router.push(`/tables/${table}/${created.record.id}`);
      setBusy(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  useSaveShortcut(() => void submit(), meta !== undefined && value !== null && !busy);

  if (!meta || value === null || scope === undefined) return <div className="status info">{T.loading}</div>;

  const content = (
    <div className="page-fill">
      <PageTitle kind={meta.name} />
      <div className="panel fill">
        <RecordForm
          meta={meta}
          value={value}
          onChange={setValue}
          mode="create"
          titleHelp={<PageHelp page={meta.name} help={T.help.create} extra={T.help.tables[table] ? [T.help.tables[table]] : []} />}
          titleNote={T.create.title(meta.name)}
          header={error && <div className="status error">{error}</div>}
          actions={
            <div className="actionbar">
              <div className="inner">
                <button onClick={(e) => openPage(`/tables/${table}`, e)} disabled={busy}>
                  {T.create.cancel}
                </button>
                <button className="primary" onClick={submit} disabled={busy}>
                  {T.create.add}
                </button>
                <span className="spacer" />
              </div>
            </div>
          }
        />
      </div>
    </div>
  );
  return <CalendarProvider calendar={scope.calendar}>{content}</CalendarProvider>;
}
