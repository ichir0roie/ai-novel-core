"use client";

import { useEffect, type ReactNode } from "react";

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

/** 中央に浮かぶ汎用モーダル。背景クリックか Escape で閉じる。 */
export default function Modal({ title, onClose, children, actions, wide, compact }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onClick={onClose}>
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
    </div>
  );
}
