"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { listAllRecords, updateRecord, type Rec } from "@/lib/api";
import { buildIdeaTree, descendantIds, type IdeaNode } from "@/lib/ideaTree";
import { useOpenPage } from "@/lib/nav";
import { T } from "@/lib/text";
import { useTreeOpen } from "@/lib/treeOpen";

type OpenState = ReturnType<typeof useTreeOpen>;

type RowProps = {
  node: IdeaNode;
  openState: OpenState;
  draggingId: number | null;
  blocked: Set<number>;
  dropTarget: number | null;
  onDragStart: (id: number) => void;
  onDragEnd: () => void;
  onDragOverNode: (id: number) => void;
  onDropOnNode: (id: number) => void;
};

function IdeaRow({ node, openState, draggingId, blocked, dropTarget, onDragStart, onDragEnd, onDragOverNode, onDropOnNode }: RowProps) {
  const openPage = useOpenPage();
  const isBlocked = draggingId !== null && (draggingId === node.id || blocked.has(node.id));
  const classes = ["tree-idea-summary", "tree-draggable"];
  if (draggingId === node.id) classes.push("dragging");
  if (dropTarget === node.id && !isBlocked) classes.push("drop-target");
  const span = [node.start, node.end].filter(Boolean).join(" 〜 ");
  const key = String(node.id);

  return (
    <li className="tree-place">
      <details open>
        <summary
          className={classes.join(" ")}
          draggable={draggingId === null}
          onClick={(e) => {
            e.preventDefault();
            openPage(`/tables/idea/${node.id}`, e);
          }}
          onDragStart={(e) => {
            e.dataTransfer.effectAllowed = "move";
            onDragStart(node.id);
          }}
          onDragEnd={onDragEnd}
          onDragOver={(e) => {
            if (isBlocked) return;
            e.preventDefault();
            e.dataTransfer.dropEffect = "move";
            onDragOverNode(node.id);
          }}
          onDrop={(e) => {
            e.preventDefault();
            if (!isBlocked) onDropOnNode(node.id);
          }}
        >
          {node.children.length > 0 && (
            <button
              type="button"
              className="tree-caret"
              aria-label={openState.isOpen(key) ? T.ideaTree.collapse : T.ideaTree.expand}
              onClick={(e) => {
                e.stopPropagation();
                e.preventDefault();
                openState.setOpen(key, !openState.isOpen(key));
              }}
            >
              {openState.isOpen(key) ? "▼" : "▶"}
            </button>
          )}
          <span className="tree-name">{node.name ?? `(id ${node.id})`}</span>
          {node.kind && <span className="tree-kind">{node.kind}</span>}
          {node.confirmed && node.confirmed !== "承認" && <span className="chip">{node.confirmed}</span>}
          <span className="tree-meta">
            {node.locationName && <span>{node.locationName}</span>}
            {span && <span>{span}</span>}
          </span>
        </summary>
        {node.preview && <p className="tree-text">{node.preview}</p>}
        {node.children.length > 0 && openState.isOpen(key) && (
          <ul className="tree">
            {node.children.map((child) => (
              <IdeaRow
                key={child.id}
                node={child}
                openState={openState}
                draggingId={draggingId}
                blocked={blocked}
                dropTarget={dropTarget}
                onDragStart={onDragStart}
                onDragEnd={onDragEnd}
                onDragOverNode={onDragOverNode}
                onDropOnNode={onDropOnNode}
              />
            ))}
          </ul>
        )}
      </details>
    </li>
  );
}

const ROOT = -1;

/** アイデア一覧をツリーで表示し、見出し行のドラッグ&ドロップで `parent_idea_id` を差し替える。 */
export default function IdeaTree() {
  const [ideas, setIdeas] = useState<Rec[] | null>(null);
  const [locations, setLocations] = useState<Rec[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [draggingId, setDraggingId] = useState<number | null>(null);
  const [dropTarget, setDropTarget] = useState<number | null>(null);
  const openState = useTreeOpen("idea");

  const load = useCallback(async () => {
    try {
      const [items, locs] = await Promise.all([
        listAllRecords("idea", { sort: "id", order: "asc" }),
        listAllRecords("location", { sort: "id", order: "asc" }),
      ]);
      setIdeas(items);
      setLocations(locs);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void load();
    window.addEventListener("focus", load);
    return () => window.removeEventListener("focus", load);
  }, [load]);

  const nodes = useMemo(() => (ideas ? buildIdeaTree(ideas, locations) : []), [ideas, locations]);
  const blocked = useMemo(() => (draggingId === null ? new Set<number>() : descendantIds(nodes, draggingId)), [nodes, draggingId]);

  const moveTo = useCallback(
    async (id: number, parentId: number | null) => {
      setSaveError(null);
      try {
        await updateRecord("idea", id, { parent_idea_id: parentId });
        await load();
      } catch (e) {
        setSaveError(T.ideaTree.moveFailed(e instanceof Error ? e.message : String(e)));
      }
    },
    [load],
  );

  const onDragEnd = () => {
    setDraggingId(null);
    setDropTarget(null);
  };
  const onDropOnNode = (parentId: number) => {
    const id = draggingId;
    onDragEnd();
    if (id !== null && id !== parentId) void moveTo(id, parentId);
  };
  const onDropOnRoot = () => {
    const id = draggingId;
    onDragEnd();
    if (id !== null) void moveTo(id, null);
  };

  if (error) return <div className="status error">{error}</div>;
  if (!ideas) return <div className="status info">{T.loading}</div>;
  if (nodes.length === 0) return <div className="status info">{T.ideaTree.empty}</div>;

  return (
    <div className="panel">
      {saveError && <div className="status error">{saveError}</div>}
      <div
        className={`tree-root-drop ${dropTarget === ROOT ? "drop-target" : ""}`}
        onDragOver={(e) => {
          if (draggingId === null) return;
          e.preventDefault();
          e.dataTransfer.dropEffect = "move";
          setDropTarget(ROOT);
        }}
        onDrop={(e) => {
          e.preventDefault();
          onDropOnRoot();
        }}
      >
        {T.ideaTree.dropToRoot}
      </div>
      <ul className="tree tree-root">
        {nodes.map((node) => (
          <IdeaRow
            key={node.id}
            node={node}
            openState={openState}
            draggingId={draggingId}
            blocked={blocked}
            dropTarget={dropTarget}
            onDragStart={setDraggingId}
            onDragEnd={onDragEnd}
            onDragOverNode={setDropTarget}
            onDropOnNode={onDropOnNode}
          />
        ))}
      </ul>
    </div>
  );
}
