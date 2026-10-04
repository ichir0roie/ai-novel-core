"use client";

import { useEffect, useState } from "react";
import ListTable, { nextSort, Pager, type SortOrder } from "@/components/ListTable";
import { listRecords, type RecordList } from "@/lib/api";
import { useTable } from "@/lib/meta";

const PAGE = 50;

/** 作品の画面の右に置く、その作品の話の一覧。並び・ページ送りは一覧の画面と同じで、行は別タブで開く。 */
export default function StoryEpisodes({ storyId }: { storyId: number | string }) {
  const meta = useTable("episode");
  const [sorting, setSorting] = useState<{ sort: string; order: SortOrder } | null>(null);
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<RecordList | null>(null);
  const [error, setError] = useState<string | null>(null);
  // 並びの既定はテーブルごと(TableMeta.sort / order)。meta が来るまでは決められない
  const sort = sorting?.sort ?? meta?.sort;
  const order = sorting?.order ?? meta?.order;

  useEffect(() => {
    if (!sort || !order) return;
    let alive = true;
    const params = new URLSearchParams({ story_id: String(storyId), sort, order, limit: String(PAGE), offset: String(offset) });
    listRecords("episode", params)
      .then((result) => {
        if (!alive) return;
        setData(result);
        setError(null);
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [storyId, sort, order, offset]);

  if (!meta || !sort || !order) return null;
  return (
    <div className="story-episodes">
      <h2>{meta.name}</h2>
      {error && <div className="status error">{error}</div>}
      <ListTable
        meta={meta}
        data={data}
        sort={sort}
        order={order}
        onSort={(key) => {
          setSorting(nextSort(meta, sort, order, key));
          setOffset(0);
        }}
        onOpen={(id) => window.open(`/tables/episode/${id}`, "_blank", "noopener,noreferrer")}
      />
      <Pager offset={offset} size={PAGE} total={data?.total ?? 0} onOffset={setOffset} />
    </div>
  );
}
