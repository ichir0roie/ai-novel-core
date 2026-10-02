"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { getRecord, labelOf, listRecords, type RecordList } from "@/lib/api";
import { cellText, listColumns, NO_PREVIEW } from "@/lib/listColumns";
import { PageTitle, useTable } from "@/lib/meta";
import StoryTree from "@/components/StoryTree";
import IdeaTree from "@/components/IdeaTree";
import CharacterTree from "@/components/CharacterTree";
import { useOpenPage } from "@/lib/nav";
import { T } from "@/lib/text";

const PAGE = 50;
// 列名の query として扱わない(絞り込みのチップに出さない)もの
const RESERVED = new Set(["q", "limit", "offset", "sort", "order"]);

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
    listRecords(table, params).then(setData).catch((e) => setError(e.message));
  }, [table, params]);

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

  const title = storyId ? T.list.episodesOf(storyLabel ?? T.list.story(storyId)) : meta?.label;
  const recordName = storyId ? (storyLabel ?? T.list.story(storyId)) : null;

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
  const columns = listColumns(meta);
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
        <PageTitle kind={meta.label} record={recordName} />
        <h1>
          {meta.label} <code>{table}</code>
        </h1>
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

  // 見出しをクリックした列で並べる。同じ列なら向きを返し、別の列なら昇順から
  const sortBy = (key: string) => {
    if (key === sort) setParams({ sort: key, order: order === "asc" ? "desc" : "asc" });
    else setParams({ sort: key, order: key === meta.sort ? meta.order : "asc" });
  };
  const sortHeader = (key: string, label: string) => (
    <th key={key} title={key} className={`sortable ${key === sort ? "sorted" : ""}`} onClick={() => sortBy(key)}>
      {label}
      {key === sort ? (order === "asc" ? " ↑" : " ↓") : ""}
    </th>
  );

  // 列名の query で絞り込んでいるもの(参照列のセルをクリックすると増える)。見出しに出す作品は除く
  const filters = [...search.entries()].filter(
    ([key]) => !RESERVED.has(key) && !(storyId && key === "story_id") && meta.columns.some((c) => c.key === key),
  );
  const filterLabel = (key: string, value: string) => {
    const column = meta.columns.find((c) => c.key === key)!;
    const shown = value === "null" ? T.list.empty : column.references ? labelOf(data?.labels, key, value) : value;
    return `${column.label}: ${shown}`;
  };

  return (
    <>
      <PageTitle kind={meta.label} record={recordName} />
      {storyId && (
        <div className="hint">
          <Link href="/tables/story">{T.list.stories}</Link> /{" "}
          <Link href={`/tables/story/${storyId}`}>{storyLabel ?? `id=${storyId}`}</Link>
        </div>
      )}
      <h1>
        {title} <code>{table}</code>
      </h1>
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
      </div>
      {error && <div className="status error">{error}</div>}
      <div className="scroll-x">
        <table className="list">
          <thead>
            <tr>
              {sortHeader("id", "id")}
              {meta.label_column ? sortHeader(meta.label_column, T.list.name) : <th>{T.list.name}</th>}
              {columns.map((c) => sortHeader(c.key, c.label))}
              {!NO_PREVIEW.has(table) && <th>{T.list.text}</th>}
            </tr>
          </thead>
          <tbody>
            {data?.items.map((item) => (
              <tr
                key={String(item.id)}
                className="row"
                tabIndex={0}
                onClick={(e) => openPage(`/tables/${table}/${item.id}`, e)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") openPage(`/tables/${table}/${item.id}`);
                }}
              >
                <td>{String(item.id)}</td>
                <td className="name">{String(item.label ?? "")}</td>
                {columns.map((c) => (
                  <td key={c.key}>
                    {c.references && item[c.key] != null ? (
                      // 参照列は、その値で一覧を絞り込む(作品の欄なら、その作品の話だけを並べる)
                      <span
                        className="ref"
                        title={T.list.filterBy(c.label)}
                        onClick={(e) => {
                          e.stopPropagation();
                          setParam(c.key, String(item[c.key]));
                        }}
                      >
                        {cellText(c, item, data.labels)}
                      </span>
                    ) : (
                      cellText(c, item, data.labels)
                    )}
                  </td>
                ))}
                {!NO_PREVIEW.has(table) && <td className="preview">{String(item.preview ?? "")}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="pager">
        <button disabled={offset <= 0} onClick={() => setParam("offset", String(Math.max(0, offset - PAGE)))}>
          {T.list.prev}
        </button>
        <span>
          {T.list.range(total === 0 ? 0 : offset + 1, Math.min(offset + PAGE, total), total)}
        </span>
        <button disabled={offset + PAGE >= total} onClick={() => setParam("offset", String(offset + PAGE))}>
          {T.list.next}
        </button>
      </div>
    </>
  );
}
