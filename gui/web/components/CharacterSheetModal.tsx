"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Modal from "@/components/Modal";
import { runEntrance, type ColumnMeta, type RunResult } from "@/lib/api";
import { useTable } from "@/lib/meta";
import { ageAt } from "@/lib/stamp";
import { T } from "@/lib/text";

type History = { start: string | null; end: string | null; description: string };

/** `character.read_character.ReadCharacter` の結果。人物の列に、`time` の時点で重ねたパラメータが同じ段に並ぶ
 * (`data_access_logic/character/reading.py` の `CharacterSheet`)。 */
type CharacterSheet = Record<string, unknown> & {
  name: string | null;
  start: string | null;
  end: string | null;
  // `time` の時点に掛かる行だけ(時点が無ければすべて)
  histories: History[];
  location: { location_name: string | null } | null;
};

function shown(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? T.yes : T.no;
  return String(value);
}

// 人物詳細の「期間ごとの説明」の札と同じく、期間は日付の部分だけ出す
function dateOnly(value: string | null): string {
  return value ? value.split(" ")[0] : "—";
}

/** 性格の軸(無/低/並/高/必)を、選択肢の何段目かで塗る。 */
function LevelMeter({ column, value }: { column: ColumnMeta; value: unknown }) {
  const choices = column.choices ?? [];
  const level = choices.indexOf(String(value));
  return (
    <div className="sheet-level">
      <span className="sheet-level-label">{column.label}</span>
      <span className="sheet-level-cells">
        {choices.map((choice, i) => (
          <span key={choice} className={`sheet-level-cell ${i <= level ? "on" : ""}`} />
        ))}
      </span>
      <span className="sheet-level-value">{shown(value)}</span>
    </div>
  );
}

type Props = {
  characterId: number;
  // 話の開始。この時点のパラメータ・年齢・居場所と、この時点に掛かる説明・来歴を出す
  time: unknown;
  onClose: () => void;
};

/** 人物の基本の列・その時点のパラメータ・来歴を、大きなモーダルで見る(閲覧専用)。並びは人物詳細(RecordForm)と同じで、
 * 左に欄とパラメータ、右に期間ごとの説明(説明・来歴)を置き、左右それぞれがスクロールする(モーダル全体はスクロールしない)。 */
export default function CharacterSheetModal({ characterId, time, onClose }: Props) {
  const meta = useTable("character");
  const [sheet, setSheet] = useState<CharacterSheet | null>(null);
  const [error, setError] = useState<string | null>(null);
  const at = typeof time === "string" && time.trim() !== "" ? time : null;

  useEffect(() => {
    let active = true;
    runEntrance("character.read_character.ReadCharacter", { character_id: characterId, time: at, count: 0 })
      .then((response) => {
        if (active) setSheet((response as RunResult).result as CharacterSheet);
      })
      .catch((e: Error) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [characterId, at]);

  const column = (key: string) => meta?.columns.find((c) => c.key === key);
  const parameterColumns = (meta?.child_lists.find((c) => c.name === "parameters")?.columns ?? [])
    .filter((c) => c.key !== "start" && c.key !== "end");
  const historyLabel = meta?.child_lists.find((c) => c.name === "histories")?.label ?? "histories";
  const age = sheet ? ageAt(sheet.start, at) : null;
  // 時点で絞り、早い順に並べるのは core(`histories_at`)
  const histories = sheet?.histories ?? [];

  const actions = (
    <>
      <span className="spacer" />
      <Link href={`/tables/character/${characterId}`}>{T.openRecord}</Link>
    </>
  );

  return (
    <Modal title={sheet ? `${sheet.name ?? characterId}${age === null ? "" : `(${age})`}` : T.loading} onClose={onClose} actions={actions} wide>
      {error && <div className="status error">{error}</div>}
      {!sheet || !meta ? (
        !error && <div className="status info">{T.loading}</div>
      ) : (
        <div className="record split character-sheet">
          <div className="record-side">
            <h3>{T.characterSheet.record}</h3>
            <dl className="sheet-fields">
              {["id", "name", "kind", "main_character"].map((key) => (
                <div key={key}>
                  <dt>{column(key)?.label ?? key}</dt>
                  <dd>{shown(sheet[key])}</dd>
                </div>
              ))}
              <div>
                <dt>{T.characterSheet.born}</dt>
                <dd>{shown(sheet.start)}</dd>
              </div>
              <div>
                <dt>{T.characterSheet.died}</dt>
                <dd>{shown(sheet.end)}</dd>
              </div>
            </dl>

            <h3>{T.characterSheet.at(at)}</h3>
            <dl className="sheet-fields">
              <div>
                <dt>{T.characterSheet.age}</dt>
                <dd>{shown(age)}</dd>
              </div>
              <div>
                <dt>{T.characterSheet.location}</dt>
                <dd>{shown(sheet.location?.location_name)}</dd>
              </div>
              {parameterColumns.filter((c) => !c.choices).map((c) => (
                <div key={c.key}>
                  <dt>{c.label}</dt>
                  <dd>{shown(sheet[c.key])}</dd>
                </div>
              ))}
            </dl>
            <div className="sheet-levels">
              {parameterColumns.filter((c) => c.choices).map((c) => (
                <LevelMeter key={c.key} column={c} value={sheet[c.key]} />
              ))}
            </div>
          </div>

          <div className="record-text">
            <div className="field wide">
              <label>{historyLabel}</label>
              {histories.length === 0 ? (
                <span className="hint">{T.characterSheet.noHistory}</span>
              ) : (
                <div className="childlist flow">
                  <div className="flowlist">
                    {histories.map((history, i) => (
                      <div key={i} className="flow-card sheet-history">
                        <div className="flow-line">
                          <span className="flow-index">#{i + 1}</span>
                          <span className="flow-period">{dateOnly(history.start)} ~ {dateOnly(history.end)}</span>
                        </div>
                        <div className="flow-detail-text">{history.description}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </Modal>
  );
}
