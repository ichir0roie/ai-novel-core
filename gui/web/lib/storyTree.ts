import type { Rec } from "./api";

/** 作品一覧のツリー。場所(location)を `parent_id` で木にし、作品は `place_id`(無ければ `world_id`)の場所の下に置く。
 *  作品を一つも含まない枝は落とし、どちらも無い作品は `unplaced` に出す。 */

export type TreeStory = {
  id: number;
  name: string;
  state: string | null;
  start: string | null;
  end: string | null;
  // 話(episode)の数
  episodes: number;
};

export type TreeNode = {
  id: number;
  name: string | null;
  kind: string | null;
  stories: TreeStory[];
  children: TreeNode[];
  // 子孫まで含めた作品の数
  total: number;
};

export type StoryTree = { nodes: TreeNode[]; unplaced: TreeStory[] };

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

export function buildStoryTree(locations: Rec[], stories: Rec[], episodes: Rec[]): StoryTree {
  const known = new Set(locations.map((l) => Number(l.id)));
  const children = new Map<number | null, Rec[]>();
  for (const place of [...locations].sort((a, b) => Number(a.id) - Number(b.id))) {
    const parent = num(place.parent_id);
    const key = parent !== null && known.has(parent) ? parent : null;
    children.set(key, [...(children.get(key) ?? []), place]);
  }

  const episodeCount = new Map<number, number>();
  for (const episode of episodes) {
    const storyId = num(episode.story_id);
    if (storyId !== null) episodeCount.set(storyId, (episodeCount.get(storyId) ?? 0) + 1);
  }

  const storiesAt = new Map<number, TreeStory[]>();
  const unplaced: TreeStory[] = [];
  for (const story of [...stories].sort(byStart)) {
    const id = Number(story.id);
    const entry: TreeStory = {
      id, name: String(story.name ?? story.label ?? ""), state: str(story.state),
      start: str(story.start), end: str(story.end), episodes: episodeCount.get(id) ?? 0,
    };
    const place = num(story.place_id), world = num(story.world_id);
    const at = place !== null && known.has(place) ? place : world !== null && known.has(world) ? world : null;
    if (at === null) unplaced.push(entry);
    else storiesAt.set(at, [...(storiesAt.get(at) ?? []), entry]);
  }

  const node = (place: Rec): TreeNode | null => {
    const id = Number(place.id);
    const subtree = (children.get(id) ?? []).map(node).filter((n): n is TreeNode => n !== null);
    const own = storiesAt.get(id) ?? [];
    if (subtree.length === 0 && own.length === 0) return null;
    return {
      id, name: str(place.name), kind: str(place.kind), stories: own, children: subtree,
      total: own.length + subtree.reduce((sum, child) => sum + child.total, 0),
    };
  };
  return { nodes: (children.get(null) ?? []).map(node).filter((n): n is TreeNode => n !== null), unplaced };
}
