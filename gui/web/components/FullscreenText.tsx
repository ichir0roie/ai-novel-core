"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useSaveShortcut } from "@/lib/saving";
import { T } from "@/lib/text";

type Props = {
  title: string;
  value: string;
  onChange: (value: string) => void;
  /** 変更は画面に残したまま閉じる */
  onBack: () => void;
  /** 閉じて保存する */
  onSave: () => void;
};

/** スマホで本文の欄を画面全体に広げて読み書きする。左上に欄の名前、右上に戻る・保存のアイコン。
 * 入力中(キーボードが開いている間)は、その一行を隠して全部を文に使う。 */
export default function FullscreenText({ title, value, onChange, onBack, onSave }: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const [typing, setTyping] = useState(false);
  // キーボードが開くと見えている高さ(visualViewport)だけが縮み、fixed の 100dvh のままでは下がキーボードに隠れる
  const [view, setView] = useState<{ top: number; height: number } | null>(null);
  useSaveShortcut(onSave);

  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) return;
    let last = viewport.height;
    const update = () => {
      // Android は戻るでキーボードを閉じてもフォーカスが残るので、見えている高さが戻ったら入力を終える
      if (viewport.height - last > 120 && document.activeElement === ref.current) ref.current?.blur();
      last = viewport.height;
      setView({ top: viewport.offsetTop, height: viewport.height });
    };
    update();
    viewport.addEventListener("resize", update);
    viewport.addEventListener("scroll", update);
    return () => {
      viewport.removeEventListener("resize", update);
      viewport.removeEventListener("scroll", update);
    };
  }, []);

  return createPortal(
    <div className="fullscreen-text" style={view ? { top: view.top, height: view.height } : undefined}>
      {!typing && (
        <div className="fullscreen-text-head">
          <h2>{title}</h2>
          <button type="button" className="ghost icon" onClick={onBack} aria-label={T.record.back} title={T.record.back}>
            <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
              <path d="M10 6l-6 6 6 6M4 12h16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
          <button type="button" className="ghost icon" onClick={onSave} aria-label={T.record.saveAndClose} title={T.record.saveAndClose}>
            <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
              <path d="M5 12.5l4.5 4.5L19 7" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>
      )}
      <textarea
        ref={ref}
        value={value}
        placeholder={T.record.emptyText}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => setTyping(true)}
        onBlur={() => setTyping(false)}
      />
    </div>,
    document.body,
  );
}
