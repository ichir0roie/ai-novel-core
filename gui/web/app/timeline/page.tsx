"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent, type PointerEvent } from "react";
import RecordModal from "@/components/RecordModal";
import ReferenceSelect, { useOptions } from "@/components/ReferenceSelect";
import StampInput from "@/components/StampInput";
import Tooltip, { useTooltip } from "@/components/Tooltip";
import TreeReferenceSelect from "@/components/TreeReferenceSelect";
import { getTimeline, labelOf, listRecords, updateRecord, type Labels, type Rec, type TimelineResponse } from "@/lib/api";
import { PageTitle } from "@/lib/meta";
import { dayNumber, formatStamp, fromDayNumber, pad2, parseStamp, shiftDays } from "@/lib/stamp";
import { T } from "@/lib/text";

// 表示する期間(日数)。中心の前後に半分ずつ取る
const SPANS = [3, 7, 31, 92, 365, 3650, 36500];
const DEFAULT_SPAN = 31;
const LANE_HEIGHT = 26;
const ITEM_GAP = 6;
// 目盛りどうしの最小の間隔(px)。これより詰まる刻みは使わない
const MIN_TICK_PX = 64;
// ドラッグとクリックを分けるしきい値(px)
const DRAG_THRESHOLD = 4;
// 一日がこれより広ければ、空の所のクリックを時の単位で丸める(狭ければ日の単位)
const HOUR_SNAP_PX_PER_DAY = 240;
const ADD_MENU_WIDTH = 190;
const ADD_MENU_HEIGHT = 120;
const FULL_STAMP = /^\d+\/\d{2}\/\d{2} \d{2}:\d{2}:\d{2}$/;

type Kind = "episode" | "event";
type Item = { kind: Kind; key: string; id: number; label: string; record: Rec; labels: Labels; start: number; end: number | null };
type Placed = Item & { x: number; width: number; barWidth: number; lane: number };
type Row = { key: string; label: string; storyId: number | null; items: Placed[]; lanes: number };
type Tick = { at: number; label: string; major: boolean };

type Drag = { item: Item; startX: number; dx: number };
type AddMenu = { x: number; y: number; at: string; storyId: number | null };
type ModalState = { table: Kind; id?: number; initial?: Rec };

function dayOf(value: unknown): number | null {
  const parts = parseStamp(value);
  return parts ? dayNumber(parts) : null;
}

/** 札の幅。枠と余白に 22px、全角は 14px、半角は 8px ほどで見積もる */
function labelWidth(label: string): number {
  let width = 22;
  for (const c of label) width += c.charCodeAt(0) > 0xff ? 14 : 8;
  return Math.min(240, width);
}

/** 重ならないよう、左から順に空いている一番上の段へ置く。 */
function pack(items: Item[], toX: (day: number) => number): { placed: Placed[]; lanes: number } {
  const laneEnds: number[] = [];
  const placed = [...items]
    .sort((a, b) => a.start - b.start || a.id - b.id)
    .map((item) => {
      const x = toX(item.start);
      const barWidth = item.end === null ? 0 : Math.max(0, toX(item.end) - x);
      const width = Math.max(barWidth, labelWidth(item.label));
      let lane = laneEnds.findIndex((end) => end <= x);
      if (lane < 0) lane = laneEnds.length;
      laneEnds[lane] = x + width + ITEM_GAP;
      return { ...item, x, width, barWidth, lane };
    });
  return { placed, lanes: Math.max(1, laneEnds.length) };
}

function ticks(since: number, until: number, pxPerDay: number): Tick[] {
  const result: Tick[] = [];
  for (const hours of [1, 2, 3, 6, 12]) {
    if ((hours / 24) * pxPerDay < MIN_TICK_PX) continue;
    for (let k = Math.ceil((since * 24) / hours); (k * hours) / 24 <= until; k++) {
      const p = fromDayNumber((k * hours) / 24);
      result.push({ at: (k * hours) / 24, label: p.hour === 0 ? `${pad2(p.month)}/${pad2(p.day)}` : `${pad2(p.hour)}:00`, major: p.hour === 0 });
    }
    return result;
  }
  for (const days of [1, 2, 7, 14]) {
    if (days * pxPerDay < MIN_TICK_PX) continue;
    for (let day = Math.ceil(since); day <= until; day += days) {
      const p = fromDayNumber(day);
      const yearStart = p.month === 1 && p.day === 1;
      result.push({ at: day, label: yearStart ? `${p.year}/01/01` : `${pad2(p.month)}/${pad2(p.day)}`, major: p.day === 1 });
    }
    return result;
  }
  const first = fromDayNumber(since);
  for (const months of [1, 2, 3, 6]) {
    if (months * 30.4 * pxPerDay < MIN_TICK_PX) continue;
    let year = first.year;
    let month = Math.ceil(first.month / months) * months + 1 - months;
    for (;;) {
      if (month > 12) {
        year += 1;
        month -= 12;
      }
      const at = dayNumber({ year, month, day: 1, hour: 0, minute: 0, second: 0 });
      if (at > until) return result;
      if (at >= since) result.push({ at, label: `${year}/${pad2(month)}`, major: month === 1 });
      month += months;
    }
  }
  const steps = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000];
  const years = steps.find((step) => step * 365.2 * pxPerDay >= MIN_TICK_PX) ?? steps[steps.length - 1];
  for (let year = Math.ceil(first.year / years) * years; ; year += years) {
    const at = dayNumber({ year, month: 1, day: 1, hour: 0, minute: 0, second: 0 });
    if (at > until) return result;
    if (at >= since) result.push({ at, label: String(year), major: year % (years * 5) === 0 });
  }
}

function itemsOf(data: TimelineResponse): Item[] {
  const items: Item[] = [];
  for (const record of data.episode.items) {
    const start = dayOf(record.start);
    if (start === null) continue;
    items.push({ kind: "episode", key: `episode-${record.id}`, id: record.id as number, label: String(record.label || `id=${record.id}`),
      record, labels: data.episode.labels ?? {}, start, end: dayOf(record.end) });
  }
  for (const record of data.event.items) {
    const time = dayOf(record.time);
    if (time === null) continue;
    // 期間(start〜end)を持つ出来事は帯にする
    const start = dayOf(record.start);
    const end = dayOf(record.end);
    const span = start !== null && end !== null && end >= start;
    items.push({ kind: "event", key: `event-${record.id}`, id: record.id as number, label: String(record.label || `id=${record.id}`),
      record, labels: data.event.labels ?? {}, start: span ? start : time, end: span ? end : null });
  }
  return items;
}

/** 日付をずらしたときに直す欄。話は開始・終了、出来事は時刻・開始・終了を同じ日数だけ動かす。 */
function shifted(item: Item, days: number): Rec {
  const keys = item.kind === "episode" ? ["start", "end"] : ["time", "start", "end"];
  const changes: Rec = {};
  for (const key of keys) if (item.record[key] != null) changes[key] = shiftDays(item.record[key], days);
  return changes;
}

/** 中心の時刻を省いて開いたら、最後の話(無ければ最後の出来事)の時刻を中心にする。どちらも無ければ 1 年。 */
async function defaultCenter(): Promise<string> {
  const episodes = await listRecords("episode", new URLSearchParams({ limit: "1", sort: "start", order: "desc" }));
  if (episodes.items[0]?.start) return String(episodes.items[0].start);
  const events = await listRecords("event", new URLSearchParams({ limit: "1", sort: "time", order: "desc" }));
  if (events.items[0]?.time) return String(events.items[0].time);
  return formatStamp({ year: 1, month: 1, day: 1, hour: 0, minute: 0, second: 0 });
}

export default function TimelinePage() {
  const router = useRouter();
  const search = useSearchParams();
  const at = search.get("at");
  const spanParam = Number(search.get("span"));
  const span = SPANS.includes(spanParam) ? spanParam : DEFAULT_SPAN;
  const storyId = Number(search.get("story_id")) || null;
  const locationId = Number(search.get("location_id")) || null;
  const centerParts = parseStamp(at);
  const center = centerParts ? dayNumber(centerParts) : null;

  const [draft, setDraft] = useState<string | null>(at);
  const [data, setData] = useState<TimelineResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const [width, setWidth] = useState(0);
  const [drag, setDrag] = useState<Drag | null>(null);
  // 保存を待つあいだ、落とした所に置いておく
  const [pending, setPending] = useState<{ key: string; days: number } | null>(null);
  const [addMenu, setAddMenu] = useState<AddMenu | null>(null);
  const [modal, setModal] = useState<ModalState | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const storyOptions = useOptions("story");
  const { tip, show, hide } = useTooltip();

  const navigate = useCallback(
    (changes: Record<string, string | number | null>) => {
      const params = new URLSearchParams(search.toString());
      for (const [key, value] of Object.entries(changes)) {
        if (value === null || value === "") params.delete(key);
        else params.set(key, String(value));
      }
      router.replace(`/timeline?${params}`);
    },
    [router, search],
  );

  useEffect(() => {
    if (at) return;
    defaultCenter()
      .then((value) => navigate({ at: value }))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [at, navigate]);

  // URL の中心が変わったら(前後へ送ったときなど)入力欄も合わせる
  const [shownAt, setShownAt] = useState(at);
  if (at !== shownAt) {
    setShownAt(at);
    setDraft(at);
  }

  const since = center === null ? null : center - span / 2;
  const until = center === null ? null : center + span / 2;

  useEffect(() => {
    if (since === null || until === null) return;
    let alive = true;
    getTimeline({ since: formatStamp(fromDayNumber(since)), until: formatStamp(fromDayNumber(until)), story_id: storyId, location_id: locationId })
      .then((result) => {
        if (!alive) return;
        setData(result);
        setError(null);
        setPending(null);
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [since, until, storyId, locationId, version]);

  // 目盛りの欄の幅。時刻を横の位置に直すのに使う
  const axisRef = useCallback((element: HTMLDivElement | null) => {
    if (!element) return;
    const observer = new ResizeObserver(() => setWidth(element.clientWidth));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!addMenu) return;
    const onDown = (e: globalThis.PointerEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setAddMenu(null);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setAddMenu(null);
    };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [addMenu]);

  const pxPerDay = width > 0 ? width / span : 0;
  const toX = useCallback((day: number) => (day - (since ?? 0)) * pxPerDay, [since, pxPerDay]);

  const rows = useMemo(() => {
    if (!data) return { episodes: [] as Row[], events: null as Row | null };
    const items = itemsOf(data);
    const byStory = new Map<number, Item[]>();
    if (storyId !== null) byStory.set(storyId, []);
    for (const item of items.filter((i) => i.kind === "episode").sort((a, b) => a.start - b.start)) {
      const story = item.record.story_id as number;
      if (!byStory.has(story)) byStory.set(story, []);
      byStory.get(story)!.push(item);
    }
    // 読み直しても段が入れ替わらないよう、作品の id 順に並べる
    const episodes: Row[] = [...byStory.entries()].sort(([a], [b]) => a - b).map(([story, storyItems]) => {
      const { placed, lanes } = pack(storyItems, toX);
      // 絞り込んだ作品にこの期間の話が無ければ、名前は選択肢から引く
      const name = data.episode.labels?.story_id?.[story] ?? storyOptions.find((o) => o.id === story)?.label;
      return { key: `story-${story}`, label: name ? `${name} (${story})` : String(story), storyId: story, items: placed, lanes };
    });
    if (episodes.length === 0) episodes.push({ key: "story-none", label: "", storyId: null, items: [], lanes: 1 });
    const { placed, lanes } = pack(items.filter((i) => i.kind === "event"), toX);
    return { episodes, events: { key: "events", label: "", storyId: null, items: placed, lanes } as Row };
  }, [data, storyId, storyOptions, toX]);

  const axisTicks = useMemo(
    () => (since === null || until === null || pxPerDay === 0 ? [] : ticks(since, until, pxPerDay)),
    [since, until, pxPerDay],
  );

  const dragDays = (item: Item) => {
    if (drag?.item.key === item.key && pxPerDay > 0) return Math.round(drag.dx / pxPerDay);
    if (pending?.key === item.key) return pending.days;
    return 0;
  };

  const move = async (item: Item, days: number) => {
    const changes = shifted(item, days);
    setPending({ key: item.key, days });
    setMessage(null);
    try {
      await updateRecord(item.kind, item.id, changes);
      setMessage(T.timeline.moved(item.label, String(changes.start ?? changes.time)));
    } catch (e) {
      setError(T.timeline.moveFailed(e instanceof Error ? e.message : String(e)));
    }
    setVersion((v) => v + 1);
  };

  const onItemDown = (e: PointerEvent<HTMLDivElement>, item: Item) => {
    if (e.button !== 0 || pending) return;
    e.stopPropagation();
    e.currentTarget.setPointerCapture(e.pointerId);
    hide();
    setDrag({ item, startX: e.clientX, dx: 0 });
  };

  const onItemMove = (e: PointerEvent<HTMLDivElement>) => {
    if (drag) setDrag({ ...drag, dx: e.clientX - drag.startX });
  };

  const onItemUp = (e: PointerEvent<HTMLDivElement>) => {
    if (!drag) return;
    const { item } = drag;
    const dx = e.clientX - drag.startX;
    setDrag(null);
    if (Math.abs(dx) <= DRAG_THRESHOLD) {
      setModal({ table: item.kind, id: item.id });
      return;
    }
    const days = pxPerDay > 0 ? Math.round(dx / pxPerDay) : 0;
    if (days !== 0) void move(item, days);
  };

  const onTrackClick = (e: MouseEvent<HTMLDivElement>, row: Row) => {
    if (since === null || pxPerDay === 0) return;
    const day = since + (e.clientX - e.currentTarget.getBoundingClientRect().left) / pxPerDay;
    const snapped = pxPerDay >= HOUR_SNAP_PX_PER_DAY ? Math.floor(day * 24) / 24 : Math.floor(day);
    // 画面の端で押しても吹き出しがはみ出さないよう、内側へ寄せる
    setAddMenu({ x: Math.min(e.clientX, window.innerWidth - ADD_MENU_WIDTH), y: Math.min(e.clientY, window.innerHeight - ADD_MENU_HEIGHT),
      at: formatStamp(fromDayNumber(snapped)), storyId: row.storyId });
  };

  const openAdd = (table: Kind) => {
    if (!addMenu) return;
    const initial: Rec = table === "episode" ? { start: addMenu.at } : { time: addMenu.at };
    const story = addMenu.storyId ?? storyId;
    if (table === "episode" && story !== null) initial.story_id = story;
    if (locationId !== null) initial.location_id = locationId;
    setAddMenu(null);
    setModal({ table, initial });
  };

  const tooltipLines = (item: Item) => {
    const r = item.record;
    return item.kind === "episode"
      ? [item.label, T.span(r.start, r.end) || String(r.start), labelOf(item.labels, "story_id", r.story_id),
         r.location_id != null && labelOf(item.labels, "location_id", r.location_id), String(r.preview ?? "")]
      : [item.label, String(r.time), r.start != null && T.span(r.start, r.end), String(r.confirmed ?? ""),
         r.location_id != null && labelOf(item.labels, "location_id", r.location_id), String(r.preview ?? "")];
  };

  const renderTrackLines = () => (
    <>
      {axisTicks.map((tick) => (
        <div key={tick.at} className={`timeline-grid ${tick.major ? "major" : ""}`} style={{ left: toX(tick.at) }} />
      ))}
      {center !== null && <div className="timeline-center" style={{ left: toX(center) }} />}
    </>
  );

  const renderRow = (row: Row) => (
    <div key={row.key} className="timeline-row">
      <div className="timeline-label" title={row.label}>{row.label}</div>
      <div className="timeline-track" style={{ height: row.lanes * LANE_HEIGHT + 6 }} onClick={(e) => onTrackClick(e, row)}>
        {renderTrackLines()}
        {row.items.map((item) => {
          const days = dragDays(item);
          const dragging = drag?.item.key === item.key;
          const className = [
            "timeline-item", item.kind,
            item.end === null ? "point" : "",
            dragging ? "dragging" : "",
            pending?.key === item.key ? "saving" : "",
            item.record.confirmed === "未確認" ? "unconfirmed" : "",
            item.record.confirmed === "非承認" ? "rejected" : "",
          ].join(" ");
          const target = days !== 0 && shifted(item, days);
          return (
            <div
              key={item.key}
              className={className}
              style={{ left: item.x, top: 3 + item.lane * LANE_HEIGHT, transform: days ? `translateX(${days * pxPerDay}px)` : undefined,
                ...(dragging ? { minWidth: item.width } : { width: item.width }) }}
              onPointerDown={(e) => onItemDown(e, item)}
              onPointerMove={onItemMove}
              onPointerUp={onItemUp}
              onPointerCancel={() => setDrag(null)}
              onClick={(e) => e.stopPropagation()}
              onMouseMove={(e) => !drag && show(e, tooltipLines(item))}
              onMouseLeave={hide}
            >
              {item.barWidth > 0 && <span className="timeline-bar" style={{ width: item.barWidth }} />}
              <span className="timeline-text" style={{ paddingLeft: Math.max(0, -(item.x + days * pxPerDay)) }}>
                {item.label}
                {target && <span className="timeline-target"> → {String(target.start ?? target.time)}</span>}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );

  const shift = (direction: number) => {
    if (center === null) return;
    navigate({ at: formatStamp(fromDayNumber(center + (direction * span) / 2)) });
  };

  const truncated = data && (data.episode.items.length >= data.limit || data.event.items.length >= data.limit);

  return (
    <div className="page-fill">
      <PageTitle kind={T.timeline.title} record={at} />
      <div className="toolbar">
        <h1 style={{ margin: 0 }}>{T.timeline.title}</h1>
        <button type="button" onClick={() => shift(-1)} disabled={center === null}>{T.timeline.earlier}</button>
        <form
          className="timeline-center-input"
          onSubmit={(e) => {
            e.preventDefault();
            if (parseStamp(draft)) navigate({ at: formatStamp(parseStamp(draft)!) });
          }}
        >
          <span className="hint">{T.timeline.center}</span>
          <StampInput
            value={draft}
            onChange={(value) => {
              setDraft(value);
              if (value && FULL_STAMP.test(value)) navigate({ at: value });
            }}
          />
        </form>
        <button type="button" onClick={() => shift(1)} disabled={center === null}>{T.timeline.later}</button>
        <label className="hint">
          {T.timeline.span}{" "}
          <select value={span} onChange={(e) => navigate({ span: Number(e.target.value) })}>
            {SPANS.map((days) => (
              <option key={days} value={days}>{T.timeline.spanOf(days)}</option>
            ))}
          </select>
        </label>
        <label className="hint timeline-filter">
          {T.timeline.story}
          <ReferenceSelect table="story" value={storyId} nullable onChange={(value) => navigate({ story_id: value })} />
        </label>
        <label className="hint timeline-filter">
          {T.timeline.location}
          <TreeReferenceSelect table="location" value={locationId} nullable onChange={(value) => navigate({ location_id: value })} />
        </label>
      </div>
      {error && <div className="status error">{error}</div>}
      {message && !error && <div className="status ok">{message}</div>}
      {truncated && <div className="status info">{T.timeline.truncated(data.limit)}</div>}
      {!data ? (
        !error && <div className="status info">{T.loading}</div>
      ) : (
        <div className="timeline" aria-busy={pending !== null}>
          <div className="timeline-row timeline-axis">
            <div className="timeline-label" />
            <div className="timeline-track" ref={axisRef}>
              {axisTicks.map((tick) => (
                <div key={tick.at} className={`timeline-tick ${tick.major ? "major" : ""}`} style={{ left: toX(tick.at) }}>
                  {tick.label}
                </div>
              ))}
              {center !== null && <div className="timeline-center" style={{ left: toX(center) }} />}
            </div>
          </div>
          <div className="timeline-body">
            <div className="timeline-section">{T.timeline.episodes}</div>
            {rows.episodes.map(renderRow)}
            <div className="timeline-section">{T.timeline.events}</div>
            {rows.events && renderRow(rows.events)}
          </div>
        </div>
      )}
      <div className="hint" style={{ marginTop: "0.4rem" }}>{T.timeline.hint}</div>
      {addMenu && (
        <div ref={menuRef} className="timeline-add" style={{ left: addMenu.x, top: addMenu.y }}>
          <span className="hint">{addMenu.at}</span>
          <button type="button" onClick={() => openAdd("episode")}>{T.timeline.addEpisode}</button>
          <button type="button" onClick={() => openAdd("event")}>{T.timeline.addEvent}</button>
        </div>
      )}
      {modal && (
        <RecordModal
          table={modal.table}
          id={modal.id}
          initial={modal.initial}
          onClose={() => setModal(null)}
          onSaved={() => {
            setModal(null);
            setVersion((v) => v + 1);
          }}
        />
      )}
      <Tooltip tip={tip} />
    </div>
  );
}
