"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  listExpansions, readExpansion, resolveConflict, revertExpansion, type ExpansionDetail, type ExpansionListItem,
} from "@/lib/api";
import { TABLES, PageTitle } from "@/lib/meta";
import { T } from "@/lib/text";

// 行のページを持つ表(来歴・知る相手などの子の行は、表と id だけを出す)
const PAGED_TABLES = new Set(TABLES.map((table) => table.name));

function RowRef({ table, id }: { table: string; id: number }) {
  return PAGED_TABLES.has(table) ? <Link href={`/tables/${table}/${id}`}>{`${table} #${id}`}</Link> : <span>{`${table} #${id}`}</span>;
}

function Detail({ expansion, onChanged }: { expansion: ExpansionDetail; onChanged: () => void }) {
  const [status, setStatus] = useState<string | null>(null);
  const act = async (work: () => Promise<string | null>) => {
    setStatus(null);
    try {
      setStatus(await work());
      onChanged();
    } catch (e) {
      setStatus(T.expansions.actionFailed(e instanceof Error ? e.message : String(e)));
    }
  };
  const revert = () => act(async () => {
    if (!window.confirm(T.expansions.confirmRevert(expansion.id))) return null;
    return T.expansions.reverted((await revertExpansion(expansion.id)).reverted);
  });

  return (
    <div className="expansion-detail panel">
      <h2>
        #{expansion.id} {T.expansions.mode[expansion.mode] ?? expansion.mode}{" "}
        <span className={`status-tag ${expansion.status}`}>{T.expansions.status[expansion.status] ?? expansion.status}</span>
      </h2>
      <div className="hint">
        {expansion.time && <span>{T.expansions.time}: {expansion.time} </span>}
        {expansion.actor_id !== null && <span>{T.expansions.actor}: <RowRef table="character" id={expansion.actor_id} /></span>}
      </div>
      <h3>{T.expansions.prompt}</h3>
      <pre>{expansion.prompt}</pre>
      {expansion.summary && (
        <>
          <h3>{T.expansions.summary}</h3>
          <pre>{expansion.summary}</pre>
        </>
      )}
      <h3>{T.expansions.conflicts}</h3>
      {expansion.conflicts.length === 0 && <div className="hint">{T.expansions.noConflicts}</div>}
      {expansion.conflicts.map((conflict) => (
        <div key={conflict.id} className="conflict">
          <div>
            <RowRef table={conflict.table_name} id={conflict.row_id} />{" "}
            <span className="status-tag">{conflict.status}</span>
          </div>
          <div>{conflict.detail}</div>
          {conflict.proposal && <div className="hint">{T.expansions.proposal}: {conflict.proposal}</div>}
          {conflict.status === "open" && (
            <div className="actions">
              <button type="button" title={T.expansions.acceptHint}
                onClick={() => act(async () => { await resolveConflict(conflict.id, "accepted"); return null; })}>
                {T.expansions.accept}
              </button>
              <button type="button" onClick={() => act(async () => { await resolveConflict(conflict.id, "dismissed"); return null; })}>
                {T.expansions.dismiss}
              </button>
            </div>
          )}
        </div>
      ))}
      <h3>{T.expansions.changes}</h3>
      {expansion.changes.length === 0 ? (
        <div className="hint">{T.expansions.noChanges}</div>
      ) : (
        <div className="scroll-x">
          <table className="list">
            <tbody>
              {expansion.changes.map((change) => (
                <tr key={change.id}>
                  <td>{T.expansions.op[change.op] ?? change.op}</td>
                  <td><RowRef table={change.table_name} id={change.row_id} /></td>
                  <td className="before" title={change.before ? JSON.stringify(change.before, null, 1) : undefined}>
                    {change.before ? `${T.expansions.before}: ${JSON.stringify(change.before)}` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {expansion.status !== "reverted" && expansion.changes.length > 0 && (
        <div>
          <button type="button" className="danger" onClick={revert}>{T.expansions.revert}</button>
        </div>
      )}
      {status && <div className="status info">{status}</div>}
    </div>
  );
}

/** 世界の展開(作者モード・人物モード)の一覧と、一つの展開で変えた行・作者の判断を待つ食い違い。 */
export default function ExpansionsPage() {
  const [mode, setMode] = useState("");
  const [items, setItems] = useState<ExpansionListItem[] | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [detail, setDetail] = useState<ExpansionDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    listExpansions({ limit: 200, ...(mode ? { mode } : {}) })
      .then((rows) => {
        setItems(rows);
        setError(null);
      })
      .catch((e) => setError(T.expansions.loadFailed(e instanceof Error ? e.message : String(e))));
  }, [mode, reload]);

  useEffect(() => {
    if (selected === null) {
      setDetail(null);
      return;
    }
    readExpansion(selected).then(setDetail).catch((e) => setError(T.expansions.loadFailed(String(e))));
  }, [selected, reload]);

  const refresh = useCallback(() => setReload((n) => n + 1), []);

  return (
    <>
      <PageTitle kind={T.expansions.title} />
      <h1>{T.expansions.title}</h1>
      <div className="hint">{T.expansions.intro}</div>
      <div className="toolbar">
        <span className="segment">
          {["", "author", "character"].map((value) => (
            <button key={value} type="button" className={mode === value ? "on" : ""} onClick={() => setMode(value)}>
              {value ? T.expansions.mode[value] : T.expansions.filterAll}
            </button>
          ))}
        </span>
      </div>
      {error && <div className="status error">{error}</div>}
      <div className="expansions">
        <div className="expansions-list">
          {items?.length === 0 && <div className="hint">{T.expansions.empty}</div>}
          <table className="list">
            <tbody>
              {items?.map((item) => (
                <tr key={item.id} className={item.id === selected ? "selected" : ""} onClick={() => setSelected(item.id)}>
                  <td>{item.id}</td>
                  <td>{T.expansions.mode[item.mode] ?? item.mode}</td>
                  <td className="prompt">{item.prompt || item.summary}</td>
                  <td>{T.expansions.counts(item.counts.added, item.counts.updated, item.counts.deleted)}</td>
                  <td>{item.counts.open_conflicts > 0 && <span className="chip on">{T.expansions.openConflicts(item.counts.open_conflicts)}</span>}</td>
                  <td><span className={`status-tag ${item.status}`}>{T.expansions.status[item.status] ?? item.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {detail && <Detail expansion={detail} onChanged={refresh} />}
      </div>
    </>
  );
}
