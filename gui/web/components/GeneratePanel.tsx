"use client";

import { useState, type ReactNode } from "react";
import { generateRecord, type ColumnMeta, type GeneratorMeta, type Rec, type TableMeta } from "@/lib/api";
import { compactDraft, isEmpty, matchingGenerators, useGenerateJob } from "@/lib/generateJob";
import { useMeta } from "@/lib/meta";
import FieldInput from "./FieldInput";
import { T } from "@/lib/text";

type Props = {
  table: string;
  /** 読み込み中は undefined になる(その間は何も出さない) */
  meta: TableMeta | undefined;
  /** 欄の値(下書き)。空の欄は AI が補う */
  draft: Rec;
  mode: "create" | "edit";
  /** 足し終わった(直し終わった)行の id */
  onDone: (id: number) => void;
  disabled?: boolean;
};

export type PanelParts = { toggle: ReactNode; body: ReactNode };

/** 「AI で作成」。欄の値を核に AI が全欄を組み立て直して行を足す(claude を叩く裏の job)。
 * 呼ぶ側(save ボタンの並び)に置く小さなボタン(`toggle`)と、押すと開く欄(`body`。無ければ null)を分けて返す。
 * 指定できる欄(params)が無ければボタン自体がその場で実行し、`body` は結果待ち・エラーの表示だけになる。
 * 大きな専用パネルで出す推敲(`panel: true`)は `useRevisePanel` の担当なので、ここでは出さない。 */
export function useGeneratePanel({ table, meta, draft, mode, onDone, disabled }: Props): PanelParts | null {
  const { claudeAvailable } = useMeta();
  const [open, setOpen] = useState(false);
  const [args, setArgs] = useState<Rec>({});
  const { job, error, running, start, setError } = useGenerateJob((id) => {
    setOpen(false);
    onDone(id);
  });

  const generators = matchingGenerators(meta, draft, mode, false);
  if (generators.length === 0) return null;

  const params = new Map<string, ColumnMeta>();
  for (const generator of generators) for (const param of generator.params ?? []) params.set(param.key, param);
  // 下書きにも同じ欄がある指定(episode の登場人物 character_ids)は、触るまで下書きの値を出して渡す
  const valueOf = (key: string) => (key in args ? args[key] : draft[key]);

  const run = async (generator: GeneratorMeta) => {
    setError(null);
    const mine: Rec = {};
    for (const param of generator.params ?? []) if (!isEmpty(valueOf(param.key))) mine[param.key] = valueOf(param.key);
    await start(() => generateRecord(table, generator.key, compactDraft(draft), mine));
  };

  const status = (running && job && <div className="hint">{T.generate.inProgress(job.id, job.status)}</div>) || (error && <div className="status error">{error}</div>);

  // 指定できる欄が無い生成(character の「AI で補完」など)は、開閉を挟まずボタンがそのまま実行する
  if (params.size === 0) {
    return {
      toggle: (
        <>
          {generators.map((generator) => (
            <button key={generator.key} onClick={() => run(generator)} disabled={disabled || running || !claudeAvailable} title={T.generate.description(mode)}>
              {generator.label}
            </button>
          ))}
        </>
      ),
      body: status ? <div className="panel generate">{status}</div> : null,
    };
  }

  return {
    toggle: (
      <button
        type="button"
        className={open ? "on" : ""}
        onClick={() => setOpen(!open)}
        disabled={disabled || !claudeAvailable}
        title={claudeAvailable ? T.generate.description(mode) : T.generate.unavailable}
      >
        {generators.map((g) => g.label).join(" / ")}
      </button>
    ),
    body: open ? (
      <div className="panel generate">
        {!claudeAvailable && <div className="status error">{T.generate.unavailable}</div>}
        <div className="form">
          {[...params.values()].map((param) => (
            <div key={param.key} className="field">
              <label title={param.comment ?? ""}>
                {param.label}
                <span className="key">{param.key}</span>
              </label>
              <FieldInput column={param} value={valueOf(param.key)} onChange={(v) => setArgs({ ...args, [param.key]: v })} disabled={running} />
            </div>
          ))}
          <div className="generate-buttons">
            {generators.map((generator) => (
              <button key={generator.key} className="primary" onClick={() => run(generator)} disabled={disabled || running || !claudeAvailable} title={T.generate.description(mode)}>
                {generator.label}
              </button>
            ))}
          </div>
        </div>
        {status}
      </div>
    ) : null,
  };
}
