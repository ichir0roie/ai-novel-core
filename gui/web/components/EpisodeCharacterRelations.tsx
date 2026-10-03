"use client";

import { useEffect, useMemo, useState } from "react";
import CharacterSheetModal from "@/components/CharacterSheetModal";
import { useOptions } from "@/components/ReferenceSelect";
import { getRelations, type Relation } from "@/lib/api";
import { ageAt, parseStamp } from "@/lib/stamp";
import { T } from "@/lib/text";

/** 関係の年(`start`〜`end`)が `year` 年を含むか。人物相関図(`/relations`)の年での絞り込みと同じ数え方。時刻の無い話は絞らない。 */
const inYear = (relation: Relation, year: number | null) =>
  year === null || ((relation.start == null || relation.start <= year) && (relation.end == null || relation.end > year));

type Props = {
  characterIds: number[];
  /** 話の開始(`episode.start`)。歳と、どの年の関係を出すかに使う */
  start: unknown;
  /** 人物の選択肢に無い id の名前(`RecordResponse.labels.character_ids`) */
  fallbackLabels?: Record<string | number, string>;
  /** 初めは名前と歳だけを一行に並べ、ボタンを押すと関係ごとの並びに開く。話のページで下のプロットを押し縮めないため */
  collapsible?: boolean;
};

/** 話の登場人物ごとに、話の開始の時点の歳と、その時点の登場人物どうしの関係を並べる(閲覧専用)。
 * 名前を押すと、その人物を話の開始の時点で見るモーダル(`CharacterSheetModal`)を開く。 */
export default function EpisodeCharacterRelations({ characterIds, start, fallbackLabels, collapsible = false }: Props) {
  const characters = useOptions("character");
  const [relations, setRelations] = useState<Relation[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [viewing, setViewing] = useState<number | null>(null);
  const [expanded, setExpanded] = useState(!collapsible);

  useEffect(() => {
    if (!expanded || relations) return;
    let active = true;
    getRelations()
      .then((graph) => {
        if (active) setRelations(graph.relations);
      })
      .catch((e: Error) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [expanded, relations]);

  const byId = useMemo(() => new Map(characters.map((o) => [o.id, o])), [characters]);
  const time = typeof start === "string" ? start : null;
  const year = parseStamp(time)?.year ?? null;
  const nameOf = (id: number) => byId.get(id)?.label ?? fallbackLabels?.[id] ?? `id=${id}`;
  const withAge = (id: number) => {
    const age = ageAt(byId.get(id)?.born ?? null, time);
    return age === null ? nameOf(id) : `${nameOf(id)}(${age})`;
  };

  if (characterIds.length === 0) return <span className="hint">{T.episodeCharacters.none}</span>;

  const sheet = viewing !== null && <CharacterSheetModal characterId={viewing} time={start} onClose={() => setViewing(null)} />;
  const toggle = collapsible && (
    <button type="button" className="episode-relations-toggle" onClick={() => setExpanded(!expanded)}>
      {T.episodeSheet.toggleRelations(expanded)}
    </button>
  );

  if (!expanded) {
    return (
      <div className="episode-sheet-characters collapsed">
        <span className="episode-sheet-character">
          {characterIds.map((id, i) => (
            <span key={id}>
              {i > 0 && " / "}
              <button type="button" className="character-open" onClick={() => setViewing(id)}>
                {withAge(id)}
              </button>
            </span>
          ))}
        </span>
        {toggle}
        {sheet}
      </div>
    );
  }
  if (error) return <div className="status error">{error}</div>;
  if (!relations) return <span className="hint">{T.loading}</span>;

  return (
    <>
      <div className="episode-sheet-characters">
        {toggle && <div>{toggle}</div>}
        {characterIds.map((id) => {
          // その人物から見た関係のうち、話の年に続いていて、相手もこの話に出るもの
          const own = relations.filter((r) => r.character_1_id === id && characterIds.includes(r.character_2_id) && inYear(r, year));
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
                    <span key={r.id} className="episode-sheet-relation"
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
      {sheet}
    </>
  );
}
