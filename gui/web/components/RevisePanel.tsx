"use client";

import { useState } from "react";
import { generateRecord, type ColumnMeta, type Rec, type TableMeta } from "@/lib/api";
import { compactDraft, isEmpty, matchingGenerators, useGenerateJob } from "@/lib/generateJob";
import { useMeta } from "@/lib/meta";
import FieldInput from "./FieldInput";
import { T } from "@/lib/text";
import type { PanelParts } from "./GeneratePanel";

type Props = {
  table: string;
  /** 読み込み中は undefined になる(その間は何も出さない) */
  meta: TableMeta | undefined;
  /** 欄の値(下書き)。空の欄は AI が補う */
  draft: Rec;
  mode: "create" | "edit";
  /** 直し終わった行の id */
  onDone: (id: number) => void;
  /** 実行の直前に呼ぶ(画面の変更を保存する)。false を返したら AI を呼ばない */
  beforeRun: () => Promise<boolean>;
  disabled?: boolean;
};

/** 「AI で推敲する」など、大きな指示テキストを書き込む専用の生成(`panel: true`)。
 * save ボタンの並びに置く小さなボタン(`toggle`)と、押すと開く大きな欄(`body`)を分けて返す。
 * 汎用のフィールド一覧(GeneratePanel と同じ組み方)では、参照選択の欄(フィルター付き)が場所を取って
 * 肝心の指示テキストが埋もれるので、ここは専用の構成で組む: 指示テキスト(大きなマークダウン欄)・
 * モデル・effort・実行ボタン。タイトル・プロットは見出しや左の欄に既に出ているのでここでは繰り返さない。
 * 登場人物・直前の話は聞かない(登場人物は下書きの `character_ids`、つまりこの話の `episode_character`、
 * 直前の話は `ReviseEpisode` 側がその時刻より前の三話を自動で使う)。 */
export function useRevisePanel({ table, meta, draft, mode, onDone, beforeRun, disabled }: Props): PanelParts | null {
  const { claudeAvailable } = useMeta();
  const [args, setArgs] = useState<Rec>({});
  const [open, setOpen] = useState(false);
  const { job, error, running, start, setError } = useGenerateJob((id) => {
    setOpen(false);
    onDone(id);
  });

  const generators = matchingGenerators(meta, draft, mode, true);
  if (generators.length === 0) return null;
  // 今のところ panel な生成器は table ごとに一つだけを想定(複数あれば最初のものを開く)
  const generator = generators[0];
  const params = generator.params ?? [];
  const instructionParam = params.find((param: ColumnMeta) => param.section);
  const otherParams = params.filter((param: ColumnMeta) => param !== instructionParam);
  const missingRequired = params.some((param: ColumnMeta) => param.required && isEmpty(args[param.key]));

  const run = async () => {
    setError(null);
    if (!(await beforeRun())) return;
    const mine: Rec = {};
    for (const param of params) if (!isEmpty(args[param.key])) mine[param.key] = args[param.key];
    await start(() => generateRecord(table, generator.key, compactDraft(draft), mine));
  };

  const toggle = (
    <button
      type="button"
      className={open ? "on" : ""}
      onClick={() => setOpen(!open)}
      disabled={disabled || !claudeAvailable || open}
      title={claudeAvailable ? T.generate.description(mode) : T.generate.unavailable}
    >
      {generator.label}
    </button>
  );

  if (!open) return { toggle, body: null };

  const body = (
    <div className="revise-panel open">
      <div className="revise-head">
        <strong>{generator.label}</strong>
        <button type="button" onClick={() => setOpen(false)} disabled={running}>
          {T.generate.close}
        </button>
      </div>
      {!claudeAvailable && <div className="status error">{T.generate.unavailable}</div>}
      <div className="revise-body">
        {instructionParam && (
          <div key={instructionParam.key} className="field section">
            <label title={instructionParam.comment ?? ""}>
              {instructionParam.label}
              <span className="key">{instructionParam.key}</span>
              {instructionParam.required && <span className="hint">{T.required}</span>}
            </label>
            <FieldInput column={instructionParam} value={args[instructionParam.key]} onChange={(v) => setArgs({ ...args, [instructionParam.key]: v })} disabled={running} />
          </div>
        )}
        <div className="revise-fields">
          {otherParams.map((param) => (
            <div key={param.key} className="field">
              <label title={param.comment ?? ""}>
                {param.label}
                <span className="key">{param.key}</span>
                {param.required && <span className="hint">{T.required}</span>}
              </label>
              <FieldInput column={param} value={args[param.key]} onChange={(v) => setArgs({ ...args, [param.key]: v })} disabled={running} />
            </div>
          ))}
          {/* 開くボタン(actionbar の generator.label = 「AI で推敲する」)と区別するため、実行するボタンはここだけ「実行」にする */}
          <button className="primary" onClick={run} disabled={disabled || running || !claudeAvailable || missingRequired} title={T.generate.description(mode)}>
            実行
          </button>
        </div>
        {running && job && <div className="hint">{T.generate.inProgress(job.id, job.status)}</div>}
        {error && <div className="status error">{error}</div>}
      </div>
    </div>
  );

  return { toggle, body };
}
