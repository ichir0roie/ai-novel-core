"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { deleteMemes, getRecord, labelOf, listRecords, type RecordList } from "@/lib/api";
import { PageTitle, useTable } from "@/lib/meta";
import StoryTree from "@/components/StoryTree";
import IdeaTree from "@/components/IdeaTree";
import CharacterTree from "@/components/CharacterTree";
import ListTable, { nextSort, Pager } from "@/components/ListTable";
import NameId from "@/components/NameId";
import { useOpenPage } from "@/lib/nav";
import { T } from "@/lib/text";

const PAGE = 50;
// 列名の query として扱わない(絞り込みのチップに出さない)もの
const RESERVED = new Set(["q", "limit", "offset", "sort", "order"]);
// 一覧で選んでまとめて消せるテーブル。抜き出しで溜まるミームを、本文を見て間引く
const BULK_DELETE: Partial<Record<string, (ids: number[]) => Promise<unknown>>> = { meme: deleteMemes };

export default function TablePage() {
  const openPage = useOpenPage();
  const { table } = useParams<{ table: string }>();
  const router = useRouter();
  const search = useSearchParams();
  const meta = useTable(table);
  const [data, setData] = useState<RecordList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState(search.get("q") ?? "");
  const storyId = table === "episode" ? search.get("story_id") : null;
  const [storyLabel, setStoryLabel] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [reload, setReload] = useState(0);
  const [deleting, setDeleting] = useState(false);
  const bulkDelete = BULK_DELETE[table];

  // 並びの既定はテーブルごと(TableMeta.sort / order)。meta が来るまでは決められない
  const params = useMemo(() => {
    if (!meta) return null;
    const p = new URLSearchParams(search.toString());
    if (!p.has("limit")) p.set("limit", String(PAGE));
    if (!p.has("sort")) p.set("sort", meta.sort);
    if (!p.has("order")) p.set("order", meta.order);
    return p;
  }, [search, meta]);

  useEffect(() => {
    if (!params) return;
    setError(null);
    setSelected(new Set());
    listRecords(table, params).then(setData).catch((e) => setError(e.message));
  }, [table, params, reload]);

  useEffect(() => {
    if (!storyId) return;
    let alive = true;
    getRecord("story", storyId)
      .then((r) => alive && setStoryLabel(r.label))
      .catch(() => alive && setStoryLabel(null));
    return () => {
      alive = false;
    };
  }, [storyId]);

  const recordName = storyId ? T.nameId(storyLabel, storyId) : null;
  const title = recordName ? T.list.episodesOf(recordName) : table;

  const setParams = (changes: Record<string, string | null>) => {
    const p = new URLSearchParams(search.toString());
    for (const [key, value] of Object.entries(changes)) {
      if (value === null || value === "") p.delete(key);
      else p.set(key, value);
    }
    if (!("offset" in changes)) p.delete("offset");
    router.push(`/tables/${table}?${p.toString()}`);
  };
  const setParam = (key: string, value: string | null) => setParams({ [key]: value });

  if (!meta || !params) return <div className="status info">{T.loading}</div>;
  const offset = Number(params.get("offset") ?? 0);
  const total = data?.total ?? 0;
  const sort = params.get("sort") ?? meta.sort;
  const order = params.get("order") === "asc" ? "asc" : "desc";

  // 作品(story)は場所の木、アイデア(idea)は parent_idea_id の木、人物(character)は居場所の木でツリー表示を持つ。
  // 既定はどれもツリー(`?view=list` で表)
  const hasTree = table === "story" || table === "idea" || table === "character";
  const tree = hasTree && (search.get("view") ?? "tree") === "tree";
  const viewSwitch = hasTree && (
    <span className="segment">
      <button type="button" className={tree ? "on" : ""} onClick={() => setParam("view", "tree")}>
        {T.list.tree}
      </button>
      <button type="button" className={tree ? "" : "on"} onClick={() => setParam("view", "list")}>
        {T.list.list}
      </button>
    </span>
  );
  if (tree) {
    return (
      <>
        <PageTitle kind={table} record={recordName} />
        <h1>{table}</h1>
        <div className="toolbar">
          {viewSwitch}
          <Link href={`/tables/${table}/new`}>
            <button type="button" className="primary">
              {T.list.add}
            </button>
          </Link>
        </div>
        {table === "story" ? <StoryTree /> : table === "idea" ? <IdeaTree /> : <CharacterTree />}
      </>
    );
  }

  const sortBy = (key: string) => setParams(nextSort(meta, sort, order, key));

  // 列名の query で絞り込んでいるもの(参照列のセルをクリックすると増える)。見出しに出す作品は除く
  const filters = [...search.entries()].filter(
    ([key]) => !RESERVED.has(key) && !(storyId && key === "story_id") && meta.columns.some((c) => c.key === key),
  );
  const toggle = (id: number) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  };
  const removeSelected = async () => {
    if (!bulkDelete || selected.size === 0 || !window.confirm(T.list.confirmDeleteSelected(selected.size))) return;
    setDeleting(true);
    setError(null);
    try {
      await bulkDelete([...selected]);
      setReload((n) => n + 1);
    } catch (e) {
      setError(T.record.deleteFailed(e instanceof Error ? e.message : String(e)));
    } finally {
      setDeleting(false);
    }
  };

  const filterLabel = (key: string, value: string) => {
    const column = meta.columns.find((c) => c.key === key)!;
    const shown = value === "null" ? T.list.empty : column.references ? labelOf(data?.labels, key, value) : value;
    return `${column.key}: ${shown}`;
  };

  return (
    <>
      <PageTitle kind={table} record={recordName} />
      {storyId && (
        <div className="hint">
          <Link href="/tables/story">{T.list.stories}</Link> /{" "}
          <Link href={`/tables/story/${storyId}`}>
            <NameId name={storyLabel} id={storyId} />
          </Link>
        </div>
      )}
      <h1>{title}</h1>
      <div className="toolbar">
        {viewSwitch}
        <form
          style={{ display: "contents" }}
          onSubmit={(e) => {
            e.preventDefault();
            setParam("q", q);
          }}
        >
          <input type="search" placeholder={T.list.searchPlaceholder} value={q} onChange={(e) => setQ(e.target.value)} />
          <button type="submit">{T.list.search}</button>
        </form>
        {filters.length > 0 && (
          <span className="chips">
            {filters.map(([key, value]) => (
              <button key={key} type="button" className="chip on" title={T.list.removeFilter} onClick={() => setParam(key, null)}>
                {filterLabel(key, value)} ×
              </button>
            ))}
          </span>
        )}
        <Link href={`/tables/${table}/new`}>
          <button type="button" className="primary">
            {T.list.add}
          </button>
        </Link>
        {bulkDelete && (
          <button type="button" className="danger" disabled={selected.size === 0 || deleting} onClick={removeSelected}>
            {T.list.deleteSelected(selected.size)}
          </button>
        )}
      </div>
      {error && <div className="status error">{error}</div>}
      <ListTable
        meta={meta}
        data={data}
        sort={sort}
        order={order}
        onSort={sortBy}
        onOpen={(id, e) => openPage(`/tables/${table}/${id}`, e)}
        onFilter={(key, value) => setParam(key, value)}
        selection={bulkDelete ? {
          selected,
          onToggle: toggle,
          onToggleAll: () => {
            const pageIds = (data?.items ?? []).map((item) => Number(item.id));
            setSelected(pageIds.every((id) => selected.has(id)) ? new Set() : new Set(pageIds));
          },
        } : undefined}
      />
      <Pager offset={offset} size={PAGE} total={total} onOffset={(next) => setParam("offset", String(next))} />
    </>
  );
}
