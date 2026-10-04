"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  addHistoryKnowers,
  getCharacterLocations,
  listAllRecords,
  readKnowableHistories,
  type KnowableHistories,
  type Rec,
} from "@/lib/api";
import { buildCharacterTree, type TreeCharacter, type TreeNode } from "@/lib/characterTree";
import { buildIdeaTree, type IdeaNode } from "@/lib/ideaTree";
import { T } from "@/lib/text";
import Modal from "./Modal";
import NameId from "./NameId";
import { useOptions } from "./ReferenceSelect";
import StampInput from "./StampInput";

type Source = { kind: "character" | "idea"; id: number; name: string | null };

/** 選んだ行。来歴・履歴の行の id は人物とアイデアで重なりうるので、種類と組にして持つ */
type Picked = { kind: Source["kind"]; id: number; owner: Source; text: string };

const pickKey = (kind: Source["kind"], id: number) => `${kind}:${id}`;

/** 名前の一部か id(先頭の # は無くてよい)で当てる。 */
function matcher(filter: string): (name: string | null, id: number) => boolean {
  const q = filter.trim().toLowerCase();
  if (q === "") return () => true;
  const asId = q.replace(/^#/, "");
  return (name, id) => String(id) === asId || (name ?? "").toLowerCase().includes(q);
}

/** 当たる人物のいる場所だけを残す。 */
function filterLocations(nodes: TreeNode[], hit: (name: string | null, id: number) => boolean): TreeNode[] {
  return nodes.flatMap((node) => {
    const characters = node.characters.filter((c) => hit(c.name, c.id));
    const children = filterLocations(node.children, hit);
    if (characters.length === 0 && children.length === 0) return [];
    return [{ ...node, characters, children }];
  });
}

/** 当たるアイデアと、その祖先を残す(当たったアイデアの下位はそのまま出す)。 */
function filterIdeas(nodes: IdeaNode[], hit: (name: string | null, id: number) => boolean): IdeaNode[] {
  return nodes.flatMap((node) => {
    if (hit(node.name, node.id)) return [node];
    const children = filterIdeas(node.children, hit);
    return children.length > 0 ? [{ ...node, children }] : [];
  });
}

type TreeProps = { selected: Source | null; onSelect: (source: Source) => void };

function CharacterItem({ character, selected, onSelect }: TreeProps & { character: TreeCharacter }) {
  const on = selected?.kind === "character" && selected.id === character.id;
  return (
    <li className={`knowledge-item ${on ? "on" : ""}`} onClick={() => onSelect({ kind: "character", id: character.id, name: character.name })}>
      <NameId name={character.name} id={character.id} />
    </li>
  );
}

function LocationBranch({ node, ...props }: TreeProps & { node: TreeNode }) {
  return (
    <li>
      <details open>
        <summary className="knowledge-branch">
          <NameId name={node.name} id={node.id} />
        </summary>
        <ul className="tree">
          {node.characters.map((character) => (
            <CharacterItem key={character.id} character={character} {...props} />
          ))}
          {node.children.map((child) => (
            <LocationBranch key={child.id} node={child} {...props} />
          ))}
        </ul>
      </details>
    </li>
  );
}

function IdeaItem({ node, selected, onSelect }: TreeProps & { node: IdeaNode }) {
  const on = selected?.kind === "idea" && selected.id === node.id;
  const item = (
    <span
      className={`knowledge-item ${on ? "on" : ""}`}
      onClick={(e) => {
        // 見出しの中で押しても枝を開閉しない(開閉は印で行う)
        e.preventDefault();
        onSelect({ kind: "idea", id: node.id, name: node.name });
      }}
    >
      <NameId name={node.name} id={node.id} />
    </span>
  );
  if (node.children.length === 0) return <li>{item}</li>;
  return (
    <li>
      <details open>
        <summary className="knowledge-branch">{item}</summary>
        <ul className="tree">
          {node.children.map((child) => (
            <IdeaItem key={child.id} node={child} selected={selected} onSelect={onSelect} />
          ))}
        </ul>
      </details>
    </li>
  );
}

/** 行の知る相手を名前で並べる(読むだけ)。 */
function KnowerNames({ knowers }: { knowers: Rec[] }) {
  const characters = useOptions("character");
  const locations = useOptions("location");
  const characterLabels = useMemo(() => new Map(characters.map((o) => [o.id, o.label])), [characters]);
  const locationLabels = useMemo(() => new Map(locations.map((o) => [o.id, o.label])), [locations]);
  if (knowers.length === 0) return null;
  return (
    <div className="knowledge-knowers">
      <span className="flow-flag">{T.knowers.label}</span>
      {knowers.map((knower, index) => {
        const characterId = knower.knower_id as number | null;
        const locationId = knower.location_id as number;
        return (
          <span key={index} className="hint">
            {characterId !== null ? (
              <NameId name={characterLabels.get(characterId)} id={characterId} />
            ) : (
              <>
                {T.knowers.location}
                <NameId name={locationLabels.get(locationId)} id={locationId} />
              </>
            )}
            {knower.start != null && ` ${T.knowers.since(String(knower.start).split(" ")[0])}`}
          </span>
        );
      })}
    </div>
  );
}

type Props = { characterId: number; characterName: string; onClose: () => void };

/** 知識整理。左の人物・アイデアの木から一つ選ぶと、右にその来歴・履歴の行が並ぶ。行を押すと選んだ行に溜まり
 * (別の人物・アイデアに移っても残る)、登録で、この人物を溜めた行すべての知る相手に足す。
 * この人物自身の来歴は記録の画面で直すので、木には出さない(画面の編集中の値と食い違わないように)。 */
export default function KnowledgeModal({ characterId, characterName, onClose }: Props) {
  const [tree, setTree] = useState<{ locations: TreeNode[]; unplaced: TreeCharacter[]; ideas: IdeaNode[] } | null>(null);
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<Source | null>(null);
  const [histories, setHistories] = useState<KnowableHistories | null>(null);
  const [picked, setPicked] = useState<Map<string, Picked>>(new Map());
  const [since, setSince] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const locationLabels = new Map(useOptions("location").map((o) => [o.id, o.label]));

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      listAllRecords("location", { sort: "id", order: "asc" }),
      listAllRecords("character", { sort: "id", order: "asc" }),
      getCharacterLocations(),
      listAllRecords("idea", { sort: "id", order: "asc" }),
    ])
      .then(([locations, characters, characterLocations, ideas]) => {
        if (cancelled) return;
        const others = characters.filter((character) => Number(character.id) !== characterId);
        const characterTree = buildCharacterTree(locations, others, characterLocations.locations);
        setTree({ locations: characterTree.nodes, unplaced: characterTree.unplaced, ideas: buildIdeaTree(ideas) });
      })
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      cancelled = true;
    };
  }, [characterId]);

  const loadHistories = useCallback(async (source: Source) => {
    setHistories(null);
    try {
      setHistories(await readKnowableHistories(source.kind === "character" ? { character_id: source.id } : { idea_id: source.id }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  const select = (source: Source) => {
    setSelected(source);
    void loadHistories(source);
  };

  const toggle = (item: Picked) =>
    setPicked((prev) => {
      const next = new Map(prev);
      const key = pickKey(item.kind, item.id);
      if (next.has(key)) next.delete(key);
      else next.set(key, item);
      return next;
    });

  const register = async () => {
    const rows = [...picked.values()];
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      const added = await addHistoryKnowers({
        knower_id: characterId,
        character_history_ids: rows.filter((row) => row.kind === "character").map((row) => row.id),
        idea_history_ids: rows.filter((row) => row.kind === "idea").map((row) => row.id),
        start: since,
      });
      setDone(T.knowledge.registered(added.character_history_ids.length + added.idea_history_ids.length));
      setPicked(new Map());
      if (selected) await loadHistories(selected);
    } catch (e) {
      setError(T.knowledge.failed(e instanceof Error ? e.message : String(e)));
    } finally {
      setBusy(false);
    }
  };

  const hit = matcher(filter);
  const locations = tree ? filterLocations(tree.locations, hit) : [];
  const unplaced = tree ? tree.unplaced.filter((c) => hit(c.name, c.id)) : [];
  const ideas = tree ? filterIdeas(tree.ideas, hit) : [];
  const knows = (knowers: Rec[]) => knowers.some((knower) => knower.knower_id === characterId);

  const row = (item: Picked, knowers: Rec[], heading: ReactNode, body: string | null) => {
    const known = knows(knowers);
    const on = picked.has(pickKey(item.kind, item.id));
    return (
      <li
        key={pickKey(item.kind, item.id)}
        className={`knowledge-row ${on ? "on" : ""} ${known ? "known" : ""}`}
        onClick={() => !known && toggle(item)}
      >
        <div className="knowledge-row-head">
          {heading}
          {known && <span className="chip">{T.knowledge.known}</span>}
        </div>
        {body && <div className="knowledge-row-body">{body}</div>}
        <KnowerNames knowers={knowers} />
      </li>
    );
  };

  return (
    <Modal
      title={T.knowledge.title(characterName)}
      onClose={onClose}
      wide
      actions={
        <>
          <span className="meta">{T.knowledge.picked(picked.size)}</span>
          <label className="knowledge-since" title={T.knowledge.since}>
            <span className="hint">{T.knowledge.since}</span>
            <StampInput value={since} onChange={setSince} disabled={busy} />
          </label>
          <span className="spacer" />
          {error && <span className="status error">{error}</span>}
          {done && !error && <span className="status ok">{done}</span>}
          <button type="button" onClick={onClose}>
            {T.close}
          </button>
          <button type="button" className="primary" onClick={() => void register()} disabled={busy || picked.size === 0}>
            {T.knowledge.register}
          </button>
        </>
      }
    >
      <div className="knowledge">
        <div className="knowledge-sources">
          <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder={T.knowledge.filter} />
          <div className="knowledge-tree">
            {!tree ? (
              !error && <div className="status info">{T.loading}</div>
            ) : (
              <>
                <h3>{T.knowledge.characters}</h3>
                {locations.length === 0 && unplaced.length === 0 ? (
                  <div className="hint">{T.knowledge.noMatch}</div>
                ) : (
                  <ul className="tree">
                    {locations.map((node) => (
                      <LocationBranch key={node.id} node={node} selected={selected} onSelect={select} />
                    ))}
                    {unplaced.length > 0 && (
                      <li>
                        <details open>
                          <summary className="knowledge-branch">{T.characterTree.noLocation}</summary>
                          <ul className="tree">
                            {unplaced.map((character) => (
                              <CharacterItem key={character.id} character={character} selected={selected} onSelect={select} />
                            ))}
                          </ul>
                        </details>
                      </li>
                    )}
                  </ul>
                )}
                <h3>{T.knowledge.ideas}</h3>
                {ideas.length === 0 ? (
                  <div className="hint">{T.knowledge.noMatch}</div>
                ) : (
                  <ul className="tree">
                    {ideas.map((node) => (
                      <IdeaItem key={node.id} node={node} selected={selected} onSelect={select} />
                    ))}
                  </ul>
                )}
              </>
            )}
          </div>
        </div>
        <div className="knowledge-histories">
          {!selected ? (
            <div className="hint">{T.knowledge.pickSource}</div>
          ) : (
            <>
              <h3>
                <NameId name={selected.name} id={selected.id} />
              </h3>
              {!histories ? (
                <div className="status info">{T.loading}</div>
              ) : histories.character_histories.length + histories.idea_histories.length === 0 ? (
                <div className="hint">{T.knowledge.noHistories}</div>
              ) : (
                <ul className="knowledge-rows">
                  {histories.character_histories.map((history) =>
                    row(
                      { kind: "character", id: history.id, owner: selected, text: history.description },
                      history.knowers,
                      <span>{history.start === null ? T.knowledge.undated : T.knowledge.year(history.start)}</span>,
                      history.description,
                    ),
                  )}
                  {histories.idea_histories.map((history) =>
                    row(
                      { kind: "idea", id: history.id, owner: selected, text: history.name },
                      history.knowers,
                      <>
                        <strong>{history.name}</strong>
                        <span className="hint">
                          {history.location_id === null
                            ? T.knowledge.anywhere
                            : T.nameId(locationLabels.get(history.location_id), history.location_id)}
                          {(history.start || history.end) && ` ${T.span(history.start?.split(" ")[0], history.end?.split(" ")[0])}`}
                        </span>
                      </>,
                      history.detail,
                    ),
                  )}
                </ul>
              )}
            </>
          )}
        </div>
      </div>
      {picked.size > 0 && (
        <div className="knowledge-picked">
          {[...picked.entries()].map(([key, item]) => (
            <span key={key} className="knower-chip">
              <NameId name={item.owner.name} id={item.owner.id} />
              <span className="knowledge-picked-text">{item.text}</span>
              <button type="button" className="ghost" onClick={() => toggle(item)} title={T.knowledge.unpick}>
                ×
              </button>
            </span>
          ))}
        </div>
      )}
    </Modal>
  );
}
