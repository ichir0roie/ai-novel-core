import { useRouter } from "next/navigation";
import { useCallback } from "react";

/** クリックによるページ移動。同じタブで移り、Ctrl/⌘ を押したクリックだけ別タブで開く。 */
export function useOpenPage() {
  const router = useRouter();
  return useCallback(
    (url: string, e?: { ctrlKey: boolean; metaKey: boolean }) => {
      if (e && (e.ctrlKey || e.metaKey)) window.open(url, "_blank", "noopener,noreferrer");
      else router.push(url);
    },
    [router],
  );
}
