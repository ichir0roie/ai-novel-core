"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { getCharacterLocations, listAllRecords, type Rec } from "@/lib/api";
import { buildCharacterTree, collapsibleIds, type TreeCharacter, type TreeNode } from "@/lib/characterTree";
import { T } from "@/lib/text";
import { useTreeOpen } from "@/lib/treeOpen";

type OpenState = ReturnType<typeof useTreeOpen>;

function CharacterRow({ character }: { character: TreeCharacter }) {
  return (
    <li className="tree-story">
      <Link href={`/tables/character/${character.id}`}>{character.name}</Link>
      <span className="tree-meta">
        {character.kind && character.kind !== "人物" && <span className="chip">{character.kind}</span>}
        {character.confirmed && character.confirmed !== "承認" && <span className="chip">{character.confirmed}</span>}
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
          <span className="tree-name">{node.name ?? `(id ${node.id})`}</span>
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
 *  (居場所は期間ごとに複数あるので、話のようなドラッグ&ドロップでの付け替えは持たない)。タブに戻ったら引き直す。 */
export default function CharacterTree() {
  const [source, setSource] = useState<Source | null>(null);
  const [error, setError] = useState<string | null>(null);
  const openState = useTreeOpen("character");

  const load = useCallback(async () => {
    try {
      const [locations, characters, characterLocations] = await Promise.all([
        listAllRecords("location", { sort: "id", order: "asc" }),
        listAllRecords("character", { sort: "id", order: "asc" }),
        getCharacterLocations(),
      ]);
      setSource({ locations, characters, characterLocations: characterLocations.locations });
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void load();
    window.addEventListener("focus", load);
    return () => window.removeEventListener("focus", load);
  }, [load]);

  if (error) return <div className="status error">{error}</div>;
  if (!source) return <div className="status info">{T.loading}</div>;

  const tree = buildCharacterTree(source.locations, source.characters, source.characterLocations);
  if (tree.nodes.length === 0 && tree.unplaced.length === 0) return <div className="status info">{T.characterTree.noCharacters}</div>;

  return (
    <div className="panel">
      <button type="button" className="tree-root-drop" onClick={() => openState.closeAll([...collapsibleIds(tree), UNPLACED])}>
        {T.characterTree.collapseAll}
      </button>
      <ul className="tree tree-root">
        {tree.nodes.map((node) => (
          <LocationNode key={node.id} node={node} openState={openState} />
        ))}
        <li className="tree-location">
          <details open={openState.isOpen(UNPLACED)} onToggle={(e) => openState.setOpen(UNPLACED, e.currentTarget.open)}>
            <summary>
              <span className="tree-name">{T.characterTree.noLocation}</span>
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
      </ul>
    </div>
  );
}
