import { useEffect, useState } from "react";
import { getPlaceCharacters } from "./api";

/** フォームの場所(`place_id`)に時刻(`start`)にいる人物の id。話の人物の候補を絞るのに使う。
 * `enabled` が偽のとき、場所・時刻が空か読めないときは null(絞らない)。 */
export function usePlaceCharacterIds(placeId: unknown, start: unknown, enabled: boolean): number[] | null {
  const [ids, setIds] = useState<number[] | null>(null);
  const place = typeof placeId === "number" ? placeId : null;
  const time = typeof start === "string" && start.trim() ? start : null;
  useEffect(() => {
    setIds(null);
    if (!enabled || place === null || time === null) return;
    let alive = true;
    getPlaceCharacters(place, time)
      .then((r) => alive && setIds(r.character_ids))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [enabled, place, time]);
  return ids;
}
