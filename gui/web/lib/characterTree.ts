import type { Rec } from "./api";

/** 人物一覧のツリー。場所(location)を `parent_id` で木にし、人物は今いる場所(`/api/character_locations` が
 *  返す、一番新しく設定された居場所。時刻で絞ればその時刻の居場所)の下に置く。居場所を一つも持たない人物は `unplaced` に出す。
 *  `focusLocationId` を渡すと、その場所の配下と、その場所までの上位の場所(そこに住む人物だけ)に絞る。
 *  居場所は国・地方のように広めに持つことがあるので、上位の場所にいる人物もその場所にいるとみなす
 *  (`data_access_logic/character/location_characters.py` と同じ)。 */

export type TreeCharacter = {
  id: number;
  name: string;
  kind: string | null;
};

export type TreeNode = {
  id: number;
  name: string | null;
  kind: string | null;
  characters: TreeCharacter[];
  children: TreeNode[];
  // 子孫まで含めた人数
  total: number;
};

export type CharacterTree = { nodes: TreeNode[]; unplaced: TreeCharacter[] };

const num = (v: unknown): number | null => (typeof v === "number" ? v : null);
const str = (v: unknown): string | null => (v == null ? null : String(v));

export function buildCharacterTree(
  locations: Rec[],
  characters: Rec[],
  characterLocations: Record<string, number>,
  focusLocationId: number | null = null,
): CharacterTree {
  const known = new Set(locations.map((l) => Number(l.id)));
  const parentOf = new Map(locations.map((l) => [Number(l.id), num(l.parent_id)]));
  // 絞り込みの場所から最上位までの道筋。辿った先が環になっていても止まる
  const path = new Set<number>();
  for (let at = focusLocationId; at !== null && known.has(at) && !path.has(at); at = parentOf.get(at) ?? null) path.add(at);
  const children = new Map<number | null, Rec[]>();
  for (const location of [...locations].sort((a, b) => Number(a.id) - Number(b.id))) {
    const parent = num(location.parent_id);
    const key = parent !== null && known.has(parent) ? parent : null;
    children.set(key, [...(children.get(key) ?? []), location]);
  }

  const charactersAt = new Map<number, TreeCharacter[]>();
  const unplaced: TreeCharacter[] = [];
  for (const character of [...characters].sort((a, b) => String(a.name ?? "").localeCompare(String(b.name ?? ""), "ja"))) {
    const id = Number(character.id);
    const entry: TreeCharacter = {
      id, name: String(character.name ?? character.label ?? ""),
      kind: str(character.kind),
    };
    const at = characterLocations[String(id)];
    if (at === undefined || !known.has(at)) unplaced.push(entry);
    else charactersAt.set(at, [...(charactersAt.get(at) ?? []), entry]);
  }

  // inside: 絞り込みの場所かその配下にいる(配下はすべて出す)。外なら道筋の上の子だけを辿る
  const node = (location: Rec, inside: boolean): TreeNode | null => {
    const id = Number(location.id);
    const within = inside || id === focusLocationId;
    const subtree = (children.get(id) ?? [])
      .filter((child) => within || path.has(Number(child.id)))
      .map((child) => node(child, within))
      .filter((n): n is TreeNode => n !== null);
    const own = charactersAt.get(id) ?? [];
    if (subtree.length === 0 && own.length === 0) return null;
    return {
      id, name: str(location.name), kind: str(location.kind), characters: own, children: subtree,
      total: own.length + subtree.reduce((sum, child) => sum + child.total, 0),
    };
  };
  const all = focusLocationId === null;
  const roots = (children.get(null) ?? []).filter((root) => all || path.has(Number(root.id)));
  return { nodes: roots.map((root) => node(root, all)).filter((n): n is TreeNode => n !== null), unplaced: all ? unplaced : [] };
}

/** 開閉できるノード(場所)の id をすべて集める。「すべて閉じる」で使う。 */
export function collapsibleIds(tree: CharacterTree): string[] {
  const result: string[] = [];
  const collect = (node: TreeNode) => {
    result.push(String(node.id));
    node.children.forEach(collect);
  };
  tree.nodes.forEach(collect);
  return result;
}
