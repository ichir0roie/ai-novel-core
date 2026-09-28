"use client";

import { useEffect, useState } from "react";
import { getJob, type GeneratorMeta, type JobInfo, type Rec, type TableMeta } from "./api";
import { T } from "./text";

/** 「AI で作成」系のボタンが起こす裏の job(claude を叩く)を、終わるまで 2 秒おきに見に行く。
 * `GeneratePanel`(小さなボタン列)・`RevisePanel`(推敲の大きなパネル)の両方で使う。 */
export function useGenerateJob(onDone: (id: number) => void) {
  const [job, setJob] = useState<JobInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const running = job !== null && (job.status === "queued" || job.status === "running");

  useEffect(() => {
    if (!running || !job) return;
    const timer = setInterval(async () => {
      try {
        const latest = await getJob(job.id);
        setJob(latest);
        if (latest.status === "done") {
          const id = (latest.result as { id?: number } | null)?.id;
          if (typeof id === "number") onDone(id);
          else setError(T.generate.noAddedId(latest.result));
        } else if (latest.status === "failed") {
          setError(latest.error ?? T.generate.failed);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        setJob(null);
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [running, job, onDone]);

  const start = async (fn: () => Promise<JobInfo>) => {
    setError(null);
    try {
      setJob(await fn());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return { job, error, running, start, setError };
}

export function isEmpty(value: unknown): boolean {
  return value === null || value === undefined || value === "" || (Array.isArray(value) && value.length === 0);
}

/** 欄の値(下書き)を core の空の判定(None・空文字・空の配列)に合わせて省く。 */
export function compactDraft(draft: Record<string, unknown>): Record<string, unknown> {
  const data: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(draft)) {
    if (isEmpty(value)) continue;
    data[key] = value;
  }
  return data;
}

/** その画面(table・mode・下書き)にいま出せる生成器。`panel` で「AI で作成」の小さなボタン列(false)と
 * 推敲のような専用の大きなパネル(true)を分ける。`meta` は読み込み中の undefined も受け取れる。 */
export function matchingGenerators(meta: TableMeta | undefined, draft: Rec, mode: "create" | "edit", panel: boolean): GeneratorMeta[] {
  return (meta?.generators ?? []).filter(
    (generator) =>
      Boolean(generator.panel) === panel &&
      (generator.mode === "both" || generator.mode === mode) &&
      (mode === "create" || !generator.when_empty || isEmpty(draft[generator.when_empty])) &&
      (mode === "create" || !generator.when_not_empty || !isEmpty(draft[generator.when_not_empty])),
  );
}
