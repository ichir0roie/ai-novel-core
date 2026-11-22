/** 地図の点の印。区分ごとに形を変える(python の `data_access_logic/map/render_svg.py` の `marker` と同じ形)。 */
export default function MapMarker({ category, x, y, r, color, strokeWidth = 1 }: { category: string; x: number; y: number; r: number; color: string; strokeWidth?: number }) {
  const common = { fill: color, stroke: "#fff", strokeWidth };
  if (category === "国") return <circle cx={x} cy={y} r={r} {...common} />;
  if (category === "都市") return <rect x={x - r} y={y - r} width={2 * r} height={2 * r} {...common} />;
  if (category === "自然") return <path d={`M${x},${y - r * 1.2} L${x + r * 1.1},${y + r * 0.8} L${x - r * 1.1},${y + r * 0.8} Z`} {...common} />;
  return <path d={`M${x},${y - r} L${x + r},${y} L${x},${y + r} L${x - r},${y} Z`} {...common} />;
}
