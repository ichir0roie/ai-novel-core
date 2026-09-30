"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type DragEvent } from "react";
import { listAllRecords, updateRecord, type Rec } from "@/lib/api";
import { buildStoryTree, descendantIds, type StoryNode } from "@/lib/storyTree";
import { T } from "@/lib/text";
import { useTreeOpen } from "@/lib/treeOpen";

type OpenState = ReturnType<typeof useTreeOpen>;

const ROOT = "root";
type DropId = number | typeof ROOT;

type DragState = {
  draggingId: number | null;
  dropTarget: DropId | null;
  blocked: Set<number>;
  onDragStart: (id: number) => void;
  onDragEnd: () => void;
  onDragOverTarget: (target: DropId) => void;
  onDropOnTarget: (target: DropId) => void;
};

// 行を落とし先にする。自分自身と子孫の上には落とせない(循環になる)
function dropHandlers(target: DropId, drag: DragState) {
  const allowed = () =>
    drag.draggingId !== null && (target === ROOT || (target !== drag.draggingId && !drag.blocked.has(target)));
  return {
    onDragOver: (e: DragEvent) => {
      if (!allowed()) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      drag.onDragOverTarget(target);
    },
    onDrop: (e: DragEvent) => {
      e.preventDefault();
      if (allowed()) drag.onDropOnTarget(target);
    },
  };
}

function StoryRow({ node }: { node: StoryNode }) {
  const span = [node.start, node.end].filter(Boolean).join(" 〜 ");
  return (
    <>
      <Link href={`/tables/story/${node.id}`} className="tree-name" draggable={false} onClick={(e) => e.stopPropagation()}>
        {node.name}
      </Link>
      <span className="tree-meta">
        {node.state && <span className="chip">{node.state}</span>}
        {span && <span>{span}</span>}
        <span>{T.storyTree.episodes(node.episodes)}</span>
        {node.children.length > 0 && <span>{T.storyTree.stories(node.children.length)}</span>}
      </span>
    </>
  );
}

function StoryNodeView({ node, openState, drag }: { node: StoryNode; openState: OpenState; drag: DragState }) {
  const classes = ["tree-draggable"];
  if (drag.draggingId === node.id) classes.push("dragging");
  if (drag.dropTarget === node.id) classes.push("drop-target");
  // 見出し行だけを掴ませる。li ごと掴ませると、入れ子の行の dragstart が親の li にも届いて親を掴んだことになる
  const rowProps = {
    className: classes.join(" "),
    draggable: drag.draggingId === null,
    onDragStart: (e: DragEvent) => {
      e.dataTransfer.effectAllowed = "move";
      drag.onDragStart(node.id);
    },
    onDragEnd: drag.onDragEnd,
    ...dropHandlers(node.id, drag),
  };

  if (node.children.length === 0) {
    return (
      <li className="tree-story tree-leaf">
        <div {...rowProps}>
          <StoryRow node={node} />
        </div>
      </li>
    );
  }
  const key = String(node.id);
  return (
    <li className="tree-parent">
      <details open={openState.isOpen(key)} onToggle={(e) => openState.setOpen(key, e.currentTarget.open)}>
        <summary {...rowProps}>
          <StoryRow node={node} />
        </summary>
        <ul className="tree">
          {node.children.map((child) => (
            <StoryNodeView key={child.id} node={child} openState={openState} drag={drag} />
          ))}
        </ul>
      </details>
    </li>
  );
}

type Source = { stories: Rec[]; episodes: Rec[] };

/** 作品・話の一覧をそのまま引いて、作品の親子(`parent_story_id`)の木をブラウザで組む。タブに戻ったときに引き直す。
 *  作品の見出し行はドラッグ&ドロップで、落とした先の作品の子(一番上の欄なら親なし)に付け替える。 */
export default function StoryTree() {
  const [source, setSource] = useState<Source | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [draggingId, setDraggingId] = useState<number | null>(null);
  const [dropTarget, setDropTarget] = useState<DropId | null>(null);
  const openState = useTreeOpen("story");

  const load = useCallback(async () => {
    try {
      const [stories, episodes] = await Promise.all([
        listAllRecords("story", { sort: "id", order: "asc" }),
        listAllRecords("episode", { sort: "id", order: "asc" }),
      ]);
      setSource({ stories, episodes });
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

  const nodes = useMemo(() => (source ? buildStoryTree(source.stories, source.episodes) : null), [source]);
  const blocked = useMemo(
    () => (nodes === null || draggingId === null ? new Set<number>() : descendantIds(nodes, draggingId)),
    [nodes, draggingId],
  );

  const moveTo = useCallback(
    async (id: number, parentId: number | null) => {
      setSaveError(null);
      try {
        await updateRecord("story", id, { parent_story_id: parentId });
        await load();
      } catch (e) {
        setSaveError(T.storyTree.moveFailed(e instanceof Error ? e.message : String(e)));
      }
    },
    [load],
  );

  const onDragEnd = () => {
    setDraggingId(null);
    setDropTarget(null);
  };
  const drag: DragState = {
    draggingId,
    dropTarget,
    blocked,
    onDragStart: setDraggingId,
    onDragEnd,
    onDragOverTarget: setDropTarget,
    onDropOnTarget: (target) => {
      const id = draggingId;
      onDragEnd();
      if (id !== null) void moveTo(id, target === ROOT ? null : target);
    },
  };

  if (error) return <div className="status error">{error}</div>;
  if (!nodes) return <div className="status info">{T.loading}</div>;
  if (nodes.length === 0) return <div className="status info">{T.storyTree.noStories}</div>;

  return (
    <div className="panel">
      {saveError && <div className="status error">{saveError}</div>}
      {draggingId !== null && (
        <div className={`tree-root-drop${dropTarget === ROOT ? " drop-target" : ""}`} {...dropHandlers(ROOT, drag)}>
          {T.storyTree.moveToRoot}
        </div>
      )}
      <ul className="tree tree-root">
        {nodes.map((node) => (
          <StoryNodeView key={node.id} node={node} openState={openState} drag={drag} />
        ))}
      </ul>
    </div>
  );
}
