import { useEffect, useRef, type Dispatch, type SetStateAction } from "react";
import { getPreviousEpisode, type Rec } from "./api";

const COPIED_KEYS = ["location_id", "viewpoint_character_id", "character_ids"] as const;

function isEmpty(v: unknown): boolean {
  return v == null || (Array.isArray(v) && v.length === 0);
}

/** 話を新しく足すとき、作品(`story_id`)が決まったら、同じ作品で開始(`start`)より前の一番後ろの話
 * (開始が空なら作品の最後の話)の場所・視点・登場人物を写す。
 * 埋めるのは空の欄と、前に写したまま手で直していない欄だけなので、入れた値やクエリで渡した値は変えない。 */
export function useCopyFromPreviousEpisode(
  storyId: unknown, start: unknown, setValue: Dispatch<SetStateAction<Rec | null>>, enabled: boolean,
) {
  const story = typeof storyId === "number" ? storyId : null;
  const before = typeof start === "string" && start !== "" ? start : null;
  // 作品・開始を変えたとき、前に写した値だけを差し替えるために覚えておく
  const copied = useRef<Rec>({});
  useEffect(() => {
    if (!enabled || story === null) return;
    let cancelled = false;
    getPreviousEpisode(story, before)
      .then((previous) => {
        if (cancelled || !previous) return;
        const source: Rec = previous;
        setValue((current) => {
          if (!current) return current;
          const next: Rec = { ...current };
          const nextCopied: Rec = {};
          for (const key of COPIED_KEYS) {
            const untouched = key in copied.current
              && JSON.stringify(current[key] ?? null) === JSON.stringify(copied.current[key] ?? null);
            if (isEmpty(current[key]) || untouched) {
              next[key] = source[key] ?? null;
              nextCopied[key] = next[key];
            }
          }
          copied.current = nextCopied;
          return next;
        });
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [enabled, story, before, setValue]);
}
