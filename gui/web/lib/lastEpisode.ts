import { useEffect, type Dispatch, type SetStateAction } from "react";
import { getLastEpisode, type Rec } from "./api";

/** 話を新しく足すとき、作品(`story_id`)が決まったら、その作品の最後の話の場所・視点・登場人物を写す。
 * 空の欄だけを埋めるので、先に入れた値やクエリで渡した値は変えない。 */
export function useCopyFromLastEpisode(storyId: unknown, setValue: Dispatch<SetStateAction<Rec | null>>, enabled: boolean) {
  const story = typeof storyId === "number" ? storyId : null;
  useEffect(() => {
    if (!enabled || story === null) return;
    getLastEpisode(story)
      .then((last) => {
        if (!last) return;
        setValue((current) => current && {
          ...current,
          location_id: current.location_id ?? last.location_id ?? null,
          viewpoint_character_id: current.viewpoint_character_id ?? last.viewpoint_character_id ?? null,
          character_ids: Array.isArray(current.character_ids) && current.character_ids.length > 0
            ? current.character_ids : last.character_ids,
        });
      })
      .catch(() => undefined);
  }, [enabled, story, setValue]);
}
