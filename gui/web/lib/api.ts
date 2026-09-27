import type { components } from "./openapi";

export type TableMeta = components["schemas"]["TableMeta"];
export type ColumnMeta = components["schemas"]["ColumnMeta"];
export type ChildListMeta = components["schemas"]["ChildListMeta"];
export type RecordList = components["schemas"]["RecordList"];
export type RecordResponse = components["schemas"]["RecordResponse"];
export type ReviewSummary = components["schemas"]["ReviewSummary"];
export type ReviewNext = components["schemas"]["ReviewNext"];
export type Option = components["schemas"]["Option"];
export type ConfirmStatus = components["schemas"]["ConfirmStatus"];
export type Labels = Record<string, Record<string, string>>;
export type Rec = Record<string, unknown>;

export class ApiError extends Error {
  status: number;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
  }
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      // 本文が JSON でないときは statusText のまま
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
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

export const getReviewSummary = () => api<ReviewSummary>("/api/review");

export const getReviewNext = (table: string, after = 0) =>
  api<ReviewNext>(`/api/review/${table}/next?after=${after}`);

export const decideReview = (table: string, id: number, decision: ConfirmStatus, changes: Rec) =>
  api<RecordResponse>(`/api/review/${table}/${id}`, {
    method: "POST",
    body: JSON.stringify({ decision, changes }),
  });

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
  const name = labels?.[column]?.[String(id)];
  return name ? `${name} (${id})` : String(id);
}

export type EntranceMeta = components["schemas"]["EntranceMeta"];
export type EntranceList = components["schemas"]["EntranceList"];
export type JobInfo = components["schemas"]["JobInfo"];
export type RunResult = components["schemas"]["RunResult"];

export const getEntrances = () => api<EntranceList>("/api/interface");

export const runEntrance = (id: string, args: Rec, background = false) =>
  api<RunResult | JobInfo>(`/api/interface/${id}`, { method: "POST", body: JSON.stringify({ args, background }) });

export const getJobs = () => api<components["schemas"]["JobList"]>("/api/jobs");

export const getJob = (id: string) => api<JobInfo>(`/api/jobs/${id}`);
