import type { Rec } from "./api";

/** アイデア一覧のツリー。`parent_idea_id` で木にする(場所と違い relationship は無いので、素の列だけで組む)。 */

export type IdeaNode = {
  id: number;
  name: string | null;
  kind: string | null;
  confirmed: string | null;
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

  const node = (idea: Rec): IdeaNode => {
    const id = Number(idea.id);
    return {
      id,
      name: str(idea.name),
      kind: str(idea.kind),
      confirmed: str(idea.confirmed),
      children: (childrenOf.get(id) ?? []).map(node),
    };
  };
  return (childrenOf.get(null) ?? []).map(node);
}

/** id の子孫(自分自身は含まない)の id 集合。ドラッグ&ドロップで循環になる相手をあらかじめ弾くのに使う。 */
export function descendantIds(nodes: IdeaNode[], id: number): Set<number> {
  const find = (list: IdeaNode[]): IdeaNode | null => {
    for (const n of list) {
      if (n.id === id) return n;
      const found = find(n.children);
      if (found) return found;
    }
    return null;
  };
  const result = new Set<number>();
  const collect = (n: IdeaNode) => {
    for (const child of n.children) {
      result.add(child.id);
      collect(child);
    }
  };
  const target = find(nodes);
  if (target) collect(target);
  return result;
}
