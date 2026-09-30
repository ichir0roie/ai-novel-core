"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { getTables, type ClaudeMode, type TableMeta } from "./api";
import { T } from "./text";

type MetaContextValue = {
  tables: TableMeta[];
  /** 「AI で作成」を押せるか(false なら使えない)。API がその場で回すか(direct)、ルーチンの待ち行列に積むか(queue) */
  claudeAvailable: boolean;
  claudeMode: ClaudeMode;
  error: string | null;
  loading: boolean;
  reload: () => Promise<void>;
};

const MetaContext = createContext<MetaContextValue>({
  tables: [],
  claudeAvailable: false,
  claudeMode: "off",
  error: null,
  loading: true,
  reload: async () => {},
});

export function MetaProvider({ children }: { children: ReactNode }) {
  const [tables, setTables] = useState<TableMeta[]>([]);
  const [claudeAvailable, setClaudeAvailable] = useState(false);
  const [claudeMode, setClaudeMode] = useState<ClaudeMode>("off");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // effect の中で同期的に setState しない(await の後でだけ状態を触る)
  const reload = useCallback(async () => {
    try {
      const result = await getTables();
      setTables(result.tables);
      setClaudeAvailable(result.claude_available ?? false);
      setClaudeMode(result.claude_mode ?? "off");
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return (
    <MetaContext.Provider value={{ tables, claudeAvailable, claudeMode, error, loading, reload }}>{children}</MetaContext.Provider>
  );
}

export function useMeta() {
  return useContext(MetaContext);
}

export function useTable(name: string): TableMeta | undefined {
  return useMeta().tables.find((table) => table.name === name);
}

// タブのタイトルを「ページの種類 - レコードの名前」に合わせる(record が無ければ種類だけ)。
// Next の metadata(layout.tsx の静的 <title>)がハイドレート後に遅れて自分の値で <title> を
// 上書きしてくることがあるため、一度書き換えたあとも MutationObserver で見張り、書き戻す
export function PageTitle({ kind, record }: { kind: string | null | undefined; record?: string | null }) {
  useEffect(() => {
    if (!kind) return;
    const desired = T.pageTitle(kind, record);
    document.title = desired;
    const observer = new MutationObserver(() => {
      if (document.title !== desired) document.title = desired;
    });
    observer.observe(document.head, { childList: true, subtree: true, characterData: true });
    return () => observer.disconnect();
  }, [kind, record]);
  return null;
}
