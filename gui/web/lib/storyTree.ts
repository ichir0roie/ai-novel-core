import type { Rec } from "./api";
import { parseStamp, stampOrder } from "./stamp";

/** 作品一覧のツリー。作品を `parent_story_id` で木にする。親が見つからない作品は根に置く。
 *  兄弟は `display_order` の順。`display_order` の空の作品は後ろに、一番早い話の順(話の無い作品はさらに後ろ)、同じなら id 順。 */

export type StoryNode = {
  id: number;
  name: string;
  displayOrder: number | null;
  // 話(episode)の数
  episodes: number;
  children: StoryNode[];
};

const num = (v: unknown): number | null => (typeof v === "number" ? v : null);

export function buildStoryTree(stories: Rec[], episodes: Rec[]): StoryNode[] {
  const known = new Set(stories.map((s) => Number(s.id)));
  const parentOf = (story: Rec): number | null => {
    const parent = num(story.parent_story_id);
    return parent !== null && known.has(parent) ? parent : null;
  };

  const episodeCount = new Map<number, number>();
  // 作品とその子孫の作品の話のうち、一番早い時刻
  const firstAt = new Map<number, number>();
  const byId = new Map(stories.map((s) => [Number(s.id), s]));
  for (const episode of episodes) {
    const storyId = num(episode.story_id);
    if (storyId === null) continue;
    episodeCount.set(storyId, (episodeCount.get(storyId) ?? 0) + 1);
    if (!parseStamp(episode.start)) continue;
    const at = stampOrder(episode.start);
    // 親をたどる作品が循環していても止まる
    const seen = new Set<number>();
    for (let id: number | null = storyId; id !== null && !seen.has(id); id = byId.has(id) ? parentOf(byId.get(id)!) : null) {
      seen.add(id);
      if (at < (firstAt.get(id) ?? Infinity)) firstAt.set(id, at);
    }
  }

  const orderOf = (story: Rec) => num(story.display_order) ?? Infinity;
  const firstOf = (story: Rec) => firstAt.get(Number(story.id)) ?? Infinity;
  const compare = (a: Rec, b: Rec) =>
    orderOf(a) - orderOf(b) || firstOf(a) - firstOf(b) || Number(a.id) - Number(b.id);
  const childrenOf = new Map<number | null, Rec[]>();
  for (const story of [...stories].sort(compare)) {
    const key = parentOf(story);
    childrenOf.set(key, [...(childrenOf.get(key) ?? []), story]);
  }

  const node = (story: Rec): StoryNode => {
    const id = Number(story.id);
    return {
      id, name: String(story.name ?? story.label ?? ""), displayOrder: num(story.display_order), episodes: episodeCount.get(id) ?? 0,
      children: (childrenOf.get(id) ?? []).map(node),
    };
  };
  return (childrenOf.get(null) ?? []).map(node);
}

/** id のノードを木から探す。 */
export function findNode(nodes: StoryNode[], id: number): StoryNode | null {
  for (const n of nodes) {
    if (n.id === id) return n;
    const found = findNode(n.children, id);
    if (found) return found;
  }
  return null;
}

/** id の子孫(自分自身は含まない)の id 集合。付け替えの間、循環になる親の候補を弾くのに使う。 */
export function descendantIds(nodes: StoryNode[], id: number): Set<number> {
  const result = new Set<number>();
  const collect = (n: StoryNode) => {
    for (const child of n.children) {
      result.add(child.id);
      collect(child);
    }
  };
  const target = findNode(nodes, id);
  if (target) collect(target);
  return result;
}

/** 子を持つ(開閉できる)作品の id をすべて集める。「すべて閉じる」で使う。 */
export function collapsibleIds(nodes: StoryNode[]): string[] {
  const result: string[] = [];
  const collect = (n: StoryNode) => {
    if (n.children.length > 0) {
      result.push(String(n.id));
      n.children.forEach(collect);
    }
  };
  nodes.forEach(collect);
  return result;
}
