"use client";

import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import EpisodeCharacterRelations from "@/components/EpisodeCharacterRelations";
import Modal from "@/components/Modal";
import { useOptions } from "@/components/ReferenceSelect";
import { getRecord, labelOf, type ColumnMeta, type RecordResponse } from "@/lib/api";
import { useTable } from "@/lib/meta";
import { T } from "@/lib/text";

// 登場人物の欄で別に並べるので、基本の欄には出さない
const CHARACTER_COLUMNS = new Set(["character_ids", "mentioned_character_ids"]);

type Props = {
  episodeId: number;
  onClose: () => void;
};

/** 本文の冒頭を見せる欄。全文は話のページで読むので、空行を詰めて 5 行で切る(CSS の line-clamp)。 */
function ClampedText({ column, value }: { column: ColumnMeta; value: string | null }) {
  const text = value?.replace(/\n\s*\n+/g, "\n").trim();
  return (
    <div className="field episode-sheet-text">
      <label>{column.label}</label>
      {text ? (
        <div className="episode-sheet-box">
          <div className="episode-sheet-clamp">{text}</div>
        </div>
      ) : (
        <span className="hint">{T.characterSheet.noText}</span>
      )}
    </div>
  );
}

/** タイムラインで押した話を見るモーダル(閲覧専用)。左に基本の欄と登場人物(話の開始の時点の歳と、その時点の関係)、
 * その下端に本文の冒頭を、右にプロットの全文を置く。直すときは右下のボタンで話のページを別タブに開く。 */
export default function EpisodeSheetModal({ episodeId, onClose }: Props) {
  const meta = useTable("episode");
  const characters = useOptions("character");
  const [loaded, setLoaded] = useState<RecordResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getRecord("episode", episodeId)
      .then((record) => {
        if (active) setLoaded(record);
      })
      .catch((e: Error) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [episodeId]);

  const byId = useMemo(() => new Map(characters.map((o) => [o.id, o])), [characters]);
  const record = loaded?.record;
  const start = record?.start ?? null;
  const characterIds = (record?.character_ids as number[] | undefined) ?? [];
  const mentionedIds = (record?.mentioned_character_ids as number[] | undefined) ?? [];
  const nameOf = (id: number) => byId.get(id)?.label ?? loaded?.labels?.character_ids?.[id] ?? `id=${id}`;

  const shown = (column: ColumnMeta, value: unknown): string => {
    if (value === null || value === undefined || value === "") return "—";
    if (column.references) return labelOf(loaded?.labels, column.key, value) || `id=${value}`;
    if (typeof value === "boolean") return value ? T.yes : T.no;
    return String(value);
  };

  const columns = meta?.columns ?? [];
  const plain = columns.filter((c) => !c.section && c.key !== meta?.label_column && !CHARACTER_COLUMNS.has(c.key));
  const sections = columns.filter((c) => c.section);
  // プロットは話のページでは左に置く欄(side)、本文はそれ以外の長い欄
  const plots = sections.filter((c) => c.side);
  const bodies = sections.filter((c) => !c.side);
  const title = meta?.columns.find((c) => c.key === meta.label_column);
  const pageUrl = `/tables/episode/${episodeId}`;

  const actions = (
    <>
      <span className="spacer" />
      <button onClick={onClose}>{T.close}</button>
      <button className="primary" onClick={() => window.open(pageUrl, "_blank", "noopener,noreferrer")}>
        {T.timeline.openInNewTab}
      </button>
    </>
  );

  return (
    <Modal
      title={record && meta ? `${meta.label}: ${(title && (record[title.key] as string | null)) || loaded.label || `id=${episodeId}`}` : T.loading}
      onClose={onClose}
      actions={actions}
      wide
    >
      {error && <div className="status error">{error}</div>}
      {!record || !meta ? (
        !error && <div className="status info">{T.loading}</div>
      ) : (
        <div className="record split character-sheet episode-sheet">
          <div className="record-side">
            <h3>{T.characterSheet.record}</h3>
            <dl className="sheet-fields">
              {plain.map((column) => (
                <div key={column.key}>
                  <dt>{column.label}</dt>
                  <dd>{shown(column, record[column.key])}</dd>
                </div>
              ))}
            </dl>

            <h3>{T.episodeSheet.characters(characterIds.length, typeof start === "string" ? start : null)}</h3>
            <EpisodeCharacterRelations characterIds={characterIds} start={start} fallbackLabels={loaded.labels?.character_ids} />
            {mentionedIds.length > 0 && (
              <div className="hint episode-sheet-mentioned">{T.episodeSheet.mentioned(mentionedIds.map(nameOf).join(" / "))}</div>
            )}
            {bodies.map((column) => <ClampedText key={column.key} column={column} value={record[column.key] as string | null} />)}
          </div>

          <div className="record-text">
            {plots.map((column) => {
              const value = record[column.key] as string | null;
              return (
                <div key={column.key} className="field section auto">
                  <label>{column.label}</label>
                  <div className="section markdown-preview auto sheet-text">
                    {!value ? (
                      <span className="hint">{T.characterSheet.noText}</span>
                    ) : column.markdown === false ? (
                      <div className="sheet-plain">{value}</div>
                    ) : (
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{value}</ReactMarkdown>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </Modal>
  );
}
