"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { getScope, readScope, type Rec, type ScopeResponse } from "./api";
import { calendarOf, convertStamp, type Calendar } from "./stamp";

/** 時刻を数える作品と、その暦(null なら西暦) */
export type Scope = { storyId: number | null; calendar: Calendar | null };

const WESTERN: Scope = { storyId: null, calendar: null };

function scopeOf(response: ScopeResponse): Scope {
  return { storyId: response.story_id ?? null, calendar: calendarOf(response.calendar) };
}

const CalendarContext = createContext<Calendar | null>(null);
const SelectedContext = createContext<Scope | undefined>(undefined);

/** 時刻の欄(StampInput)が数える暦。null なら西暦 */
export const useCalendar = () => useContext(CalendarContext);

export function CalendarProvider({ calendar, children }: { calendar: Calendar | null; children: ReactNode }) {
  return <CalendarContext.Provider value={calendar}>{children}</CalendarContext.Provider>;
}

// 読む先。`query` は `/api/scope` の問い合わせ(空なら画面が選んでいる作品)、`args` は行を足す入口の引数
type Source = { query: Record<string, string | number> } | { args: Rec };

/** 作品と暦を読む。読めるまで undefined(`keepPrevious` なら、読み直すあいだは前に読んだもの)。source が null なら読まずに西暦 */
function useLoadedScope(source: Source | null, keepPrevious = false): Scope | undefined {
  const key = source === null ? null : JSON.stringify(source);
  const [loaded, setLoaded] = useState<{ key: string; scope: Scope } | null>(null);
  useEffect(() => {
    if (key === null) return;
    let alive = true;
    const parsed = JSON.parse(key) as Source;
    ("query" in parsed ? getScope(parsed.query) : readScope(parsed.args))
      .then((response) => alive && setLoaded({ key, scope: scopeOf(response) }))
      // 読めなければ西暦で数える(API が出す時刻の文字列は、そのまま出し入れできる)
      .catch(() => alive && setLoaded({ key, scope: WESTERN }));
    return () => {
      alive = false;
    };
  }, [key]);
  if (key === null) return WESTERN;
  if (loaded?.key === key) return loaded.scope;
  return keepPrevious ? loaded?.scope : undefined;
}

/** 行(`table`・`id`)の作品と暦。API がその行の時刻を出し入れする暦(`gui/api/app.py` の `_request_scope`)。
 * 暦の表(`custom_stamp`)の始まりは、どの作品の暦でもなく西暦で数える */
export function useRowScope(table: string, id: string | number): Scope | undefined {
  return useLoadedScope(table === "custom_stamp" ? null : { query: { table, id } });
}

/** 作品で絞る画面の暦。作品を選んでいなければ、画面が選んでいる作品の暦 */
export function useStoryScope(storyId: number | null): Scope | undefined {
  const selected = useContext(SelectedContext);
  const own = useLoadedScope(storyId === null ? null : { query: { story_id: storyId } });
  return storyId === null ? selected : own;
}

// 入口の引数から作品を決める欄(`data_access_logic/story/scope.py` の `_ARG_MODELS`)
// 作品を決める欄。サーバーは書く行の id と、`<表>_id` / `<表>_ids` の名前の欄から表を引いて作品を決める
// (`data_access_logic/story/scope.py` の `story_of_args`)
const isScopeKey = (key: string) => key === "id" || key === "table" || key === "row_id" || /_ids?$/.test(key);

/** 引数のうち作品を決める欄だけを、入れ子の形を保って残す(本文などを打つたびに読み直さない) */
function scopeArgs(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(scopeArgs);
  if (value === null || typeof value !== "object") return value;
  return Object.fromEntries(
    Object.entries(value).flatMap(([key, child]) =>
      isScopeKey(key) ? [[key, child]] : child !== null && typeof child === "object" ? [[key, scopeArgs(child)]] : [],
    ),
  );
}

/** 行を足すときの作品と暦。API は足す行の欄(`story_id`・`character_id` など)から作品を決め、その暦で時刻を読む。
 * 欄を選び直して読み直すあいだは、書きかけの欄を消さないよう前の暦のまま */
export function useArgsScope(args: Rec | null): Scope | undefined {
  return useLoadedScope(args === null ? null : { args: scopeArgs(args) as Rec }, true);
}

/** 画面が選んでいる作品(ナビ)の暦を読み、画面全体の時刻の欄の既定にする。行の画面・作品で絞る画面は、その作品の暦で包み直す */
export function SelectedStoryScope({ children }: { children: ReactNode }) {
  const scope = useLoadedScope({ query: {} });
  return (
    <SelectedContext.Provider value={scope}>
      <CalendarProvider calendar={scope?.calendar ?? null}>{children}</CalendarProvider>
    </SelectedContext.Provider>
  );
}

/** 画面が選んでいる作品と暦。読めるまで undefined */
export const useSelectedScope = () => useContext(SelectedContext);

// 作品ごとの暦。書くたびに読まないよう、ページを開いているあいだ取り置く(画面に出した時刻も、開いたときの暦で数えてある)
const storyCalendars = new Map<number, Promise<Calendar | null>>();

// 入口が時刻を読む作品。作品(`story_id`)か、行(`table`・`id`。その行の作品)か、行を足す入口の引数(`args`。引数から決まる作品)
type WriteTarget = { story_id: number } | { table: string; id: number } | { args: Rec };

function calendarOfTarget(target: WriteTarget): Promise<Calendar | null> {
  if ("args" in target) return readScope(scopeArgs(target.args) as Rec).then((response) => calendarOf(response.calendar));
  const read = () => getScope(target).then((response) => calendarOf(response.calendar));
  if (!("story_id" in target)) return read();
  let found = storyCalendars.get(target.story_id);
  if (!found) {
    found = read();
    found.catch(() => storyCalendars.delete(target.story_id));
    storyCalendars.set(target.story_id, found);
  }
  return found;
}

/**
 * 画面の暦(`from`)で数えた時刻の欄を、書く先の入口がその行の時刻を読む暦の桁に直す(同じ時刻を指す)。
 * 作品をまたいで並べる画面(タイムラインなど)は、どの行の時刻も画面の作品の暦で出すが、入口は行ごとにその行の作品の暦で読む
 */
export async function convertForWrite(
  form: Rec,
  keys: readonly string[],
  from: Calendar | null,
  target: WriteTarget,
): Promise<Rec> {
  if (!keys.some((key) => typeof form[key] === "string")) return form;
  const to = await calendarOfTarget(target);
  const converted: Rec = { ...form };
  for (const key of keys) if (typeof form[key] === "string") converted[key] = convertStamp(form[key] as string, from, to);
  return converted;
}
