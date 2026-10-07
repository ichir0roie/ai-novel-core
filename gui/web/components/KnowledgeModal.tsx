"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  getCharacterLocations,
  listAllRecords,
  readKnowableRows,
  readKnownRows,
  updateKnowledge,
  type KnowableRows,
  type KnowledgeChange,
  type KnownRows,
  type Rec,
} from "@/lib/api";
import { buildCharacterTree, type TreeCharacter, type TreeNode } from "@/lib/characterTree";
import { buildIdeaTree, type IdeaNode } from "@/lib/ideaTree";
import { T } from "@/lib/text";
import Modal from "./Modal";
import NameId from "./NameId";
import { useOptions } from "./ReferenceSelect";
import StampInput from "./StampInput";

type Source = { kind: "character" | "idea" | "location"; id: number; name: string | null };

/** 知る相手を付け外しする行(人物の来歴・スキルの来歴・アイデアの履歴・場所の来歴)。行の id で指す */
type RowKind = "character" | "skill" | "idea" | "place";

/** 場所の来歴を選ぶ木。場所を `parent_id` で木にする */
type PlaceNode = { id: number; name: string | null; children: PlaceNode[] };

function buildPlaceTree(locations: Rec[]): PlaceNode[] {
  const known = new Set(locations.map((l) => Number(l.id)));
  const childrenOf = new Map<number | null, Rec[]>();
  for (const location of [...locations].sort((a, b) => Number(a.id) - Number(b.id))) {
    const parent = typeof location.parent_id === "number" && known.has(location.parent_id) ? location.parent_id : null;
    childrenOf.set(parent, [...(childrenOf.get(parent) ?? []), location]);
  }
  const node = (location: Rec): PlaceNode => ({
    id: Number(location.id),
    name: location.name == null ? null : String(location.name),
    children: (childrenOf.get(Number(location.id)) ?? []).map(node),
  });
  return (childrenOf.get(null) ?? []).map(node);
}

/** 人物の今の居場所と、そこから最上位までの場所(住んでいるので、場所を知る相手にした行を知っている)。 */
function homeChain(locations: Rec[], homeId: number | undefined): Set<number> {
  const parentOf = new Map(locations.map((l) => [Number(l.id), typeof l.parent_id === "number" ? l.parent_id : null]));
  const chain = new Set<number>();
  for (let id: number | null | undefined = homeId; id != null && !chain.has(id); id = parentOf.get(id)) chain.add(id);
  return chain;
}

type RowState = { known: boolean; start: string | null };

/** 保存前の付け外し。人物・アイデアを移っても残る */
type Change = RowState & { kind: RowKind; id: number; owner: Source; label: string };

const rowKey = (kind: RowKind, id: number) => `${kind}:${id}`;
const sourceKey = (source: Pick<Source, "kind" | "id">) => `${source.kind}:${source.id}`;
const sameState = (a: RowState, b: RowState) => a.known === b.known && (a.start ?? null) === (b.start ?? null);

/** 名前の一部か id(先頭の # は無くてよい)で当てる。 */
function matcher(filter: string): (name: string | null, id: number) => boolean {
  const q = filter.trim().toLowerCase();
  if (q === "") return () => true;
  const asId = q.replace(/^#/, "");
  return (name, id) => String(id) === asId || (name ?? "").toLowerCase().includes(q);
}

type Keep = (kind: Source["kind"], name: string | null, id: number) => boolean;

/** 残す人物のいる場所だけを残す。 */
function filterLocations(nodes: TreeNode[], keep: Keep): TreeNode[] {
  return nodes.flatMap((node) => {
    const characters = node.characters.filter((c) => keep("character", c.name, c.id));
    const children = filterLocations(node.children, keep);
    if (characters.length === 0 && children.length === 0) return [];
    return [{ ...node, characters, children }];
  });
}

/** 残す場所と、その祖先を残す。 */
function filterPlaces(nodes: PlaceNode[], keep: Keep): PlaceNode[] {
  return nodes.flatMap((node) => {
    const children = filterPlaces(node.children, keep);
    if (keep("location", node.name, node.id) || children.length > 0) return [{ ...node, children }];
    return [];
  });
}

/** 残すアイデアと、その祖先を残す。 */
function filterIdeas(nodes: IdeaNode[], keep: Keep): IdeaNode[] {
  return nodes.flatMap((node) => {
    const children = filterIdeas(node.children, keep);
    if (keep("idea", node.name, node.id) || children.length > 0) return [{ ...node, children }];
    return [];
  });
}

/** 保存した知る行に付け外しを重ね、人物・アイデアごとに知る行の数を数える。 */
function knownCounts(saved: KnownRows | null, changes: Map<string, Change>): Map<string, number> {
  const owners = new Map<string, string>();
  if (saved) {
    saved.character_histories.forEach((row) => owners.set(rowKey("character", row.id), sourceKey({ kind: "character", id: row.character_id })));
    saved.character_skill_histories.forEach((row) => owners.set(rowKey("skill", row.id), sourceKey({ kind: "character", id: row.character_id })));
    saved.idea_histories.forEach((row) => owners.set(rowKey("idea", row.id), sourceKey({ kind: "idea", id: row.idea_id })));
    saved.location_histories.forEach((row) => owners.set(rowKey("place", row.id), sourceKey({ kind: "location", id: row.location_id })));
  }
  for (const [key, change] of changes) {
    if (change.known) owners.set(key, sourceKey(change.owner));
    else owners.delete(key);
  }
  const counts = new Map<string, number>();
  for (const owner of owners.values()) counts.set(owner, (counts.get(owner) ?? 0) + 1);
  return counts;
}

type TreeProps = { selected: Source | null; counts: Map<string, number>; onSelect: (source: Source) => void };

function SourceLabel({ source, counts, selfId }: { source: Source; counts: Map<string, number>; selfId?: number }) {
  const count = counts.get(sourceKey(source)) ?? 0;
  return (
    <>
      <NameId name={source.name} id={source.id} />
      {source.id === selfId && source.kind === "character" && <span className="hint"> {T.knowledge.self}</span>}
      {count > 0 && <span className="knowledge-count">{T.knowledge.knownCount(count)}</span>}
    </>
  );
}

function CharacterItem({ character, selected, counts, onSelect, selfId }: TreeProps & { character: TreeCharacter; selfId: number }) {
  const source: Source = { kind: "character", id: character.id, name: character.name };
  const on = selected?.kind === "character" && selected.id === character.id;
  return (
    <li className={`knowledge-item ${on ? "on" : ""}`} onClick={() => onSelect(source)}>
      <SourceLabel source={source} counts={counts} selfId={selfId} />
    </li>
  );
}

function LocationBranch({ node, ...props }: TreeProps & { node: TreeNode; selfId: number }) {
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

function IdeaItem({ node, selected, counts, onSelect }: TreeProps & { node: IdeaNode }) {
  const source: Source = { kind: "idea", id: node.id, name: node.name };
  const on = selected?.kind === "idea" && selected.id === node.id;
  const item = (
    <span
      className={`knowledge-item ${on ? "on" : ""}`}
      onClick={(e) => {
        // 見出しの中で押しても枝を開閉しない(開閉は印で行う)
        e.preventDefault();
        onSelect(source);
      }}
    >
      <SourceLabel source={source} counts={counts} />
    </span>
  );
  if (node.children.length === 0) return <li>{item}</li>;
  return (
    <li>
      <details open>
        <summary className="knowledge-branch">{item}</summary>
        <ul className="tree">
          {node.children.map((child) => (
            <IdeaItem key={child.id} node={child} selected={selected} counts={counts} onSelect={onSelect} />
          ))}
        </ul>
      </details>
    </li>
  );
}

/** 子孫まで含めて、この人物が知る行のある場所か。 */
function hasKnown(node: PlaceNode, counts: Map<string, number>): boolean {
  return (counts.get(sourceKey({ kind: "location", id: node.id })) ?? 0) > 0 || node.children.some((child) => hasKnown(child, counts));
}

type PlaceProps = TreeProps & { depth: number; expand: boolean; home: Set<number>; homeId: number | undefined };

/** 場所の木の一つの枝。場所は数が多いので、開いておくのは一番上と、絞り込み中・知る行のある枝・今住んでいる場所までの枝だけにする。 */
function PlaceItem({ node, ...props }: PlaceProps & { node: PlaceNode }) {
  const { depth, expand, home, homeId, selected, counts, onSelect } = props;
  const source: Source = { kind: "location", id: node.id, name: node.name };
  const on = selected?.kind === "location" && selected.id === node.id;
  const item = (
    <span
      className={`knowledge-item ${on ? "on" : ""}`}
      onClick={(e) => {
        // 見出しの中で押しても枝を開閉しない(開閉は印で行う)
        e.preventDefault();
        onSelect(source);
      }}
    >
      <SourceLabel source={source} counts={counts} />
      {node.id === homeId && <span className="hint"> {T.knowledge.home}</span>}
    </span>
  );
  if (node.children.length === 0) return <li>{item}</li>;
  const open = expand || depth === 0 || node.children.some((child) => home.has(child.id) || hasKnown(child, counts));
  return (
    <li>
      <details open={open}>
        <summary className="knowledge-branch">{item}</summary>
        <ul className="tree">
          {node.children.map((child) => (
            <PlaceItem key={child.id} node={child} {...props} depth={depth + 1} />
          ))}
        </ul>
      </details>
    </li>
  );
}

/** 行の知る相手を名前で並べる(読むだけ。保存した値)。 */
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

type Props = { characterId: number; characterName: string; onClose: () => void; onSaved: () => void };

/** 知識整理。この人物が、人物の来歴・スキルの来歴・アイデアの履歴・場所の来歴の行を知るかを、まとめて付け外しする。
 * 左の人物・アイデア・場所の木(この人物が知る行の数つき)から一つ選ぶと、右にその行が並ぶ。行を押すと知る/知らないが
 * 切り替わり、知る行には知った時刻を入れられる。付け外しは人物・アイデアを移っても残り、保存で一度に直す。
 * 場所として知る相手に入っている行(その場所に住むので知る)は、ここでは付け外ししない。 */
export default function KnowledgeModal({ characterId, characterName, onClose, onSaved }: Props) {
  const [tree, setTree] = useState<{
    locations: TreeNode[]; unplaced: TreeCharacter[]; ideas: IdeaNode[]; places: PlaceNode[];
    home: Set<number>; homeId: number | undefined;
  } | null>(null);
  const [saved, setSaved] = useState<KnownRows | null>(null);
  const [filter, setFilter] = useState("");
  const [onlyKnown, setOnlyKnown] = useState(false);
  const [selected, setSelected] = useState<Source | null>(null);
  const [rows, setRows] = useState<KnowableRows | null>(null);
  const [changes, setChanges] = useState<Map<string, Change>>(new Map());
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
      readKnownRows(characterId),
    ])
      .then(([locations, characters, characterLocations, ideas, known]) => {
        if (cancelled) return;
        const characterTree = buildCharacterTree(locations, characters, characterLocations.locations);
        setTree({
          locations: characterTree.nodes, unplaced: characterTree.unplaced, ideas: buildIdeaTree(ideas),
          places: buildPlaceTree(locations), home: homeChain(locations, characterLocations.locations[String(characterId)]),
          homeId: characterLocations.locations[String(characterId)],
        });
        setSaved(known);
      })
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      cancelled = true;
    };
  }, [characterId]);

  const loadRows = useCallback(async (source: Source) => {
    setRows(null);
    try {
      setRows(await readKnowableRows(
        source.kind === "character" ? { character_id: source.id } : source.kind === "idea" ? { idea_id: source.id } : { location_id: source.id },
      ));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  const select = (source: Source) => {
    setSelected(source);
    void loadRows(source);
  };

  /** 保存した値(この人物が人物として知る相手に入っているか、知った時刻) */
  const savedState = (knowers: Rec[]): RowState => {
    const own = knowers.find((knower) => knower.knower_id === characterId);
    return own ? { known: true, start: (own.start as string | null) ?? null } : { known: false, start: null };
  };

  const setState = (row: Omit<Change, "known" | "start">, original: RowState, next: RowState) =>
    setChanges((prev) => {
      const copy = new Map(prev);
      const key = rowKey(row.kind, row.id);
      if (sameState(original, next)) copy.delete(key);
      else copy.set(key, { ...row, ...next });
      return copy;
    });

  const save = async () => {
    const list = [...changes.values()];
    const of = (kind: RowKind): KnowledgeChange[] =>
      list.filter((change) => change.kind === kind).map(({ id, known, start }) => ({ id, known, start: known ? start : null }));
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      const known = await updateKnowledge({
        knower_id: characterId, character_histories: of("character"), character_skill_histories: of("skill"),
        idea_histories: of("idea"), location_histories: of("place"),
      });
      setSaved(known);
      setDone(T.knowledge.saved(list.length));
      setChanges(new Map());
      if (selected) await loadRows(selected);
      onSaved();
    } catch (e) {
      setError(T.knowledge.failed(e instanceof Error ? e.message : String(e)));
    } finally {
      setBusy(false);
    }
  };

  const close = () => {
    if (changes.size === 0 || window.confirm(T.knowledge.confirmDiscard(changes.size))) onClose();
  };

  const counts = knownCounts(saved, changes);
  const hit = matcher(filter);
  const keep: Keep = (kind, name, id) => hit(name, id) && (!onlyKnown || (counts.get(sourceKey({ kind, id })) ?? 0) > 0);
  const locations = tree ? filterLocations(tree.locations, keep) : [];
  const unplaced = tree ? tree.unplaced.filter((c) => keep("character", c.name, c.id)) : [];
  const ideas = tree ? filterIdeas(tree.ideas, keep) : [];
  const places = tree ? filterPlaces(tree.places, keep) : [];
  const filtering = filter.trim() !== "" || onlyKnown;
  const treeProps = { selected, counts, onSelect: select };

  /** 住んでいるので、場所を知る相手にした行をすでに知っているか。その場所の名前(知らなければ null) */
  const livesIn = (knowers: Rec[]): string | null => {
    const place = knowers.find((knower) => typeof knower.location_id === "number" && tree?.home.has(knower.location_id));
    return place ? T.nameId(locationLabels.get(place.location_id as number), place.location_id as number) : null;
  };

  const row = (kind: RowKind, id: number, knowers: Rec[], label: string, heading: ReactNode, body: string | null) => {
    if (!selected) return null;
    const original = savedState(knowers);
    const change = changes.get(rowKey(kind, id));
    const state: RowState = change ?? original;
    const base = { kind, id, owner: selected, label };
    const lives = kind === "place" ? livesIn(knowers) : null;
    return (
      <li
        key={rowKey(kind, id)}
        className={`knowledge-row ${state.known ? "known" : ""} ${!state.known && lives ? "via-place" : ""} ${change ? "changed" : ""}`}
        onClick={() => setState(base, original, state.known ? { known: false, start: null } : { known: true, start: original.known ? original.start : since })}
      >
        <div className="knowledge-row-head">
          <span className="knowledge-check" aria-hidden>
            {state.known || lives ? "✓" : ""}
          </span>
          {heading}
          {change && <span className="chip on">{!original.known ? T.knowledge.adding : !state.known ? T.knowledge.removing : T.knowledge.retiming}</span>}
          {lives && <span className="chip">{T.knowledge.livesHere(lives)}</span>}
        </div>
        {body && <div className="knowledge-row-body">{body}</div>}
        {state.known && (
          <div className="knowledge-row-since" onClick={(e) => e.stopPropagation()}>
            <span className="hint">{T.knowledge.knownSince}</span>
            <StampInput value={state.start} onChange={(start) => setState(base, original, { known: true, start })} disabled={busy} />
          </div>
        )}
        <KnowerNames knowers={knowers} />
      </li>
    );
  };

  return (
    <Modal
      title={T.knowledge.title(characterName)}
      onClose={close}
      wide
      actions={
        <>
          <span className="meta">{T.knowledge.changes(changes.size)}</span>
          <label className="knowledge-since" title={T.knowledge.defaultSince}>
            <span className="hint">{T.knowledge.defaultSince}</span>
            <StampInput value={since} onChange={setSince} disabled={busy} />
          </label>
          <span className="spacer" />
          {error && <span className="status error">{error}</span>}
          {done && !error && <span className="status ok">{done}</span>}
          <button type="button" onClick={() => setChanges(new Map())} disabled={busy || changes.size === 0}>
            {T.record.revert}
          </button>
          <button type="button" onClick={close}>
            {T.close}
          </button>
          <button type="button" className="primary" onClick={() => void save()} disabled={busy || changes.size === 0}>
            {T.record.save}
          </button>
        </>
      }
    >
      <div className="knowledge">
        <div className="knowledge-sources">
          <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder={T.knowledge.filter} />
          <label className="knowledge-only-known">
            <input type="checkbox" checked={onlyKnown} onChange={(e) => setOnlyKnown(e.target.checked)} />
            {T.knowledge.onlyKnown}
          </label>
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
                      <LocationBranch key={node.id} node={node} selfId={characterId} {...treeProps} />
                    ))}
                    {unplaced.length > 0 && (
                      <li>
                        <details open>
                          <summary className="knowledge-branch">{T.characterTree.noLocation}</summary>
                          <ul className="tree">
                            {unplaced.map((character) => (
                              <CharacterItem key={character.id} character={character} selfId={characterId} {...treeProps} />
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
                      <IdeaItem key={node.id} node={node} {...treeProps} />
                    ))}
                  </ul>
                )}
                <h3>{T.knowledge.places}</h3>
                {places.length === 0 ? (
                  <div className="hint">{T.knowledge.noMatch}</div>
                ) : (
                  <ul className="tree">
                    {places.map((node) => (
                      <PlaceItem key={node.id} node={node} depth={0} expand={filtering} home={tree.home} homeId={tree.homeId} {...treeProps} />
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
              {selected.kind === "location" && <p className="hint knowledge-place-hint">{T.knowledge.placeHint}</p>}
              {!rows ? (
                <div className="status info">{T.loading}</div>
              ) : (
                <ul className="knowledge-rows">
                  {rows.character_histories.map((history) =>
                    row(
                      "character",
                      history.id,
                      history.knowers,
                      history.description,
                      <span>{history.start === null ? T.knowledge.undated : T.knowledge.date(history.start)}</span>,
                      history.description,
                    ),
                  )}
                  {rows.character_skills.flatMap((skill) =>
                    skill.histories.map((history) =>
                      row(
                        "skill",
                        history.id,
                        history.knowers,
                        `${skill.name}: ${history.description}`,
                        <>
                          <strong>{T.knowledge.skill(skill.name)}</strong>
                          <span>{history.start === null ? T.knowledge.undated : T.knowledge.date(history.start)}</span>
                        </>,
                        history.description,
                      ),
                    ),
                  )}
                  {rows.idea_histories.map((history) =>
                    row(
                      "idea",
                      history.id,
                      history.knowers,
                      history.name,
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
                  {rows.location_histories.map((history) =>
                    row(
                      "place",
                      history.id,
                      history.knowers,
                      history.description,
                      <span>{history.start === null ? T.knowledge.undated : T.knowledge.date(history.start)}</span>,
                      history.description,
                    ),
                  )}
                  {rows.character_histories.length === 0 && rows.character_skills.length === 0 && rows.idea_histories.length === 0 &&
                    rows.location_histories.length === 0 && (
                    <li className="hint">{T.knowledge.noHistories}</li>
                  )}
                </ul>
              )}
            </>
          )}
        </div>
      </div>
      {changes.size > 0 && (
        <div className="knowledge-picked">
          {[...changes.entries()].map(([key, change]) => (
            <span key={key} className={`knower-chip ${change.known ? "" : "removing"}`}>
              <span>{change.known ? (saved && isSaved(saved, change) ? "⏱" : "+") : "−"}</span>
              <NameId name={change.owner.name} id={change.owner.id} />
              <span className="knowledge-picked-text">{change.label}</span>
              <button
                type="button"
                className="ghost"
                onClick={() =>
                  setChanges((prev) => {
                    const copy = new Map(prev);
                    copy.delete(key);
                    return copy;
                  })
                }
                title={T.knowledge.undo}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
    </Modal>
  );
}

/** 付け外しの行が、保存した値ですでに知る行か(知った時刻だけを直す行)。 */
function isSaved(saved: KnownRows, change: Change): boolean {
  if (change.kind === "character") return saved.character_histories.some((row) => row.id === change.id);
  if (change.kind === "skill") return saved.character_skill_histories.some((row) => row.id === change.id);
  if (change.kind === "idea") return saved.idea_histories.some((row) => row.id === change.id);
  return saved.location_histories.some((row) => row.id === change.id);
}
