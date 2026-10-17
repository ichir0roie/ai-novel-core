"use client";

import { useEffect, useRef, useSyncExternalStore } from "react";

// 走っている保存の数。0 より大きい間は SavingOverlay が画面を覆う
let count = 0;
const listeners = new Set<() => void>();

function set(next: number) {
  count = next;
  listeners.forEach((listener) => listener());
}

/** 保存の約束を渡すと、決着するまで画面をロックしてぐるぐるを出す。渡した約束をそのまま返す。 */
export function trackSaving<T>(promise: Promise<T>): Promise<T> {
  set(count + 1);
  return promise.finally(() => set(count - 1));
}

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => void listeners.delete(listener);
};

/** 保存が一つでも走っていれば true。 */
export const useSaving = () => useSyncExternalStore(subscribe, () => count > 0, () => false);

// Ctrl+S を受ける保存の重なり順。モーダルはページの上に開くので、一番上(最後に付けたもの)だけが受ける
const handlers: { current: () => void }[] = [];

if (typeof window !== "undefined") {
  window.addEventListener(
    "keydown",
    (e) => {
      // 覆いはクリックしか止めないので、フォーカスの残った欄へ打ち込むのもここで止める。
      // 保存の返りで欄を置き換える画面があり、保存中に打った字が消えるため
      if (count > 0) {
        e.preventDefault();
        e.stopPropagation();
        return;
      }
      if (!((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "s")) return;
      // 保存の無い画面でも、ブラウザのページ保存は出さない
      e.preventDefault();
      if (!e.repeat) handlers[handlers.length - 1]?.current();
    },
    { capture: true },
  );
}

const nothing = () => {};

/** 付けている間、Ctrl+S(Mac は ⌘S)で onSave を呼ぶ。enabled が false の間は何もしない(下の重なりにも渡さない)。 */
export function useSaveShortcut(onSave: () => void, enabled = true) {
  // onSave は描画ごとに作り直されるので、重なり順を崩さないよう付け外しはせず中身だけ差し替える
  const handler = useRef(nothing);
  useEffect(() => {
    handler.current = enabled ? onSave : nothing;
  });
  useEffect(() => {
    handlers.push(handler);
    return () => void handlers.splice(handlers.indexOf(handler), 1);
  }, []);
}
