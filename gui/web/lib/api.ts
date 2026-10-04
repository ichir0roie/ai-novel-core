import { fetchAuthSession } from "aws-amplify/auth";
import { loginRequired } from "./auth";
import { T } from "./text";
import type { components } from "./openapi";

export type TableMeta = components["schemas"]["TableMeta"];
export type ColumnMeta = components["schemas"]["ColumnMeta"];
export type ChildListMeta = components["schemas"]["ChildListMeta"];
export type RecordList = components["schemas"]["RecordList"];
export type RecordResponse = components["schemas"]["RecordResponse"];
export type Option = components["schemas"]["Option"];
export type Labels = Record<string, Record<string, string>>;
export type Rec = Record<string, unknown>;

export class ApiError extends Error {
  status: number;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
  }
}

function detailOf(body: { detail?: unknown }): string {
  return typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = detailOf(await response.json());
    } catch {
      // 本文が JSON でないときは statusText のまま
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

// 同じ時に出た GET は `/api/batch` 一回にまとめる。Lambda は一つの実行環境で一つの要求しか受けないので、
// 並べて送るとその数だけ実行環境が起き、それぞれがコールドスタートを待つ
const BATCH_LIMIT = 20;
type Pending = { path: string; resolve: (value: unknown) => void; reject: (reason: unknown) => void };
let pending: Pending[] = [];

async function flush(): Promise<void> {
  const queued = pending;
  pending = [];
  for (let i = 0; i < queued.length; i += BATCH_LIMIT) {
    const chunk = queued.slice(i, i + BATCH_LIMIT);
    if (chunk.length === 1) {
      request(chunk[0].path).then(chunk[0].resolve, chunk[0].reject);
      continue;
    }
    request<components["schemas"]["BatchResponse"]>("/api/batch", {
      method: "POST",
      body: JSON.stringify({ paths: chunk.map((item) => item.path) }),
    }).then(
      ({ responses }) =>
        responses.forEach(({ status, body }, j) =>
          status < 400 ? chunk[j].resolve(body) : chunk[j].reject(new ApiError(status, detailOf(body ?? {})))),
      (e) => chunk.forEach((item) => item.reject(e)),
    );
  }
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  // アクセストークン(1 時間)が切れていれば、更新のトークンで取り直してクッキーに置く。route handler はクッキーのトークンを確かめる
  if (loginRequired) await fetchAuthSession();
  if (init) return request<T>(path, init);
  return new Promise<T>((resolve, reject) => {
    pending.push({ path, resolve: resolve as (value: unknown) => void, reject });
    // 同じ描画で動いた effect の呼び出しが出揃ってから送る
    if (pending.length === 1) setTimeout(() => void flush(), 0);
  });
}

export const getTables = () => api<components["schemas"]["TablesResponse"]>("/api/tables");

export const listRecords = (table: string, params: URLSearchParams) =>
  api<RecordList>(`/api/tables/${table}/records?${params.toString()}`);

export const getRecord = (table: string, id: number | string) =>
  api<RecordResponse>(`/api/tables/${table}/records/${id}`);

export const createRecord = (table: string, data: Rec) =>
  api<RecordResponse>(`/api/tables/${table}/records`, { method: "POST", body: JSON.stringify(data) });

export const updateRecord = (table: string, id: number | string, data: Rec) =>
  api<RecordResponse>(`/api/tables/${table}/records/${id}`, { method: "PATCH", body: JSON.stringify(data) });

export const getOptions = (table: string, q?: string) => {
  const params = new URLSearchParams({ limit: "2000" });
  if (q) params.set("q", q);
  return api<components["schemas"]["OptionList"]>(`/api/tables/${table}/options?${params}`);
};

/** 読んだときの値から変わった欄だけを返す(入口は「渡した欄だけ直す」)。 */
export function diff(initial: Rec, current: Rec): Rec {
  const changes: Rec = {};
  for (const key of Object.keys(current)) {
    if (JSON.stringify(initial[key] ?? null) !== JSON.stringify(current[key] ?? null)) {
      changes[key] = current[key];
    }
  }
  return changes;
}

export function labelOf(labels: Labels | undefined, column: string, id: unknown): string {
  if (id === null || id === undefined) return "";
  return T.nameId(labels?.[column]?.[String(id)], id);
}

export type EntranceMeta = components["schemas"]["EntranceMeta"];
export type EntranceList = components["schemas"]["EntranceList"];
export type RunResult = components["schemas"]["RunResult"];

export const getEntrances = () => api<EntranceList>("/api/interface");

export const runEntrance = (id: string, args: Rec) =>
  api<RunResult>(`/api/interface/${id}`, { method: "POST", body: JSON.stringify({ args }) });

/** アイデアを消す(下位のアイデアが残っていると失敗する)。`idea.delete_idea.DeleteIdea` を呼ぶ。 */
export const deleteIdea = (ideaId: number) => runEntrance("idea.delete_idea.DeleteIdea", { idea_id: ideaId });

/** ミームをまとめて消す(一つでも無ければ何も消さない)。`meme.delete_meme.DeleteMeme` を呼ぶ。 */
export const deleteMemes = (memeIds: number[]) => runEntrance("meme.delete_meme.DeleteMeme", { meme_ids: memeIds });

/** 話を消す(登場人物・踏まえたアイデアとの中間テーブルの行も消える)。`episode.delete_episode.DeleteEpisode` を呼ぶ。 */
export const deleteEpisode = (episodeId: number) =>
  runEntrance("episode.delete_episode.DeleteEpisode", { episode_id: episodeId });

export type MapsResponse = components["schemas"]["MapsResponse"];
export type PlanetMap = components["schemas"]["PlanetMap"];
export type MapLocation = components["schemas"]["MapLocation"];
export type RelationsResponse = components["schemas"]["RelationsResponse"];
export type RelationCharacter = components["schemas"]["RelationCharacter"];
export type Relation = components["schemas"]["Relation"];

export const getMaps = () => api<MapsResponse>("/api/maps");
export const getRelations = () => api<RelationsResponse>("/api/relations");

export type CharacterLocationsResponse = components["schemas"]["CharacterLocationsResponse"];

export const getCharacterLocations = () => api<CharacterLocationsResponse>("/api/character_locations");

export type LocationCharactersResponse = components["schemas"]["LocationCharactersResponse"];

export const getLocationCharacters = (locationId: number, time: string) =>
  api<LocationCharactersResponse>(`/api/location_characters?${new URLSearchParams({ location_id: String(locationId), time })}`);

export type EpisodeRecord = components["schemas"]["EpisodeRecord"];

export const getLastEpisode = (storyId: number) =>
  api<EpisodeRecord | null>(`/api/last_episode?${new URLSearchParams({ story_id: String(storyId) })}`);

export type TimelineResponse = components["schemas"]["TimelineResponse"];

export const getTimeline = (params: { story_id?: number | null; location_id?: number | null }) => {
  const query = new URLSearchParams();
  if (params.story_id != null) query.set("story_id", String(params.story_id));
  if (params.location_id != null) query.set("location_id", String(params.location_id));
  return api<TimelineResponse>(`/api/timeline?${query}`);
};

/** 一覧を末尾まで全部引く(`limit` の上限 500 ごとに繰り返す)。 */
export async function listAllRecords(table: string, params: Record<string, string> = {}): Promise<Rec[]> {
  const items: Rec[] = [];
  for (let offset = 0; ; offset += 500) {
    const page = await listRecords(table, new URLSearchParams({ ...params, limit: "500", offset: String(offset) }));
    items.push(...page.items);
    if (items.length >= page.total || page.items.length === 0) return items;
  }
}
