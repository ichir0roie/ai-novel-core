"use client";

import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import CharacterSheetModal from "@/components/CharacterSheetModal";
import Modal from "@/components/Modal";
import { useOptions } from "@/components/ReferenceSelect";
import { getRecord, getRelations, labelOf, type ColumnMeta, type Relation, type RecordResponse } from "@/lib/api";
import { useTable } from "@/lib/meta";
import { ageAt, parseStamp } from "@/lib/stamp";
import { T } from "@/lib/text";

// 登場人物の欄で別に並べるので、基本の欄には出さない
const CHARACTER_COLUMNS = new Set(["character_ids", "mentioned_character_ids"]);

/** 関係の年(`start`〜`end`)が `year` 年を含むか。人物相関図(`/relations`)の年での絞り込みと同じ数え方。時刻の無い話は絞らない。 */
const inYear = (relation: Relation, year: number | null) =>
  year === null || ((relation.start == null || relation.start <= year) && (relation.end == null || relation.end > year));

type Props = {
  episodeId: number;
  onClose: () => void;
};

/** タイムラインで押した話を見るモーダル(閲覧専用)。基本の欄と登場人物(話の開始の時点の歳と、その時点の関係)を左に、
 * 本文などの長い欄を右に置く。直すときは右下のボタンで話のページを別タブに開く。 */
export default function EpisodeSheetModal({ episodeId, onClose }: Props) {
  const meta = useTable("episode");
  const characters = useOptions("character");
  const [loaded, setLoaded] = useState<RecordResponse | null>(null);
  const [relations, setRelations] = useState<Relation[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [viewing, setViewing] = useState<number | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([getRecord("episode", episodeId), getRelations()])
      .then(([record, graph]) => {
        if (!active) return;
        setLoaded(record);
        setRelations(graph.relations);
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
  const year = parseStamp(start)?.year ?? null;
  const characterIds = (record?.character_ids as number[] | undefined) ?? [];
  const mentionedIds = (record?.mentioned_character_ids as number[] | undefined) ?? [];
  const nameOf = (id: number) => byId.get(id)?.label ?? loaded?.labels?.character_ids?.[id] ?? `id=${id}`;
  const withAge = (id: number) => {
    const age = ageAt(byId.get(id)?.born ?? null, start);
    return age === null ? nameOf(id) : `${nameOf(id)}(${age})`;
  };

  const shown = (column: ColumnMeta, value: unknown): string => {
    if (value === null || value === undefined || value === "") return "—";
    if (column.references) return labelOf(loaded?.labels, column.key, value) || `id=${value}`;
    if (typeof value === "boolean") return value ? T.yes : T.no;
    return String(value);
  };

  const columns = meta?.columns ?? [];
  const plain = columns.filter((c) => !c.section && c.key !== meta?.label_column && !CHARACTER_COLUMNS.has(c.key));
  const sections = columns.filter((c) => c.section);
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
    <>
      <Modal
        title={record && meta ? `${meta.label}: ${(title && (record[title.key] as string | null)) || loaded.label || `id=${episodeId}`}` : T.loading}
        onClose={onClose}
        actions={actions}
        wide
      >
        {error && <div className="status error">{error}</div>}
        {!record || !meta || !relations ? (
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
              {characterIds.length === 0 ? (
                <span className="hint">{T.episodeCharacters.none}</span>
              ) : (
                <div className="episode-sheet-characters">
                  {characterIds.map((id) => {
                    // その人物から見た関係のうち、話の年に続いているもの。この話に出る相手を先に並べる
                    const own = relations
                      .filter((r) => r.character_1_id === id && inYear(r, year))
                      .sort((a, b) => Number(characterIds.includes(b.character_2_id)) - Number(characterIds.includes(a.character_2_id)));
                    return (
                      <div key={id} className="episode-sheet-character">
                        <button type="button" className="character-open" onClick={() => setViewing(id)}>
                          {withAge(id)}
                        </button>
                        {own.length === 0 ? (
                          <span className="hint">{T.episodeSheet.noRelations}</span>
                        ) : (
                          <span className="episode-sheet-relations">
                            {own.map((r) => (
                              <span key={r.id} className={`episode-sheet-relation ${characterIds.includes(r.character_2_id) ? "here" : ""}`}
                                title={[T.span(r.start, r.end), r.text].filter(Boolean).join("\n")}>
                                {T.episodeSheet.relation(nameOf(r.character_2_id), r.relation ?? "")}
                              </span>
                            ))}
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
              {mentionedIds.length > 0 && (
                <div className="hint episode-sheet-mentioned">{T.episodeSheet.mentioned(mentionedIds.map(nameOf).join(" / "))}</div>
              )}
            </div>

            <div className="record-text">
              {sections.map((column) => {
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
      {viewing !== null && <CharacterSheetModal characterId={viewing} time={start} onClose={() => setViewing(null)} />}
    </>
  );
}
