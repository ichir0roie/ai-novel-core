import { useEffect, useState } from "react";
import { getStoryCharacters } from "./api";

// 話の行と一緒に受けた値(`related.story_character_ids`)。話のページを開き直すまで引き直さない
const received = new Map<number, number[]>();

export function receiveStoryCharacterIds(storyId: unknown, ids: number[]) {
  if (typeof storyId === "number") received.set(storyId, ids);
}

/** 作品(`story_id`。一番上の作品とその章・外伝をまとめる)の話・出来事に出てくる人物の id。出てくる回数の多い順。
 * 話の人物の候補に使う。`enabled` が偽のとき、作品が空か読めないときは null(絞らない)。 */
export function useStoryCharacterIds(storyId: unknown, enabled: boolean): number[] | null {
  const [ids, setIds] = useState<number[] | null>(null);
  const story = typeof storyId === "number" ? storyId : null;
  useEffect(() => {
    setIds(null);
    if (!enabled || story === null) return;
    const known = received.get(story);
    if (known) {
      setIds(known);
      return;
    }
    let alive = true;
    getStoryCharacters(story)
      .then((r) => alive && setIds(r.character_ids))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [enabled, story]);
  return ids;
}
