import type { RouteStop } from "@/lib/api";

/** 同じ場所に続けて立つ話をまとめた一回の立ち寄り。`n` は作品の中の順(1 から)。 */
export type Visit = {
  n: number;
  placedId: number | null;
  planetId: number | null;
  lon: number | null;
  lat: number | null;
  stops: RouteStop[];
};

export const ROUTE_COLOR = "#7d3c98";

export function routeVisits(stops: RouteStop[]): Visit[] {
  const visits: Visit[] = [];
  for (const stop of stops) {
    const last = visits[visits.length - 1];
    if (last && last.placedId === stop.placed_id) last.stops.push(stop);
    else visits.push({ n: visits.length + 1, placedId: stop.placed_id, planetId: stop.planet_id, lon: stop.lon, lat: stop.lat, stops: [stop] });
  }
  return visits;
}

/** 地図に置ける立ち寄りを順につなぐ。間に置けない立ち寄りを挟んだら `gap`(点線で描く)。 */
export function routeLegs(visits: Visit[]): { from: Visit; to: Visit; gap: boolean }[] {
  const placed = visits.filter((v) => v.lon != null && v.lat != null);
  return placed.slice(1).map((to, i) => ({ from: placed[i], to, gap: to.n - placed[i].n > 1 }));
}

/** 二点を少し曲げて結ぶ。行きと帰りが逆の側に膨らむので重ならない。両端は `r1` `r2` だけ手前で止める。 */
export function legPath(x1: number, y1: number, x2: number, y2: number, r1: number, r2: number): string {
  const dx = x2 - x1, dy = y2 - y1;
  const len = Math.hypot(dx, dy) || 1;
  const bend = Math.min(40, len * 0.15);
  const cx = (x1 + x2) / 2 - (dy / len) * bend, cy = (y1 + y2) / 2 + (dx / len) * bend;
  const toward = (x: number, y: number, r: number) => {
    const d = Math.hypot(cx - x, cy - y) || 1;
    return [x + ((cx - x) / d) * r, y + ((cy - y) / d) * r];
  };
  const [sx, sy] = toward(x1, y1, r1);
  const [ex, ey] = toward(x2, y2, r2);
  return `M${sx},${sy} Q${cx},${cy} ${ex},${ey}`;
}

/** 印の上に立てる番号の札の文字。多ければ先頭だけ出す。 */
export const badgeText = (ns: number[]) => (ns.length > 4 ? `${ns.slice(0, 3).join(",")},…` : ns.join(","));
