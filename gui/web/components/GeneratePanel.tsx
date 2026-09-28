"use client";

import { useEffect, useState } from "react";
import { generateRecord, getJob, type ColumnMeta, type GeneratorMeta, type JobInfo, type Rec, type TableMeta } from "@/lib/api";
import { useMeta } from "@/lib/meta";
import FieldInput from "./FieldInput";
import { T } from "@/lib/text";

type Props = {
  table: string;
  meta: TableMeta;
  /** 欄の値(下書き)。空の欄は AI が補う */
  draft: Rec;
  mode: "create" | "edit";
  /** 足し終わった(直し終わった)行の id */
  onDone: (id: number) => void;
  disabled?: boolean;
};

/** 欄の値(下書き)を core の空の判定(None・空文字・空の配列)に合わせて省く。 */
function compactDraft(draft: Rec): Rec {
  const data: Rec = {};
  for (const [key, value] of Object.entries(draft)) {
    if (value === null || value === undefined || value === "" || (Array.isArray(value) && value.length === 0)) continue;
    data[key] = value;
  }
  return data;
}

function isEmpty(value: unknown): boolean {
  return value === null || value === undefined || value === "" || (Array.isArray(value) && value.length === 0);
}

/** 「AI で作成」。欄の値を核に AI が全欄を組み立て直して行を足す。claude を叩く裏の job なので、終わるまで待って結果の行へ移る。 */
export default function GeneratePanel({ table, meta, draft, mode, onDone, disabled }: Props) {
  const { claudeAvailable } = useMeta();
  const [args, setArgs] = useState<Rec>({});
  const [job, setJob] = useState<JobInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  const generators = (meta.generators ?? []).filter(
    (generator) => (generator.mode === "both" || generator.mode === mode) && (mode === "create" || !generator.when_empty || isEmpty(draft[generator.when_empty])),
  );

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

  if (generators.length === 0) return null;

  const params = new Map<string, ColumnMeta>();
  for (const generator of generators) for (const param of generator.params ?? []) params.set(param.key, param);

  const run = async (generator: GeneratorMeta) => {
    setError(null);
    try {
      const mine: Rec = {};
      for (const param of generator.params ?? []) if (!isEmpty(args[param.key])) mine[param.key] = args[param.key];
      setJob(await generateRecord(table, generator.key, compactDraft(draft), mine));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const buttons = (
    <div className="generate-buttons">
      {generators.map((generator) => (
        <button key={generator.key} className="primary" onClick={() => run(generator)} disabled={disabled || running || !claudeAvailable} title={T.generate.description(mode)}>
          {generator.label}
        </button>
      ))}
    </div>
  );

  return (
    <div className="panel generate">
      {!claudeAvailable && <div className="status error">{T.generate.unavailable}</div>}
      {params.size > 0 ? (
        <div className="form">
          {[...params.values()].map((param) => (
            <div key={param.key} className="field">
              <label title={param.comment ?? ""}>
                {param.label}
                <span className="key">{param.key}</span>
              </label>
              <FieldInput column={param} value={args[param.key]} onChange={(v) => setArgs({ ...args, [param.key]: v })} disabled={running} />
            </div>
          ))}
          {buttons}
        </div>
      ) : (
        buttons
      )}
      {running && job && <div className="hint">{T.generate.inProgress(job.id, job.status)}</div>}
      {error && <div className="status error">{error}</div>}
    </div>
  );
}
