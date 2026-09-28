import { useCallback, useEffect, useState } from "react";

/** ツリーの開閉をブラウザの localStorage に覚える。既定は開いた状態で、閉じた枝の key だけを持つ。 */
export function useTreeOpen(name: string) {
  const storageKey = `tree-closed:${name}`;
  const [closed, setClosed] = useState<Set<string>>(new Set());

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey) ?? "[]");
      if (Array.isArray(saved)) setClosed(new Set(saved.map(String)));
    } catch {
      // 読めない値・使えない localStorage は、すべて開いた状態として扱う
    }
  }, [storageKey]);

  const setOpen = useCallback(
    (key: string, open: boolean) => {
      setClosed((prev) => {
        if (prev.has(key) === !open) return prev;
        const next = new Set(prev);
        if (open) next.delete(key);
        else next.add(key);
        try {
          localStorage.setItem(storageKey, JSON.stringify([...next]));
        } catch {
          // 保存できなくても、この画面の中では開閉を保つ
        }
        return next;
      });
    },
    [storageKey],
  );

  const isOpen = useCallback((key: string) => !closed.has(key), [closed]);

  const closeAll = useCallback(
    (keys: string[]) => {
      const next = new Set(keys);
      setClosed(next);
      try {
        localStorage.setItem(storageKey, JSON.stringify([...next]));
      } catch {
        // 保存できなくても、この画面の中では開閉を保つ
      }
    },
    [storageKey],
  );

  return { isOpen, setOpen, closeAll };
}
