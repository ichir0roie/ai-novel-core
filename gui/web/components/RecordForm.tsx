"use client";

import { useState, type ReactNode } from "react";
import type { Rec, TableMeta } from "@/lib/api";
import ChildListEditor, { type ExtraColumn } from "./ChildListEditor";
import EpisodeCharacters from "./EpisodeCharacters";
import FieldInput from "./FieldInput";
import { Spec } from "./Hint";
import { childListHint, columnHint } from "@/lib/hint";
import { useLocationCharacterIds } from "@/lib/locationCharacters";
import { ageAt, ageInYear } from "@/lib/stamp";
import { T } from "@/lib/text";

/** 期間ごとの居場所・パラメータの開始・終了それぞれの隣に、その時点の人物の年齢を出す(人物の start が生年)。
 * 年齢は人物固有の概念なので、人物テーブルの期間子リストにだけ足す。 */
function ageColumns(birth: unknown): ExtraColumn[] {
  return [
    { key: "start_age", after: "start", label: T.record.ageAt, render: (row) => formatAge(ageAt(birth, row.start)) },
    { key: "end_age", after: "end", label: T.record.ageAt, render: (row) => formatAge(ageAt(birth, row.end)) },
  ];
}

function formatAge(age: number | null): string {
  return age === null ? "—" : String(age);
}

/** 来歴の始まりの年の隣に、その年に迎える歳を出す(年が未定・生年が無いときは出さない)。 */
export function historyAgeColumns(birth: unknown): ExtraColumn[] {
  return [{
    key: "start_age", after: "start", label: T.record.ageAt,
    render: (row) => {
      const age = ageInYear(birth, row.start);
      return age === null ? null : T.record.ageInYear(age);
    },
  }];
}

/** 人物の来歴に足す行の知る相手。API が knowers の無い新しい行を本人だけが知る行にするのと揃え、画面でも本人を出しておく
 * (本人を出さずに知る相手を足すと、本人の知らない行になる)。まだ id の無い人物は API の既定に任せる。 */
function selfKnowers(id: unknown): Rec[] | undefined {
  return typeof id === "number" ? [{ knower_id: id, location_id: null, start: null }] : undefined;
}

type Props = {
  meta: TableMeta;
  value: Rec;
  onChange: (value: Rec) => void;
  mode: "create" | "edit";
  /** 見出しの名前(label_column の欄。クリックで直せる)の右に添えるもの(テーブル名・id など) */
  titleNote?: ReactNode;
  /** 見出しの下に置くもの(保存の結果・エラーなど) */
  header?: ReactNode;
  /** 左の欄の末尾に置くもの(関連の一覧など) */
  side?: ReactNode;
  /** 左の欄の一番下に置く保存系のボタン列 */
  actions?: ReactNode;
  /** 渡すと右半分にこれを置き、本文(section の列)は左の欄の下に回す(作品の話の一覧など) */
  aside?: ReactNode;
};

/** 見出しとして出す名前の欄。クリックすると入力欄になり、Enter・Esc・フォーカスが外れると見出しに戻る。 */
function EditableTitle({ value, placeholder, onChange }: { value: string; placeholder: string; onChange: (value: string) => void }) {
  const [editing, setEditing] = useState(false);
  if (editing) {
    return (
      <input
        type="text"
        className="title-input"
        autoFocus
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        onBlur={() => setEditing(false)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === "Escape") e.currentTarget.blur();
        }}
      />
    );
  }
  return (
    <h1 className={`title-editable ${value ? "" : "empty"}`} title={T.record.clickToEdit} onClick={() => setEditing(true)}>
      {value || placeholder}
    </h1>
  );
}

/** スキーマの列の情報(`/api/tables`)から組み立てるフォーム。値は親が持つ。
 * 本文(section の列)は右半分で、他の欄と side は左半分に並べる。左右それぞれが独立にスクロールする。狭い画面では縦に積む。 */
export default function RecordForm({ meta, value, onChange, mode, titleNote, header, side, actions, aside }: Props) {
  const set = (key: string, v: unknown) => onChange({ ...value, [key]: v });
  const columns = meta.columns.filter((column) => (mode === "create" ? column.key !== "id" && !column.readonly : !column.create_only));
  // 名前の欄は見出しで直し、id は見出しの横に出すので、フォームには並べない
  const titleColumn = columns.find((c) => c.key === meta.label_column && c.type === "string" && !c.section && !c.readonly);
  // episode の登場人物(character_ids)は、通常のフォーム欄ではなく「time & place」の行のボタン
  // (EpisodeCharacters。side の Related 経由)で編集するので、編集画面では二重に出さない
  const plain = columns.filter((c) => !c.section && c !== titleColumn && c.key !== "id"
    && !(mode === "edit" && meta.name === "episode" && c.key === "character_ids"));
  const textLeft = aside !== undefined;
  const sections = columns.filter((c) => c.section && !c.side && !textLeft);
  const sideSections = columns.filter((c) => c.section && (c.side || textLeft));
  // display が "flow" の子リスト(アイデアの呼び名など)は本文(section)の下に続けて出す。それ以外は左の欄に並べる
  const sideChildLists = meta.child_lists.filter((c) => c.display !== "flow");
  const flowChildLists = meta.child_lists.filter((c) => c.display === "flow");
  // episode の視点の人物は、絞り込み欄が空ならフォームの場所・時刻にいる人物だけを候補に出す
  const locationCharacterIds = useLocationCharacterIds(value.location_id, value.start, meta.name === "episode");
  // 人物の本文は欄が多く長いので、初めは枠に収まる行数だけ出して畳む
  const collapsible = meta.name === "character";

  const flowLists = (
    <>
      {flowChildLists.map((child) => (
        <div key={child.name} className="field wide">
          <label>
            <Spec hint={childListHint(child)}>{child.name}</Spec>
          </label>
          <ChildListEditor
            meta={child}
            rows={(value[child.name] as Rec[] | undefined) ?? []}
            onChange={(rows) => set(child.name, rows)}
            extraColumns={meta.name === "character" && child.name === "histories" ? historyAgeColumns(value.start) : undefined}
            newRowKnowers={meta.name === "character" && child.name === "histories" ? selfKnowers(value.id) : undefined}
          />
        </div>
      ))}
    </>
  );

  return (
    <div className={`record ${sections.length || textLeft ? "split" : ""}`}>
      <div className="record-side">
        <div className="record-header">
          <div className="title-line">
            {titleColumn && (
              <EditableTitle
                value={(value[titleColumn.key] as string | null) ?? ""}
                placeholder={titleColumn.required ? `${titleColumn.key} (${T.required})` : titleColumn.key}
                onChange={(v) => set(titleColumn.key, v === "" && titleColumn.nullable ? null : v)}
              />
            )}
            {titleNote && <span className="hint">{titleNote}</span>}
          </div>
          {header}
        </div>
        <div className="form">
          {plain.map((column) => (
            <div key={column.key} className={`field ${column.type === "id_list" || column.type === "json" ? "wide" : ""}`}>
              <label>
                <Spec hint={columnHint(column)}>{column.key}</Spec>
                {column.required && <span className="hint">{T.required}</span>}
              </label>
              {meta.name === "episode" && column.key === "character_ids" ? (
                // 全人物のチェック欄は縦に長く、下のプロットを押し縮めるので、ボタンからモーダルで選ぶ
                <div className="episode-characters-field">
                  <EpisodeCharacters
                    characterIds={(value.character_ids as number[] | null) ?? []}
                    onChange={(ids) => set("character_ids", ids)}
                    episodeStart={value.start}
                    episodeLocationId={value.location_id}
                  />
                </div>
              ) : (
                <FieldInput column={column} value={value[column.key]} onChange={(v) => set(column.key, v)}
                  defaultIds={column.key === "viewpoint_character_id" ? locationCharacterIds : null} />
              )}
            </div>
          ))}
        </div>
        {sideChildLists.map((child) => (
          <div key={child.name} className="field wide" style={{ marginTop: "1rem" }}>
            <label>
              <Spec hint={childListHint(child)}>{child.name}</Spec>
            </label>
            <ChildListEditor
              meta={child}
              rows={(value[child.name] as Rec[] | undefined) ?? []}
              onChange={(rows) => set(child.name, rows)}
              extraColumns={child.display === "periodic" && meta.name === "character" ? ageColumns(value.start) : undefined}
            />
          </div>
        ))}
        {side}
        {sideSections.map((column) => (
          <div key={column.key} className="field section side" style={{ marginTop: "1rem" }}>
            <label>
              <Spec hint={columnHint(column)}>{column.key}</Spec>
            </label>
            <FieldInput column={column} value={value[column.key]} onChange={(v) => set(column.key, v)} />
          </div>
        ))}
        {textLeft && flowLists}
        {actions && <div className="record-actions">{actions}</div>}
      </div>
      {textLeft && <div className="record-aside">{aside}</div>}
      {sections.length > 0 && (
        <div className="record-text">
          {sections.map((column) => (
            <div key={column.key} className={`field section ${flowChildLists.length > 0 || collapsible ? "auto" : ""}`}>
              <label>
                <Spec hint={columnHint(column)}>{column.key}</Spec>
              </label>
              <FieldInput column={column} value={value[column.key]} onChange={(v) => set(column.key, v)}
                autoHeight={flowChildLists.length > 0} collapsible={collapsible} />
            </div>
          ))}
          {!textLeft && flowLists}
        </div>
      )}
    </div>
  );
}

/** 足すときの初期値。boolean は false、それ以外は空。 */
export function emptyRecord(meta: TableMeta): Rec {
  const record: Rec = {};
  for (const column of meta.columns) {
    if (column.key === "id" || column.readonly) continue;
    record[column.key] = column.type === "boolean" ? false : column.type === "id_list" ? [] : null;
  }
  for (const child of meta.child_lists) record[child.name] = [];
  return record;
}
