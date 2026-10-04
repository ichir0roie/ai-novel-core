"use client";

import { useEffect, useState, type ReactNode } from "react";

type Shown = { text: string; left: number; top?: number; bottom?: number } | null;

const GAP = 6;
// `.tip` の max-width と余白
const TIP_WIDTH = 380;

/** 列・子の一覧の名前。かざすと仕様を出す(仕様があると分かるよう点線の下線を引く)。 */
export function Spec({ hint, children }: { hint: string; children: ReactNode }) {
  return (
    <span className="spec" data-hint={hint}>
      {children}
    </span>
  );
}

/** `data-hint` を持つ要素にかざすと、その文言を要素の下(画面の下の方なら上)に吹き出しで出す。layout に一つだけ置く。
 * 要素ごとに状態を持たせず一か所で拾うので、表・札・モーダルのどこに置いた名前でも同じに出る。 */
export default function HintLayer() {
  const [shown, setShown] = useState<Shown>(null);

  useEffect(() => {
    let current: Element | null = null;
    const clear = () => {
      current = null;
      setShown(null);
    };
    const over = (e: PointerEvent) => {
      const target = e.target instanceof Element ? e.target.closest("[data-hint]") : null;
      if (target === current) return;
      current = target;
      const text = target?.getAttribute("data-hint");
      if (!target || !text) {
        setShown(null);
        return;
      }
      const rect = target.getBoundingClientRect();
      const left = Math.max(GAP, Math.min(rect.left, window.innerWidth - TIP_WIDTH));
      setShown(rect.bottom > window.innerHeight * 0.7
        ? { text, left, bottom: window.innerHeight - rect.top + GAP }
        : { text, left, top: rect.bottom + GAP });
    };
    const out = (e: PointerEvent) => {
      if (!e.relatedTarget) clear();
    };
    document.addEventListener("pointerover", over);
    document.addEventListener("pointerout", out);
    document.addEventListener("pointerdown", clear);
    document.addEventListener("scroll", clear, true);
    return () => {
      document.removeEventListener("pointerover", over);
      document.removeEventListener("pointerout", out);
      document.removeEventListener("pointerdown", clear);
      document.removeEventListener("scroll", clear, true);
    };
  }, []);

  if (!shown) return null;
  return (
    <div className="tip" style={{ left: shown.left, top: shown.top, bottom: shown.bottom }}>
      {shown.text}
    </div>
  );
}
