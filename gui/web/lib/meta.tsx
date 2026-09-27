"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { getTables, type TableMeta } from "./api";

type MetaContextValue = {
  tables: TableMeta[];
  error: string | null;
  loading: boolean;
  reload: () => Promise<void>;
};

const MetaContext = createContext<MetaContextValue>({ tables: [], error: null, loading: true, reload: async () => {} });

export function MetaProvider({ children }: { children: ReactNode }) {
  const [tables, setTables] = useState<TableMeta[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // effect の中で同期的に setState しない(await の後でだけ状態を触る)
  const reload = useCallback(async () => {
    try {
      const result = await getTables();
      setTables(result.tables);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return <MetaContext.Provider value={{ tables, error, loading, reload }}>{children}</MetaContext.Provider>;
}

export function useMeta() {
  return useContext(MetaContext);
}

export function useTable(name: string): TableMeta | undefined {
  return useMeta().tables.find((table) => table.name === name);
}
