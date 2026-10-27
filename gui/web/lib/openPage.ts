import { useRouter } from "next/navigation";
import { useCallback } from "react";

/** クリック・キー入力の修飾キー(MouseEvent・KeyboardEvent のどちらも満たす) */
export type OpenModifiers = { ctrlKey: boolean; metaKey: boolean };

/** Ctrl(Mac は ⌘)を押しながらの操作か。押していれば、リンクと同じく別タブで開く */
export function inNewTab(e?: OpenModifiers | null): boolean {
  return !!e && (e.ctrlKey || e.metaKey);
}

export function openInNewTab(href: string) {
  window.open(href, "_blank", "noopener");
}

/** 画面を移る関数を返す。Ctrl(⌘)を押しながらなら別タブで開き、この画面はそのまま残す */
export function useOpenPage() {
  const router = useRouter();
  return useCallback(
    (href: string, e?: OpenModifiers | null) => {
      if (inNewTab(e)) openInNewTab(href);
      else router.push(href);
    },
    [router],
  );
}
