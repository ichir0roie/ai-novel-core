"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useOptions } from "./ReferenceSelect";
import { buildOptionTree, type OptionNode } from "@/lib/optionTree";
import { useTreeOpen } from "@/lib/treeOpen";
import { T } from "@/lib/text";

type Props = {
  table: string;
  value: number | null;
  nullable: boolean;
  onChange: (value: number | null) => void;
  disabled?: boolean;
};

type OpenState = ReturnType<typeof useTreeOpen>;

function NodeRow({
  node,
  depth,
  selectedId,
  openState,
  onPick,
}: {
  node: OptionNode;
  depth: number;
  selectedId: number | null;
  openState: OpenState;
  onPick: (id: number) => void;
}) {
  const key = String(node.id);
  const hasChildren = node.children.length > 0;
  const open = openState.isOpen(key);
  return (
    <li>
      <div className="tree-select-row" style={{ paddingLeft: `${depth * 1.1}rem` }}>
        {hasChildren ? (
          <button
            type="button"
            className="tree-caret"
            aria-label={open ? T.treeSelect.collapse : T.treeSelect.expand}
            onClick={() => openState.setOpen(key, !open)}
          >
            {open ? "▼" : "▶"}
          </button>
        ) : (
          <span className="tree-caret-spacer" />
        )}
        <button
          type="button"
          className={`tree-select-label ${node.id === selectedId ? "selected" : ""}`}
          onClick={() => onPick(node.id)}
        >
          {node.id}: {node.label}
        </button>
      </div>
      {hasChildren && open && (
        <ul className="tree">
          {node.children.map((child) => (
            <NodeRow key={child.id} node={child} depth={depth + 1} selectedId={selectedId} openState={openState} onPick={onPick} />
          ))}
        </ul>
      )}
    </li>
  );
}

/** 場所・アイデアのように親子を持つテーブルの参照選択。ポップアップに親子のツリーを表示し、
 * クリックした行を選ぶ。絞り込み文字列があるあいだはツリーを外して一致した行だけを並べる。 */
export default function TreeReferenceSelect({ table, value, nullable, onChange, disabled }: Props) {
  const options = useOptions(table);
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);
  const openState = useTreeOpen(`select:${table}`);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const tree = useMemo(() => buildOptionTree(options), [options]);
  const current = options.find((o) => o.id === value);
  const q = filter.trim();
  const flatMatches = useMemo(
    () => (q ? options.filter((o) => o.label.includes(q) || String(o.id) === q) : []),
    [options, q],
  );

  const pick = (id: number | null) => {
    onChange(id);
    setOpen(false);
    setFilter("");
  };

  return (
    <div className="tree-select" ref={containerRef}>
      <button type="button" className="tree-select-toggle" onClick={() => setOpen((v) => !v)} disabled={disabled}>
        {current ? `${current.id}: ${current.label}` : value !== null ? `id ${value}` : nullable ? T.none : T.select}
        {" ▾"}
      </button>
      {open && (
        <div className="tree-select-popup">
          <input
            type="text"
            placeholder={T.filter}
            value={filter}
            autoFocus
            onChange={(e) => setFilter(e.target.value)}
          />
          {nullable && !q && (
            <button type="button" className="tree-select-label tree-select-none" onClick={() => pick(null)}>
              {T.none}
            </button>
          )}
          <div className="tree-select-scroll">
            {q ? (
              <ul className="tree">
                {flatMatches.map((o) => (
                  <li key={o.id}>
                    <button type="button" className={`tree-select-label ${o.id === value ? "selected" : ""}`} onClick={() => pick(o.id)}>
                      {o.id}: {o.label}
                    </button>
                  </li>
                ))}
                {flatMatches.length === 0 && <span className="hint">{T.noCandidates}</span>}
              </ul>
            ) : (
              <ul className="tree tree-root">
                {tree.map((node) => (
                  <NodeRow key={node.id} node={node} depth={0} selectedId={value} openState={openState} onPick={pick} />
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
