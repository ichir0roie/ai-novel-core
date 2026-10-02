import type { Rec } from "./api";

/** アイデア一覧のツリー。`parent_idea_id` で木にする(場所と違い relationship は無いので、素の列だけで組む)。 */

export type IdeaNode = {
  id: number;
  name: string | null;
  children: IdeaNode[];
};

const num = (v: unknown): number | null => (typeof v === "number" ? v : null);
const str = (v: unknown): string | null => (v == null ? null : String(v));

export function buildIdeaTree(ideas: Rec[]): IdeaNode[] {
  const known = new Set(ideas.map((i) => Number(i.id)));
  const childrenOf = new Map<number | null, Rec[]>();
  for (const idea of [...ideas].sort((a, b) => Number(a.id) - Number(b.id))) {
    const parent = num(idea.parent_idea_id);
    const key = parent !== null && known.has(parent) ? parent : null;
    childrenOf.set(key, [...(childrenOf.get(key) ?? []), idea]);
  }

  const node = (idea: Rec): IdeaNode => ({
    id: Number(idea.id),
    name: str(idea.name),
    children: (childrenOf.get(Number(idea.id)) ?? []).map(node),
  });
  return (childrenOf.get(null) ?? []).map(node);
}

/** id のノードを木から探す。 */
export function findNode(nodes: IdeaNode[], id: number): IdeaNode | null {
  for (const n of nodes) {
    if (n.id === id) return n;
    const found = findNode(n.children, id);
    if (found) return found;
  }
  return null;
}

/** id の子孫(自分自身は含まない)の id 集合。移動モードで、循環になる移動先をあらかじめ弾くのに使う。 */
export function descendantIds(nodes: IdeaNode[], id: number): Set<number> {
  const result = new Set<number>();
  const collect = (n: IdeaNode) => {
    for (const child of n.children) {
      result.add(child.id);
      collect(child);
    }
  };
  const target = findNode(nodes, id);
  if (target) collect(target);
  return result;
}

/** 子を持つノード(caret を出す・開閉できるノード)の id をすべて集める。「すべて閉じる」で使う。 */
export function collapsibleIds(nodes: IdeaNode[]): string[] {
  const result: string[] = [];
  const collect = (n: IdeaNode) => {
    if (n.children.length > 0) {
      result.push(String(n.id));
      n.children.forEach(collect);
    }
  };
  nodes.forEach(collect);
  return result;
}
