"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

type Props = {
  title: string;
  onClose: () => void;
  children: ReactNode;
  actions?: ReactNode;
  // 画面の大部分を使う、幅の広いモーダル(データ表など)
  wide?: boolean;
  // 中身の幅に合わせて縮む、小さなモーダル(日時ピッカーなど)。wide と同時には使わない
  compact?: boolean;
};

// 開いているモーダルの重なり順。選択のモーダルは別のモーダルの中からも開くので、Escape は一番上のものだけを閉じる
const stack: symbol[] = [];

/** 中央に浮かぶ汎用モーダル。背景クリックか Escape で閉じる。
 * 親の枠(表の行・別のモーダル)に切られないよう body の直下へ描く。 */
export default function Modal({ title, onClose, children, actions, wide, compact }: Props) {
  const close = useRef(onClose);
  useEffect(() => {
    close.current = onClose;
  });

  useEffect(() => {
    const id = Symbol();
    stack.push(id);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && stack[stack.length - 1] === id) close.current();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      stack.splice(stack.indexOf(id), 1);
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  return createPortal(
    // portal の中のクリックも React の木では親へ伝わるので、背景・中身のどちらでも止める
    <div
      className="modal-backdrop"
      onClick={(e) => {
        e.stopPropagation();
        onClose();
      }}
    >
      <div className={`modal ${wide ? "wide" : ""} ${compact ? "compact" : ""}`} onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>{title}</h2>
          <button type="button" className="ghost" onClick={onClose}>
            ×
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {actions && <div className="modal-actions">{actions}</div>}
      </div>
    </div>,
    document.body,
  );
}
