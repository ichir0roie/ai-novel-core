"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { getCharacterLocations, listAllRecords, type Rec } from "@/lib/api";
import NameId from "./NameId";
import StampInput from "./StampInput";
import TreeReferenceSelect from "./TreeReferenceSelect";
import { buildCharacterTree, collapsibleIds, type TreeCharacter, type TreeNode } from "@/lib/characterTree";
import { T } from "@/lib/text";
import { FULL_STAMP } from "@/lib/timelineAxis";
import { useTreeOpen } from "@/lib/treeOpen";

type OpenState = ReturnType<typeof useTreeOpen>;

function CharacterRow({ character }: { character: TreeCharacter }) {
  return (
    <li className="tree-story">
      <Link href={`/tables/character/${character.id}`}>
        <NameId name={character.name} id={character.id} />
      </Link>
      <span className="tree-meta">
        {character.kind && character.kind !== "人物" && <span className="chip">{character.kind}</span>}
      </span>
    </li>
  );
}

function LocationNode({ node, openState }: { node: TreeNode; openState: OpenState }) {
  const key = String(node.id);
  return (
    <li className="tree-location">
      <details open={openState.isOpen(key)} onToggle={(e) => openState.setOpen(key, e.currentTarget.open)}>
        <summary>
          <span className="tree-name">
            <NameId name={node.name} id={node.id} />
          </span>
          {node.kind && <span className="tree-kind">{node.kind}</span>}
          <span className="tree-count">{T.characterTree.characters(node.total)}</span>
          <Link href={`/tables/location/${node.id}`} className="tree-link" onClick={(e) => e.stopPropagation()}>
            {T.characterTree.openLocation}
          </Link>
        </summary>
        <ul className="tree">
          {node.characters.map((character) => (
            <CharacterRow key={character.id} character={character} />
          ))}
          {node.children.map((child) => (
            <LocationNode key={child.id} node={child} openState={openState} />
          ))}
        </ul>
      </details>
    </li>
  );
}

const UNPLACED = "unplaced";

type Source = { locations: Rec[]; characters: Rec[]; characterLocations: Record<string, number> };

/** 人物一覧のツリー。場所・人物の一覧と、人物ごとの居場所をそのまま引いて、木はブラウザで組む。読み取り専用
 *  (居場所は期間ごとに複数あるので、作品ツリーのような親の付け替えは持たない)。タブに戻ったら引き直す。
 *  場所(`?location_id=`)と時刻(`?at=`)で、その時刻にその場所にいる人物に絞れる。 */
export default function CharacterTree() {
  const router = useRouter();
  const search = useSearchParams();
  const locationId = Number(search.get("location_id")) || null;
  const at = search.get("at");
  const [draft, setDraft] = useState<string | null>(at);
  const [source, setSource] = useState<Source | null>(null);
  const [error, setError] = useState<string | null>(null);
  const openState = useTreeOpen("character");

  useEffect(() => setDraft(at), [at]);

  const setFilter = (key: "location_id" | "at", value: string | null) => {
    const p = new URLSearchParams(search.toString());
    if (value === null || value === "") p.delete(key);
    else p.set(key, value);
    router.replace(`/tables/character?${p.toString()}`);
  };

  const load = useCallback(async () => {
    try {
      const [locations, characters, characterLocations] = await Promise.all([
        listAllRecords("location", { sort: "id", order: "asc" }),
        listAllRecords("character", { sort: "id", order: "asc" }),
        getCharacterLocations(at),
      ]);
      setSource({ locations, characters, characterLocations: characterLocations.locations });
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [at]);

  useEffect(() => {
    void load();
    window.addEventListener("focus", load);
    return () => window.removeEventListener("focus", load);
  }, [load]);

  const filters = (
    <div className="toolbar">
      <div className="hint timeline-filter">
        {T.characterTree.location}
        <TreeReferenceSelect
          table="location"
          value={locationId}
          nullable
          onChange={(value) => setFilter("location_id", value === null ? null : String(value))}
          title={T.characterTree.location}
        />
      </div>
      <form
        className="hint timeline-filter"
        onSubmit={(e) => {
          e.preventDefault();
          setFilter("at", draft);
        }}
      >
        {T.characterTree.at}
        <StampInput
          value={draft}
          onChange={(value) => {
            setDraft(value);
            if (value === null || FULL_STAMP.test(value)) setFilter("at", value);
          }}
        />
      </form>
    </div>
  );

  if (error) return <>{filters}<div className="status error">{error}</div></>;
  if (!source) return <>{filters}<div className="status info">{T.loading}</div></>;

  const tree = buildCharacterTree(source.locations, source.characters, source.characterLocations, locationId);
  if (tree.nodes.length === 0 && tree.unplaced.length === 0) {
    const filtered = locationId !== null || at !== null;
    return <>{filters}<div className="status info">{filtered ? T.characterTree.noMatch : T.characterTree.noCharacters}</div></>;
  }

  return (
    <>
      {filters}
      <div className="panel">
        <button type="button" className="tree-root-drop" onClick={() => openState.closeAll([...collapsibleIds(tree), UNPLACED])}>
          {T.characterTree.collapseAll}
        </button>
        <ul className="tree tree-root">
          {tree.nodes.map((node) => (
            <LocationNode key={node.id} node={node} openState={openState} />
          ))}
          {/* 場所で絞ったときは、居場所の無い人物はその場所にいないので出さない */}
          {locationId === null && (
            <li className="tree-location">
              <details open={openState.isOpen(UNPLACED)} onToggle={(e) => openState.setOpen(UNPLACED, e.currentTarget.open)}>
                <summary>
                  <span className="tree-name">{at !== null ? T.characterTree.noLocationAt : T.characterTree.noLocation}</span>
                  <span className="tree-count">{T.characterTree.characters(tree.unplaced.length)}</span>
                </summary>
                {tree.unplaced.length > 0 && (
                  <ul className="tree">
                    {tree.unplaced.map((character) => (
                      <CharacterRow key={character.id} character={character} />
                    ))}
                  </ul>
                )}
              </details>
            </li>
          )}
        </ul>
      </div>
    </>
  );
}
