import { T } from "@/lib/text";
/** 地図の座標の決め方と距離・方角。python 側(`data_access_logic/map/layout.py` `data_access_logic/map/geometry.py`)と同じ決め方にする。 */

export type Polygon = { coordinates: number[][][] };
export type LonLat = { lon: number; lat: number };

const ML = 60;
const MT = 40;
const PAD = 10;
const GRID = 10;
const MIN_SCALE = 6;
const TARGET_WIDTH = 1400;

export type Frame = {
  lonMin: number;
  lonMax: number;
  latMin: number;
  latMax: number;
  scale: number;
  step: number;
  x: (lon: number) => number;
  y: (lat: number) => number;
};

/** 輪郭の外側の環。最後の点が最初と同じなら落とす。 */
export function outerRing(polygon: Polygon): number[][] {
  const ring = polygon.coordinates[0] ?? [];
  const closed = ring.length > 1 && ring[0][0] === ring[ring.length - 1][0] && ring[0][1] === ring[ring.length - 1][1];
  return closed ? ring.slice(0, -1) : ring;
}

export function polygonCenter(polygon: Polygon): [number, number] {
  const ring = outerRing(polygon);
  return [ring.reduce((a, q) => a + q[0], 0) / ring.length, ring.reduce((a, q) => a + q[1], 0) / ring.length];
}

/** 全部が収まる枠。`center` を渡すと、その点が真ん中に来るように枠を左右・上下に広げる。 */
export function fitFrame(points: LonLat[], shapes: { polygon: Polygon }[], zoom: number, center?: LonLat | null): Frame {
  const fl = (v: number, s: number) => Math.floor(v / s) * s;
  const ce = (v: number, s: number) => -fl(-v, s);
  const lons = points.map((p) => p.lon);
  const lats = points.map((p) => p.lat);
  for (const sh of shapes) for (const [lon, lat] of outerRing(sh.polygon)) { lons.push(lon); lats.push(lat); }
  let box = lons.length
    ? {
        lonMin: Math.max(-180, fl(Math.min(...lons) - PAD, GRID)),
        lonMax: Math.min(180, ce(Math.max(...lons) + PAD, GRID)),
        latMin: Math.max(-90, fl(Math.min(...lats) - PAD, GRID)),
        latMax: Math.min(90, ce(Math.max(...lats) + PAD, GRID)),
      }
    : { lonMin: -180, lonMax: 180, latMin: -90, latMax: 90 };
  if (center) {
    const halfLon = Math.max(center.lon - box.lonMin, box.lonMax - center.lon, GRID);
    const halfLat = Math.max(center.lat - box.latMin, box.latMax - center.lat, GRID);
    box = {
      lonMin: Math.max(-180, fl(center.lon - halfLon, GRID)),
      lonMax: Math.min(180, ce(center.lon + halfLon, GRID)),
      latMin: Math.max(-90, fl(center.lat - halfLat, GRID)),
      latMax: Math.min(90, ce(center.lat + halfLat, GRID)),
    };
  }
  const scale = (lons.length ? Math.max(MIN_SCALE, TARGET_WIDTH / (box.lonMax - box.lonMin)) : MIN_SCALE / 2) * zoom;
  const span = Math.max(box.lonMax - box.lonMin, box.latMax - box.latMin);
  return {
    ...box,
    scale,
    step: span > 180 ? 30 : span > 60 ? 10 : 5,
    x: (lon) => ML + (lon - box.lonMin) * scale,
    y: (lat) => MT + (box.latMax - lat) * scale,
  };
}

export const MARGIN = { left: ML, top: MT, right: 20, bottom: 30 };

export const textWidth = (text: string, px = 11) => [...text].reduce((w, ch) => w + ((ch.codePointAt(0) ?? 0) > 0x2e7f ? px : px * 0.55), 0);

type Anchor = "start" | "end" | "middle";
const CANDIDATES: [Anchor, number, number][] = [
  ["start", 8, 4], ["end", -8, 4], ["middle", 0, -9], ["middle", 0, 15],
  ["start", 8, -8], ["start", 8, 16], ["end", -8, -8], ["end", -8, 16],
];
type Box = [number, number, number, number];
const overlaps = (a: Box, b: Box) => !(a[2] <= b[0] || b[2] <= a[0] || a[3] <= b[1] || b[3] <= a[1]);

/** 印のそばで他のラベルと重ならない位置を選ぶ。同じ点に重なる印は呼ぶ側で y をずらして渡す。 */
export function locationLabels(items: [number, number, string][], px = 11): [number, number, Anchor][] {
  const placed: Box[] = [];
  return items.map(([x, y, text]) => {
    const w = textWidth(text, px);
    const h = px + 2;
    for (const [anchor, dx, dy] of CANDIDATES) {
      const lx = x + dx - (anchor === "end" ? w : anchor === "middle" ? w / 2 : 0);
      const box: Box = [lx, y + dy - h, lx + w, y + dy];
      if (!placed.some((o) => overlaps(box, o))) {
        placed.push(box);
        return [x + dx, y + dy, anchor];
      }
    }
    placed.push([x + 8, y + 4 - h, x + 8 + w, y + 4]);
    return [x + 8, y + 4, "start"];
  });
}

const rad = (d: number) => (d * Math.PI) / 180;

/** 二点の角距離(度)。 */
export function angular(a: LonLat, b: LonLat): number {
  const p1 = rad(a.lat), p2 = rad(b.lat), dl = rad(b.lon - a.lon);
  const h = Math.sin((p2 - p1) / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return (2 * Math.asin(Math.min(1, Math.sqrt(h))) * 180) / Math.PI;
}

export function bearing(a: LonLat, b: LonLat): number {
  const p1 = rad(a.lat), p2 = rad(b.lat), dl = rad(b.lon - a.lon);
  const x = Math.sin(dl) * Math.cos(p2);
  const y = Math.cos(p1) * Math.sin(p2) - Math.sin(p1) * Math.cos(p2) * Math.cos(dl);
  return ((Math.atan2(x, y) * 180) / Math.PI + 360) % 360;
}

export const distanceKm = (radiusKm: number | null | undefined, deg: number) => (radiusKm == null ? null : rad(deg) * radiusKm);
export const bearingName = (bearings: string[], d: number) => bearings[Math.floor((d + 11.25) / 22.5) % 16];

export function distanceText(km: number | null, deg: number): string {
  if (km == null) return T.maps.aboutDegrees(deg);
  return T.maps.aboutKm(km < 100 ? Math.round(km) : Math.round(km / 10) * 10);
}
export const altText = (alt: number | null | undefined) => (alt == null ? "" : ` (${alt >= 0 ? "+" : ""}${Math.round(alt).toLocaleString()} m)`);
export function altDiffText(d: number | null): string {
  if (d == null) return T.maps.altDiffUnknown;
  if (Math.abs(d) < 1) return T.maps.sameAltitude;
  return T.maps.altDiff(d > 0, Math.round(Math.abs(d)));
}
