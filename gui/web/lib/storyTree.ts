import type { Rec } from "./api";

/** 作品一覧のツリー。作品を `parent_story_id` で木にする。親が見つからない作品は根に置く。 */

export type StoryNode = {
  id: number;
  name: string;
  state: string | null;
  start: string | null;
  end: string | null;
  // 話(episode)の数
  episodes: number;
  children: StoryNode[];
};

const num = (v: unknown): number | null => (typeof v === "number" ? v : null);
const str = (v: unknown): string | null => (v == null ? null : String(v));

// 立つ年の順(空は後ろ)。同じなら id 順
function byStart(a: Rec, b: Rec): number {
  const sa = str(a.start), sb = str(b.start);
  if (sa === sb) return Number(a.id) - Number(b.id);
  if (sa === null) return 1;
  if (sb === null) return -1;
  return sa < sb ? -1 : 1;
}

export function buildStoryTree(stories: Rec[], episodes: Rec[]): StoryNode[] {
  const known = new Set(stories.map((s) => Number(s.id)));
  const childrenOf = new Map<number | null, Rec[]>();
  for (const story of [...stories].sort(byStart)) {
    const parent = num(story.parent_story_id);
    const key = parent !== null && known.has(parent) ? parent : null;
    childrenOf.set(key, [...(childrenOf.get(key) ?? []), story]);
  }

  const episodeCount = new Map<number, number>();
  for (const episode of episodes) {
    const storyId = num(episode.story_id);
    if (storyId !== null) episodeCount.set(storyId, (episodeCount.get(storyId) ?? 0) + 1);
  }

  const node = (story: Rec): StoryNode => {
    const id = Number(story.id);
    return {
      id, name: String(story.name ?? story.label ?? ""), state: str(story.state),
      start: str(story.start), end: str(story.end), episodes: episodeCount.get(id) ?? 0,
      children: (childrenOf.get(id) ?? []).map(node),
    };
  };
  return (childrenOf.get(null) ?? []).map(node);
}

/** id の子孫(自分自身は含まない)の id 集合。ドラッグ中、循環になる落とし先を弾くのに使う。 */
export function descendantIds(nodes: StoryNode[], id: number): Set<number> {
  const result = new Set<number>();
  const collect = (n: StoryNode) => {
    for (const child of n.children) {
      result.add(child.id);
      collect(child);
    }
  };
  const find = (list: StoryNode[]): StoryNode | null => {
    for (const n of list) {
      if (n.id === id) return n;
      const found = find(n.children);
      if (found) return found;
    }
    return null;
  };
  const target = find(nodes);
  if (target) collect(target);
  return result;
}
