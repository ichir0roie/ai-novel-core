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
 * 生成はまとめて一つのボタン・欄で出す。`separate` の生成だけは、同じ名前の欄(model など)を他と分けるため、
 * 自分だけのボタン・欄で出す。開ける欄は一度に一つ。
 * 指定できる欄(params)が無ければボタン自体がその場で実行し、`body` は結果待ち・エラーの表示だけになる。
 * 大きな専用パネルで出す推敲(`panel: true`)は `useRevisePanel` の担当なので、ここでは出さない。 */
export function useGeneratePanel({ table, meta, draft, mode, onDone, disabled }: Props): PanelParts | null {
  const { claudeAvailable } = useMeta();
  const [openGroup, setOpenGroup] = useState<string | null>(null);
  const [args, setArgs] = useState<Record<string, Rec>>({});
  const { job, error, running, start, setError } = useGenerateJob((id) => {
    setOpenGroup(null);
    onDone(id);
  });

  const generators = matchingGenerators(meta, draft, mode, false);
  if (generators.length === 0) return null;

  const groups = [generators.filter((g) => !g.separate), ...generators.filter((g) => g.separate).map((g) => [g])]
    .filter((group) => group.length > 0)
    .map((group) => {
      const params = new Map<string, ColumnMeta>();
      for (const generator of group) for (const param of generator.params ?? []) params.set(param.key, param);
      return { key: group.map((g) => g.key).join("/"), generators: group, params: [...params.values()] };
    });

  // 下書きにも同じ欄がある指定は、触るまで下書きの値を出して渡す
  const valueOf = (group: string, key: string) => {
    const mine = args[group] ?? {};
    return key in mine ? mine[key] : draft[key];
  };

  const run = async (group: string, generator: GeneratorMeta) => {
    setError(null);
    const mine: Rec = {};
    for (const param of generator.params ?? []) if (!isEmpty(valueOf(group, param.key))) mine[param.key] = valueOf(group, param.key);
    await start(() => generateRecord(table, generator.key, compactDraft(draft), mine));
  };

  const status = (running && job && <div className="hint">{T.generate.inProgress(job.id, job.status)}</div>) || (error && <div className="status error">{error}</div>);

  const toggle = (
    <>
      {groups.map((group) =>
        // 指定できる欄が無い生成(character の「AI で補完」など)は、開閉を挟まずボタンがそのまま実行する
        group.params.length === 0 ? (
          group.generators.map((generator) => (
            <button key={generator.key} onClick={() => run(group.key, generator)} disabled={disabled || running || !claudeAvailable} title={T.generate.description(mode)}>
              {generator.label}
            </button>
          ))
        ) : (
          <button
            key={group.key}
            type="button"
            className={openGroup === group.key ? "on" : ""}
            onClick={() => setOpenGroup(openGroup === group.key ? null : group.key)}
            disabled={disabled || !claudeAvailable}
            title={claudeAvailable ? T.generate.description(mode) : T.generate.unavailable}
          >
            {group.generators.map((g) => g.label).join(" / ")}
          </button>
        ),
      )}
    </>
  );

  const opened = groups.find((group) => group.key === openGroup && group.params.length > 0);
  if (!opened) return { toggle, body: status ? <div className="panel generate">{status}</div> : null };

  const field = (param: ColumnMeta) => (
    <div key={param.key} className={param.section ? "field section auto" : "field"}>
      <label title={param.comment ?? ""}>
        {param.label}
        <span className="key">{param.key}</span>
      </label>
      <FieldInput
        column={param}
        value={valueOf(opened.key, param.key)}
        onChange={(v) => setArgs({ ...args, [opened.key]: { ...(args[opened.key] ?? {}), [param.key]: v } })}
        disabled={running}
        autoHeight={param.section}
      />
    </div>
  );
  const buttons = (
    <div className="generate-buttons">
      {opened.generators.map((generator) => (
        <button key={generator.key} className="primary" onClick={() => run(opened.key, generator)} disabled={disabled || running || !claudeAvailable} title={T.generate.description(mode)}>
          {generator.label}
        </button>
      ))}
    </div>
  );
  // 注文のような長い文の欄(section)は幅いっぱいに置き、残りの欄と実行ボタンをその下の一行に並べる
  const sections = opened.params.filter((param) => param.section);
  const others = opened.params.filter((param) => !param.section);

  return {
    toggle,
    body: (
      <div className="panel generate">
        {!claudeAvailable && <div className="status error">{T.generate.unavailable}</div>}
        {sections.length > 0 ? (
          <div className="generate-stack">
            {sections.map(field)}
            <div className="generate-row">
              {others.map(field)}
              {buttons}
            </div>
          </div>
        ) : (
          <div className="form">
            {others.map(field)}
            {buttons}
          </div>
        )}
        {status}
      </div>
    ),
  };
}
