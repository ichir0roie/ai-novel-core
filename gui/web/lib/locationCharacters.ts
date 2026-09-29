import { useEffect, useState } from "react";
import { getLocationCharacters } from "./api";

/** フォームの場所(`location_id`)に時刻(`start`)にいる人物の id。話の人物の候補を絞るのに使う。
 * `enabled` が偽のとき、場所・時刻が空か読めないときは null(絞らない)。 */
export function useLocationCharacterIds(locationId: unknown, start: unknown, enabled: boolean): number[] | null {
  const [ids, setIds] = useState<number[] | null>(null);
  const location = typeof locationId === "number" ? locationId : null;
  const time = typeof start === "string" && start.trim() ? start : null;
  useEffect(() => {
    setIds(null);
    if (!enabled || location === null || time === null) return;
    let alive = true;
    getLocationCharacters(location, time)
      .then((r) => alive && setIds(r.character_ids))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [enabled, location, time]);
  return ids;
}
