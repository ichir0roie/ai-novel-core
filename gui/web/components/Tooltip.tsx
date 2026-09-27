"use client";

import { useState, type MouseEvent } from "react";

export type Tip = { x: number; y: number; lines: string[] } | null;

/** 図の上でマウスに追いかける吹き出し。`show(e, lines)` を onMouseMove に、`hide` を onMouseLeave に渡す。 */
export function useTooltip() {
  const [tip, setTip] = useState<Tip>(null);
  const show = (e: MouseEvent, lines: (string | null | undefined | false)[]) =>
    setTip({ x: e.clientX + 14, y: e.clientY + 14, lines: lines.filter((l): l is string => Boolean(l)) });
  const hide = () => setTip(null);
  return { tip, show, hide };
}

export default function Tooltip({ tip }: { tip: Tip }) {
  if (!tip) return null;
  return (
    <div className="tip" style={{ left: tip.x, top: tip.y }}>
      {tip.lines.join("\n")}
    </div>
  );
}
