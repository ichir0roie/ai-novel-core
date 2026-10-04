"use client";

import { Fragment, useEffect, useRef, useState, type FocusEvent, type ReactNode } from "react";
import type { ChildListMeta, ColumnMeta, Rec } from "@/lib/api";
import FieldInput, { AutoGrowTextarea, CHILD_FREEFORM_TEXT_KEYS } from "./FieldInput";
import { Spec } from "./Hint";
import KnowerList from "./KnowerList";
import Modal from "./Modal";
import NameId from "./NameId";
import { useOptions } from "./ReferenceSelect";
import StampInput from "./StampInput";
import { columnHint, columnsHint } from "@/lib/hint";
import { T } from "@/lib/text";

/** スキーマに無い、行から計算するだけの読み取り専用の列(居場所の期間から出す年齢など)。指定した列の右に挿む。 */
export type ExtraColumn = { key: string; label: string; after: string; render: (row: Rec) => ReactNode };

type Props = {
  meta: ChildListMeta;
  rows: Rec[];
  onChange: (rows: Rec[]) => void;
  extraColumns?: ExtraColumn[];
};

/** リードオンリーの表の一マス。参照列(場所など)は id ではなく名前で出す。 */
function ReadValue({ column, value }: { column: ColumnMeta; value: unknown }) {
  const options = useOptions(column.references ?? undefined);
  if (value == null || value === "") return <>—</>;
  if (column.references) {
    const option = options.find((o) => o.id === value);
    return <NameId name={option?.label} id={value} />;
  }
  if (column.type === "boolean") return <>{value ? T.yes : T.no}</>;
  if (Array.isArray(value) || typeof value === "object") return <>{JSON.stringify(value)}</>;
  return <>{String(value)}</>;
}

/** 空なら "—"、あれば stamp の日付部分だけ("11579/03/02 10:00:00" → "11579/03/02")。 */
function formatDateOnly(value: unknown): string {
  if (value == null || value === "") return "—";
  // 人物の来歴の始まりは年だけの整数
  if (typeof value === "number") return `${value}年`;
  return String(value).split(" ")[0];
}

/** 札 1 枚ぶん(項目名+値)。実在の列(誠実性など)だけでなく、期間・年齢のように
 * 複数の列から合成する項目もこの形にそろえて、同じ ChipGrid で並べられるようにする。 */
type Chip = { key: string; label: ReactNode; hint?: string; render: (row: Rec) => ReactNode };

/** 札・1 行の項目の名前。仕様があればかざすと出す。 */
function ChipLabel({ chip }: { chip: Chip }) {
  return chip.hint ? <Spec hint={chip.hint}>{chip.label}</Spec> : <>{chip.label}</>;
}

function chipOf(column: ColumnMeta): Chip {
  return {
    key: column.key,
    label: column.key,
    hint: columnHint(column),
    render: (row) => <ReadValue column={column} value={row[column.key]} />,
  };
}

/** 項目名を上、値を下に置く枠つきの小さな札。共有の見出し列に項目名を収めようとすると幅が合わず
 * 折り返しが崩れるので、見出し列には置かず、各期間(列)のマスの中に項目名ごと(重複して)書く。
 * 札の幅は中身まかせ(flex-wrap)で、決め打ちの列数・列幅は持たない。ラベルが長い札ほど自分の分だけ
 * 幅を取るので、短い札を無理に同じ幅へ広げて折り返させることがない。 */
function ChipGrid({ chips, row }: { chips: Chip[]; row: Rec }) {
  return (
    <div className="chipgrid">
      {chips.map((c) => (
        <div key={c.key} className="chip">
          <div className="chip-label"><ChipLabel chip={c} /></div>
          <div className="chip-value">{c.render(row)}</div>
        </div>
      ))}
    </div>
  );
}

/** 1 行を丸ごと使う項目(期間・体格など)。項目名と値を「キー | 値」で横に並べ、左詰めにする。 */
function SoloField({ chip, row }: { chip: Chip; row: Rec }) {
  return (
    <div className="solo-field">
      <span className="solo-key"><ChipLabel chip={chip} /></span>
      <span className="solo-sep">|</span>
      <span className="solo-value">{chip.render(row)}</span>
    </div>
  );
}

/** リードオンリーの表の 1 行ぶんの中身。項目が多いので、素朴に 1 項目 1 行にはせず、
 * 1 行を丸ごと使うだけの中身を持つ項目(期間・年齢・体格・口調・方言。期間・年齢は幅を目立たせたい、
 * 体格等は自由記述で長くなりがち)は 1 項目 1 行のまま上にまとめ、それ以外の値の短い項目
 * (一人称・二人称・三人称や性格など)はまとめて 1 行の札の並び(ChipGrid)にして下に置く。 */
type RowSpec = { key: string; label: ReactNode; render: (row: Rec) => ReactNode };

function buildRowSpecs(columns: ColumnMeta[], extraColumns: ExtraColumn[]): RowSpec[] {
  const byKey = new Map(columns.map((c) => [c.key, c]));
  const consumed = new Set<string>();
  const soloSpecs: RowSpec[] = [];

  if (byKey.has("start") && byKey.has("end")) {
    consumed.add("start");
    consumed.add("end");
    const startAge = extraColumns.find((e) => e.after === "start");
    const endAge = extraColumns.find((e) => e.after === "end");
    const period: Chip = { key: "__period", label: "start ~ end", hint: columnsHint([byKey.get("start"), byKey.get("end")]), render: (row) => `${formatDateOnly(row.start)} ~ ${formatDateOnly(row.end)}` };
    soloSpecs.push({ key: "__period", label: "", render: (row) => <SoloField chip={period} row={row} /> });
    if (startAge && endAge) {
      const age: Chip = { key: "__age", label: T.record.ageAt, render: (row) => `${startAge.render(row)} ~ ${endAge.render(row)}` };
      soloSpecs.push({ key: "__age", label: "", render: (row) => <SoloField chip={age} row={row} /> });
    }
  } else if (byKey.has("start")) {
    // 終わりを持たない行(人物のパラメータ・来歴)は、始まりから先ずっと効く
    consumed.add("start");
    const startAge = extraColumns.find((e) => e.after === "start");
    const since: Chip = { key: "__period", label: "start ~ end", hint: columnsHint([byKey.get("start")]), render: (row) => `${formatDateOnly(row.start)} ~` };
    soloSpecs.push({ key: "__period", label: "", render: (row) => <SoloField chip={since} row={row} /> });
    if (startAge) {
      const age: Chip = { key: "__age", label: T.record.ageAt, render: (row) => `${startAge.render(row)} ~` };
      soloSpecs.push({ key: "__age", label: "", render: (row) => <SoloField chip={age} row={row} /> });
    }
  }

  // 体格・口調・方言・呼び名の注釈は自由記述で長い文になりがちなので、札には収めず 1 項目 1 行のまま出す
  // (どの列が対象かは編集用の textarea 化(FieldInput)と共有する)
  const soloColumns = [...CHILD_FREEFORM_TEXT_KEYS].map((key) => byKey.get(key)).filter((c): c is ColumnMeta => c != null);
  for (const column of soloColumns) {
    consumed.add(column.key);
    const chip = chipOf(column);
    soloSpecs.push({ key: `__solo_${column.key}`, label: "", render: (row) => <SoloField chip={chip} row={row} /> });
  }

  const chips: Chip[] = [];
  for (const column of columns) {
    if (!consumed.has(column.key)) chips.push(chipOf(column));
  }

  const specs: RowSpec[] = [...soloSpecs];
  if (chips.length === 1) {
    // 残りが 1 項目だけなら、わざわざ札にせず他の 1 行セルと同じ「キー | 値」にする(例: 居場所の「場所」)
    const chip = chips[0];
    specs.push({ key: "__grid", label: "", render: (row) => <SoloField chip={chip} row={row} /> });
  } else if (chips.length > 1) {
    specs.push({ key: "__grid", label: "", render: (row) => <ChipGrid chips={chips} row={row} /> });
  }

  return specs;
}

/** リードオンリーの表(パラメータ・居場所など、display が "periodic" の子リスト)。
 * 列(期間)ごとに幅を固定し、はみ出す分は横スクロールで見せる。
 * クリック・ホバーの単位は列(期間・レコード)全体で、項目(マス)単位ではハイライトしない。 */
function ReadOnlyTable({ meta, rows, extraColumns, onOpen }: { meta: ChildListMeta; rows: Rec[]; extraColumns: ExtraColumn[]; onOpen: (index: number) => void }) {
  const rowSpecs = buildRowSpecs(meta.columns, extraColumns);
  const [hovered, setHovered] = useState<number | null>(null);
  const columnProps = (index: number) => ({
    className: `clickable${hovered === index ? " hover" : ""}`,
    onClick: () => onOpen(index),
    onMouseEnter: () => setHovered(index),
    onMouseLeave: () => setHovered(null),
  });
  return (
    <div className="scroll-x">
      <table>
        <thead>
          <tr>
            <th />
            {rows.map((_, index) => (
              <th key={index} style={{ minWidth: "26rem" }} {...columnProps(index)}>
                #{index + 1}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rowSpecs.map((spec) => (
            <tr key={spec.key}>
              <th scope="row">{spec.label}</th>
              {rows.map((row, index) => (
                <td key={index} {...columnProps(index)}>
                  {spec.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** 本文の下に続ける、上から下へ流れる札(display が "flow" の子リスト。アイデアの呼び名など)。
 * モーダルは開かず、札をクリックするとその場で編集用の入力に差し替わる(EditableTitle と同じ考え方)。
 * 1 行目に短い項目(番号・期間・呼び名・場所など)を横に並べ、2 行目に自由記述(注釈)を
 * 行数ぶんの高さの textarea(編集時)またはそのままの文章(表示時)で出す。 */
function FlowCard({
  meta, row, index, extraColumns, editing, onEdit, onStopEdit, onChange, onRemove,
}: {
  meta: ChildListMeta;
  row: Rec;
  extraColumns: ExtraColumn[];
  index: number;
  editing: boolean;
  onEdit: () => void;
  onStopEdit: () => void;
  onChange: (key: string, value: unknown) => void;
  onRemove: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const startColumn = meta.columns.find((c) => c.key === "start");
  const hasPeriod = startColumn !== undefined;
  const hasEnd = meta.columns.some((c) => c.key === "end");
  const longColumns = meta.columns.filter((c) => CHILD_FREEFORM_TEXT_KEYS.has(c.key));
  // 1 行目は 番号 → 名前 → 期間 → それ以外の短い項目(場所など)の順に並べる。
  const nameColumn = meta.columns.find((c) => c.key === "name");
  const otherLineColumns = meta.columns.filter(
    (c) => !CHILD_FREEFORM_TEXT_KEYS.has(c.key) && c.key !== "start" && c.key !== "end" && c.key !== "name");

  // カードの外をクリックするか、Tab でカードの外へ焦点が移ったら編集を終える。カードの欄から開いた選択のモーダル
  // (場所の木など)は body の直下に描かれるので、モーダルの中もカードの中とみなす。焦点の行き先(activeElement)では
  // 見ない: モーダルを開くと焦点がその入力欄へ、閉じると body へ落ち、どちらも「外へ出た」と取り違えてモーダルごと消える
  const outside = (target: EventTarget | null) =>
    target instanceof Element && !ref.current?.contains(target) && !target.closest(".modal-backdrop");
  useEffect(() => {
    if (!editing) return;
    const onPointerDown = (e: PointerEvent) => {
      if (outside(e.target)) onStopEdit();
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  });
  const stopIfTabbedOut = (e: FocusEvent) => {
    if (outside(e.relatedTarget)) onStopEdit();
  };

  return (
    <div ref={ref} className={`flow-card ${editing ? "editing" : ""}`} onClick={editing ? undefined : onEdit} onBlur={editing ? stopIfTabbedOut : undefined}>
      <div className="flow-line">
        <span className="flow-index">#{index + 1}</span>
        {nameColumn && (
          <div className="flow-field flow-name" data-hint={columnHint(nameColumn)}>
            {editing ? (
              <FieldInput column={nameColumn} value={row[nameColumn.key]} onChange={(v) => onChange(nameColumn.key, v)} compact />
            ) : (
              <ReadValue column={nameColumn} value={row[nameColumn.key]} />
            )}
          </div>
        )}
        {hasPeriod && (
          editing ? (
            <span className="flow-period-edit">
              {startColumn?.type === "integer" ? (
                <FieldInput column={startColumn} value={row.start} onChange={(v) => onChange("start", v)} compact />
              ) : (
                <StampInput value={(row.start as string | null) ?? null} onChange={(v) => onChange("start", v)} />
              )}
              <span className="solo-sep">~</span>
              {hasEnd && <StampInput value={(row.end as string | null) ?? null} onChange={(v) => onChange("end", v)} />}
            </span>
          ) : (
            <span className="flow-period" data-hint={columnsHint(meta.columns.filter((c) => c.key === "start" || c.key === "end"))}>
              {formatDateOnly(row.start)} ~ {hasEnd ? formatDateOnly(row.end) : ""}
            </span>
          )
        )}
        {extraColumns.filter((extra) => extra.after === "start").map((extra) => (
          <span key={extra.key} className="flow-period" title={extra.label}>{extra.render(row)}</span>
        ))}
        {otherLineColumns.map((column) => {
          // 真偽の欄は Yes / No だけでは何の欄か読めないので、欄の名前を添え、表示では立っているときだけ出す
          const flag = column.type === "boolean";
          if (flag && !editing && !row[column.key]) return null;
          return (
            <div key={column.key} className="flow-field" data-hint={flag ? undefined : columnHint(column)}>
              {flag && <span className="flow-flag"><Spec hint={columnHint(column)}>{column.key}</Spec></span>}
              {editing ? (
                <FieldInput column={column} value={row[column.key]} onChange={(v) => onChange(column.key, v)} compact />
              ) : (
                !flag && <ReadValue column={column} value={row[column.key]} />
              )}
            </div>
          );
        })}
        {editing && (
          <button type="button" className="ghost flow-remove" onClick={onRemove} title={T.childList.removeRow}>
            ×
          </button>
        )}
      </div>
      {longColumns.map((column) => (
        <div key={column.key} className="flow-detail">
          {editing ? (
            <AutoGrowTextarea value={(row[column.key] as string | null) ?? ""} onChange={(v) => onChange(column.key, v)} />
          ) : (
            <div className="flow-detail-text"><ReadValue column={column} value={row[column.key]} /></div>
          )}
        </div>
      ))}
      {meta.knowers && <KnowerList knowers={(row.knowers as Rec[] | null) ?? []} onChange={(knowers) => onChange("knowers", knowers)} />}
    </div>
  );
}

function FlowList({
  meta, rows, extraColumns, editingIndex, onEdit, onStopEdit, onChange, onRemove,
}: {
  meta: ChildListMeta;
  rows: Rec[];
  extraColumns: ExtraColumn[];
  editingIndex: number | null;
  onEdit: (index: number) => void;
  onStopEdit: () => void;
  onChange: (index: number, key: string, value: unknown) => void;
  onRemove: (index: number) => void;
}) {
  return (
    <div className="flowlist">
      {rows.map((row, index) => (
        <FlowCard
          key={index}
          meta={meta}
          row={row}
          index={index}
          extraColumns={extraColumns}
          editing={editingIndex === index}
          onEdit={() => onEdit(index)}
          onStopEdit={onStopEdit}
          onChange={(key, value) => onChange(index, key, value)}
          onRemove={() => onRemove(index)}
        />
      ))}
    </div>
  );
}

/** 子の行(期間ごとのパラメータなど)。並びで行が決まるので、行の入れ替えはしない。 */
export default function ChildListEditor({ meta, rows, onChange, extraColumns = [] }: Props) {
  const [editing, setEditing] = useState<number | null>(null);
  const readOnly = meta.display !== "table";
  const update = (index: number, key: string, value: unknown) =>
    onChange(rows.map((row, i) => (i === index ? { ...row, [key]: value } : row)));
  const remove = (index: number) => onChange(rows.filter((_, i) => i !== index));
  const add = () => {
    onChange([...rows, Object.fromEntries(meta.columns.map((c) => [c.key, c.type === "boolean" ? false : null]))]);
    if (readOnly) setEditing(rows.length);
  };
  const extrasAfter = (key: string) => extraColumns.filter((extra) => extra.after === key);

  return (
    <div className={`childlist ${readOnly ? "readonly" : ""} ${meta.display === "flow" ? "flow" : ""}`}>
      {meta.display === "flow" ? (
        <FlowList
          meta={meta}
          rows={rows}
          extraColumns={extraColumns}
          editingIndex={editing}
          onEdit={setEditing}
          onStopEdit={() => setEditing(null)}
          onChange={update}
          onRemove={(index) => { remove(index); setEditing(null); }}
        />
      ) : meta.display === "periodic" ? (
        <ReadOnlyTable meta={meta} rows={rows} extraColumns={extraColumns} onOpen={setEditing} />
      ) : (
        <div className="scroll-x">
          <table>
            <thead>
              <tr>
                <th />
                {meta.columns.map((column) => (
                  <Fragment key={column.key}>
                    <th><Spec hint={columnHint(column)}>{column.key}</Spec></th>
                    {extrasAfter(column.key).map((extra) => (
                      <th key={extra.key} className="hint">
                        {extra.label}
                      </th>
                    ))}
                  </Fragment>
                ))}
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={index}>
                  <td className="rowhead">{index + 1}</td>
                  {meta.columns.map((column) => (
                    <Fragment key={column.key}>
                      <td>
                        <FieldInput column={column} value={row[column.key]} onChange={(v) => update(index, column.key, v)} compact />
                      </td>
                      {extrasAfter(column.key).map((extra) => (
                        <td key={extra.key} className="readonly">
                          {extra.render(row)}
                        </td>
                      ))}
                    </Fragment>
                  ))}
                  <td>
                    <button type="button" className="ghost" onClick={() => remove(index)} title={T.childList.removeRow}>
                      ×
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <button type="button" onClick={add} style={{ marginTop: "0.4rem" }}>
        {T.childList.addRow}
      </button>
      {meta.display === "periodic" && editing !== null && rows[editing] && (
        <Modal
          title={`${meta.name} #${editing + 1}`}
          onClose={() => setEditing(null)}
          actions={
            <>
              <button type="button" className="danger" onClick={() => { remove(editing); setEditing(null); }}>
                {T.childList.removeRow}
              </button>
              <span className="spacer" />
              <button type="button" className="primary" onClick={() => setEditing(null)}>
                {T.childList.close}
              </button>
            </>
          }
        >
          <div className="form">
            {meta.columns.map((column) => (
              <div key={column.key} className="field">
                <label>
                  <Spec hint={columnHint(column)}>{column.key}</Spec>
                </label>
                <FieldInput column={column} value={rows[editing][column.key]} onChange={(v) => update(editing, column.key, v)} />
              </div>
            ))}
          </div>
        </Modal>
      )}
    </div>
  );
}
