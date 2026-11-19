"use client";

import { useEffect, useMemo, useState } from "react";
import ListTable, { nextSort, Pager, type ExtraListColumn, type SortOrder } from "@/components/ListTable";
import { listRecords, type RecordList } from "@/lib/api";
import { tableMeta } from "@/lib/meta";
import { useOpenPage } from "@/lib/openPage";
import { useCalendar } from "@/lib/scope";
import { convertStamp } from "@/lib/stamp";
import { T } from "@/lib/text";

const PAGE = 50;

/** 作品の行と一緒に返る、その作品の話(`gui/api/records.py` の `EpisodeLink`)。start は作品の暦、western_start は同じ時刻の西暦 */
export type EpisodeLink = {
  table: string;
  id: number;
  label: string;
  letters: number;
  start?: string | null;
  western_start?: string | null;
};

/** 作品の画面の右に置く、その作品の話の一覧。並び・ページ送りは一覧の画面と同じ。
 * 作品が暦を持てば、開始の列(暦)の隣に、同じ時刻を西暦で数えた列を並べる */
export default function StoryEpisodes({ storyId, links }: { storyId: number | string; links: EpisodeLink[] }) {
  const openPage = useOpenPage();
  const calendar = useCalendar();
  const meta = tableMeta("episode");
  const western = useMemo(() => new Map(links.map((link) => [link.id, link.western_start ?? null])), [links]);
  const extraColumns: ExtraListColumn[] | undefined = calendar
    ? [
        {
          key: "western_start",
          after: "start",
          label: T.list.western("start"),
          // 作品の行を読んだあとに足された話は、画面の暦から数える
          render: (item) =>
            western.get(Number(item.id)) ?? convertStamp((item.start as string | null) ?? null, calendar, null) ?? "",
        },
      ]
    : undefined;
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
        onOpen={(id, e) => openPage(`/tables/episode/${id}`, e)}
        extraColumns={extraColumns}
        headers={calendar ? { start: T.list.inCalendar("start", calendar.name) } : undefined}
      />
      <Pager offset={offset} size={PAGE} total={data?.total ?? 0} onOffset={setOffset} />
    </div>
  );
}
