"use client";

import { useEffect } from "react";
import type { TableMeta, TablesResponse } from "./api";
import tablesJson from "./tables.json";
import { T } from "./text";

// 表の列・子の一覧は API に聞かず、書き出した JSON(`gui/api/dump_static.py`)を画面に持つ
export const TABLES: TableMeta[] = (tablesJson as unknown as TablesResponse).tables;

export function tableMeta(name: string): TableMeta | undefined {
  return TABLES.find((table) => table.name === name);
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
