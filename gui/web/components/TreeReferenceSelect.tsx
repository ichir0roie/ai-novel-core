"use client";

import { useMemo, useState } from "react";
import Modal from "./Modal";
import { PickerToggle } from "./Picker";
import { RecordLink, useOptions } from "./ReferenceSelect";
import { buildOptionTree, type OptionNode } from "@/lib/optionTree";
import { useTreeOpen } from "@/lib/treeOpen";
import { T } from "@/lib/text";

type Props = {
  table: string;
  value: number | null;
  nullable: boolean;
  onChange: (value: number | null) => void;
  disabled?: boolean;
  // 選ぶモーダルの見出し(欄の名前)
  title?: string;
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

/** 絞り込みに一致した行を、子孫ごと残す。一致した行の子孫にある一致は、その枝の中に出るので根には並べない。 */
function matchedSubtrees(nodes: OptionNode[], matches: (node: OptionNode) => boolean): OptionNode[] {
  return nodes.flatMap((node) => (matches(node) ? [node] : matchedSubtrees(node.children, matches)));
}

/** 場所・アイデアのように親子を持つテーブルの参照選択。押すとモーダルに親子のツリーを大きく表示し、
 * クリックした行を選ぶ。絞り込み文字列があるあいだは、一致した行とその子孫だけのツリーにする。 */
export default function TreeReferenceSelect({ table, value, nullable, onChange, disabled, title }: Props) {
  const options = useOptions(table);
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const openState = useTreeOpen(`select:${table}`);

  const tree = useMemo(() => buildOptionTree(options), [options]);
  const current = options.find((o) => o.id === value);
  const q = filter.trim();
  const shown = useMemo(
    () => (q ? matchedSubtrees(tree, (node) => node.label.includes(q) || String(node.id) === q) : tree),
    [tree, q],
  );

  const close = () => {
    setOpen(false);
    setFilter("");
  };
  const pick = (id: number | null) => {
    onChange(id);
    close();
  };

  return (
    <div className="picker">
      <PickerToggle
        label={current ? `${current.id}: ${current.label}` : value !== null ? `id ${value}` : nullable ? T.none : T.select}
        empty={value === null}
        onClick={() => setOpen(true)}
        disabled={disabled}
      />
      {value !== null && <RecordLink table={table} id={value} />}
      {open && (
        <Modal title={title ?? T.select} onClose={close}>
          <input type="text" className="picker-filter" placeholder={T.filter} value={filter} autoFocus onChange={(e) => setFilter(e.target.value)} />
          {nullable && !q && (
            <button type="button" className={`tree-select-label tree-select-none ${value === null ? "selected" : ""}`} onClick={() => pick(null)}>
              {T.none}
            </button>
          )}
          <ul className="tree tree-root tree-select-tree">
            {shown.map((node) => (
              <NodeRow key={node.id} node={node} depth={0} selectedId={value} openState={openState} onPick={pick} />
            ))}
            {q && shown.length === 0 && <span className="hint">{T.noCandidates}</span>}
          </ul>
        </Modal>
      )}
    </div>
  );
}
