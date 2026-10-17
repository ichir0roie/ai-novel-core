import { useEffect, useState } from "react";
import { getLocationCharacters } from "./api";

// 話の行と一緒に受けた値(`related.location_character_ids`)。同じ場所・時刻なら引き直さない
const received = new Map<string, number[]>();

export function receiveLocationCharacterIds(locationId: unknown, start: unknown, ids: number[]) {
  if (typeof locationId === "number" && typeof start === "string") received.set(`${locationId} ${start}`, ids);
}

/** フォームの場所(`location_id`)か、その上位の場所に時刻(`start`)にいる人物の id。話の人物の候補を絞るのに使う。
 * `enabled` が偽のとき、場所・時刻が空か読めないときは null(絞らない)。 */
export function useLocationCharacterIds(locationId: unknown, start: unknown, enabled: boolean): number[] | null {
  const [ids, setIds] = useState<number[] | null>(null);
  const location = typeof locationId === "number" ? locationId : null;
  const time = typeof start === "string" && start.trim() ? start : null;
  useEffect(() => {
    setIds(null);
    if (!enabled || location === null || time === null) return;
    const known = received.get(`${location} ${time}`);
    if (known) {
      setIds(known);
      return;
    }
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
