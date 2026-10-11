"use client";

import { useEffect, useState } from "react";
import CharacterSheetModal from "@/components/CharacterSheetModal";
import NameId from "@/components/NameId";
import { getEpisodeNeighbors, getRecord, listAllRecords, runEntrance, type Rec } from "@/lib/api";
import { ageAt } from "@/lib/stamp";
import { T } from "@/lib/text";

/** 前の話の本文から添える末尾の行数。続きとして書き出す手がかりに足りる長さ */
const TAIL_LINES = 12;

const TABS = ["plot", "previous", "cast", "style"] as const;
type Tab = (typeof TABS)[number];

// 話し方と見た目のうち、本文を書くときに合わせる欄(人物のパラメータの列名)
const VOICE_KEYS = ["first_person", "second_person", "third_person", "tone", "dialect"] as const;
const LOOK_KEYS = ["build", "outfit"] as const;

type Previous = { id: number; title: string; tail: string } | null;
type CastMember = { id: number; sheet: Rec };

type Props = {
  episode: Rec;
};

/** 本文を自分で書くときの材料。プロット・前の話の終わり・登場人物の話し方と装い(話の時刻の値)・書き方(`style_preference`)を
 * タブで切り替えて見る。AI を回す材料(`ReadEpisodeBrief`)は GUI から呼べないので、db の行をそのまま引いて並べる。 */
export default function EpisodeMaterials({ episode }: Props) {
  const [tab, setTab] = useState<Tab>("plot");
  const [previous, setPrevious] = useState<Previous | undefined>(undefined);
  const [cast, setCast] = useState<CastMember[] | null>(null);
  const [styles, setStyles] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sheet, setSheet] = useState<number | null>(null);

  const episodeId = Number(episode.id);
  const start = episode.start;
  const viewpoint = episode.viewpoint_character_id as number | null;
  const characterIds = (episode.character_ids as number[] | null) ?? [];
  const castKey = characterIds.join(",");

  useEffect(() => {
    let alive = true;
    const fail = (e: unknown) => alive && setError(e instanceof Error ? e.message : String(e));
    getEpisodeNeighbors(episodeId)
      .then(async ({ previous: head }) => {
        if (!head) return null;
        const main = String((await getRecord("episode", head.id)).record.main_text ?? "");
        return { id: head.id, title: head.title, tail: main.trimEnd().split("\n").slice(-TAIL_LINES).join("\n") };
      })
      .then((result) => alive && setPrevious(result), fail);
    listAllRecords("style_preference", { sort: "id", order: "asc" })
      .then((rows) => Promise.all(rows.map((row) => getRecord("style_preference", Number(row.id)))))
      .then((results) => alive && setStyles(results.map((result) => String(result.record.text ?? ""))), fail);
    return () => {
      alive = false;
    };
  }, [episodeId]);

  useEffect(() => {
    let alive = true;
    const ids = castKey ? castKey.split(",").map(Number) : [];
    const time = typeof start === "string" && start.trim() !== "" ? start : null;
    Promise.all(
      ids.map((id) =>
        runEntrance("character.read_character.ReadCharacter", { character_id: id, time, count: 0 }).then((result) => ({
          id,
          sheet: result.result as Rec,
        })),
      ),
    )
      // 視点人物を先に置く
      .then((members) => alive && setCast(members.sort((a, b) => Number(b.id === viewpoint) - Number(a.id === viewpoint))))
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [castKey, start, viewpoint]);

  const plot = String(episode.plot_text ?? "");

  return (
    <details className="writer-materials" open>
      <summary>
        {T.writer.materials}
        <span className="writer-tabs" onClick={(e) => e.preventDefault()}>
          {TABS.map((key) => (
            <button key={key} type="button" className={`ghost${tab === key ? " on" : ""}`} onClick={() => setTab(key)}>
              {T.writer.tabs[key]}
            </button>
          ))}
        </span>
      </summary>
      <div className="writer-materials-body">
        {error && <div className="status error">{error}</div>}
        {tab === "plot" && (plot ? <div className="writer-plain">{plot}</div> : <span className="hint">{T.writer.noPlot}</span>)}
        {tab === "previous" &&
          (previous === undefined ? (
            <span className="hint">{T.loading}</span>
          ) : previous == null ? (
            <span className="hint">{T.writer.noPrevious}</span>
          ) : (
            <>
              <div className="meta">{T.writer.previousOf(T.nameId(previous.title, previous.id), TAIL_LINES)}</div>
              <div className="writer-plain">{previous.tail || T.writer.noPreviousText}</div>
            </>
          ))}
        {tab === "cast" &&
          (cast == null ? (
            <span className="hint">{T.loading}</span>
          ) : cast.length === 0 ? (
            <span className="hint">{T.writer.noCast}</span>
          ) : (
            cast.map(({ id, sheet: member }) => {
              const age = ageAt(member.start, start);
              return (
                <div key={id} className="writer-cast">
                  <div className="writer-cast-head">
                    <button type="button" className="ghost" onClick={() => setSheet(id)} title={T.writer.openSheet}>
                      <NameId name={String(member.name ?? "")} id={id} />
                    </button>
                    {id === viewpoint && <span className="writer-pov">{T.writer.viewpoint}</span>}
                    {age != null && <span className="meta">{T.record.ageInYear(age)}</span>}
                  </div>
                  <dl>
                    {[...VOICE_KEYS, ...LOOK_KEYS].map((key) =>
                      member[key] ? (
                        <div key={key}>
                          <dt>{T.writer.fields[key]}</dt>
                          <dd>{String(member[key])}</dd>
                        </div>
                      ) : null,
                    )}
                  </dl>
                </div>
              );
            })
          ))}
        {tab === "style" &&
          (styles == null ? (
            <span className="hint">{T.loading}</span>
          ) : styles.length === 0 ? (
            <span className="hint">{T.writer.noStyle}</span>
          ) : (
            <ul className="writer-styles">
              {styles.map((text, i) => (
                <li key={i}>{text}</li>
              ))}
            </ul>
          ))}
      </div>
      {sheet != null && <CharacterSheetModal characterId={sheet} time={start} onClose={() => setSheet(null)} />}
    </details>
  );
}
