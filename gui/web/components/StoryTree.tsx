"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type DragEvent, type MouseEvent } from "react";
import { listAllRecords, updateRecord, type Rec } from "@/lib/api";
import { buildStoryTree, collapsibleIds, descendantIds, findNode, type StoryNode } from "@/lib/storyTree";
import { useOpenPage } from "@/lib/nav";
import { T } from "@/lib/text";
import { useTreeOpen } from "@/lib/treeOpen";

type OpenState = ReturnType<typeof useTreeOpen>;

const ROOT = "root";
type DropId = number | typeof ROOT;

type ContextMenuState = { node: StoryNode; x: number; y: number };

// ドラッグ&ドロップと、Move ボタンの移動モード(量が多くドラッグ中にスクロールで見切れるとき用)の両方の状態
type MoveState = {
  draggingId: number | null;
  dropTarget: DropId | null;
  movingId: number | null;
  blocked: Set<number>;
  onDragStart: (id: number) => void;
  onDragEnd: () => void;
  onDragOverTarget: (target: DropId) => void;
  onDropOnTarget: (target: DropId) => void;
  onStartMove: (id: number) => void;
  onCancelMove: () => void;
  onMoveHere: (target: DropId) => void;
  onContextMenu: (menu: ContextMenuState) => void;
};

// 行を落とし先にする。自分自身と子孫の上には落とせない(循環になる)
function dropHandlers(target: DropId, move: MoveState) {
  const allowed = () =>
    move.draggingId !== null && (target === ROOT || (target !== move.draggingId && !move.blocked.has(target)));
  return {
    onDragOver: (e: DragEvent) => {
      if (!allowed()) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      move.onDragOverTarget(target);
    },
    onDrop: (e: DragEvent) => {
      e.preventDefault();
      if (allowed()) move.onDropOnTarget(target);
    },
  };
}

function StoryRow({ node, move }: { node: StoryNode; move: MoveState }) {
  const span = [node.start, node.end].filter(Boolean).join(" 〜 ");
  const inMoveMode = move.movingId !== null;
  const isSelf = move.movingId === node.id;
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
      <button
        type="button"
        className="tree-move-btn"
        disabled={inMoveMode && !isSelf}
        onClick={(e) => {
          e.stopPropagation();
          e.preventDefault();
          if (isSelf) move.onCancelMove();
          else if (!inMoveMode) move.onStartMove(node.id);
        }}
      >
        {isSelf ? T.storyTree.cancelMove : T.storyTree.move}
      </button>
    </>
  );
}

function StoryNodeView({ node, openState, move }: { node: StoryNode; openState: OpenState; move: MoveState }) {
  const inMoveMode = move.movingId !== null;
  const isSelf = move.movingId === node.id;
  const isBlocked = inMoveMode && (isSelf || move.blocked.has(node.id));
  const classes = ["tree-draggable"];
  if (move.draggingId === node.id) classes.push("dragging");
  if (move.dropTarget === node.id) classes.push("drop-target");
  if (isSelf) classes.push("moving");
  else if (isBlocked) classes.push("move-blocked");
  else if (inMoveMode) classes.push("move-target");
  // 見出し行だけを掴ませる。li ごと掴ませると、入れ子の行の dragstart が親の li にも届いて親を掴んだことになる
  const rowProps = {
    className: classes.join(" "),
    draggable: move.draggingId === null && !inMoveMode,
    onDragStart: (e: DragEvent) => {
      e.dataTransfer.effectAllowed = "move";
      move.onDragStart(node.id);
    },
    onDragEnd: move.onDragEnd,
    ...dropHandlers(node.id, move),
    // 移動モードの間は、行のクリックで開閉・リンクへの移動をせず、クリックした作品を親にする
    onClickCapture: (e: MouseEvent) => {
      if (!inMoveMode || (e.target as HTMLElement).closest(".tree-move-btn")) return;
      e.preventDefault();
      e.stopPropagation();
      if (!isBlocked) move.onMoveHere(node.id);
    },
    onContextMenu: (e: MouseEvent) => {
      e.preventDefault();
      if (!inMoveMode) move.onContextMenu({ node, x: e.clientX, y: e.clientY });
    },
  };

  if (node.children.length === 0) {
    return (
      <li className="tree-story tree-leaf">
        <div {...rowProps}>
          <StoryRow node={node} move={move} />
        </div>
      </li>
    );
  }
  const key = String(node.id);
  return (
    <li className="tree-parent">
      <details open={openState.isOpen(key)} onToggle={(e) => openState.setOpen(key, e.currentTarget.open)}>
        <summary {...rowProps}>
          <StoryRow node={node} move={move} />
        </summary>
        <ul className="tree">
          {node.children.map((child) => (
            <StoryNodeView key={child.id} node={child} openState={openState} move={move} />
          ))}
        </ul>
      </details>
    </li>
  );
}

type Source = { stories: Rec[]; episodes: Rec[] };

/** 作品・話の一覧をそのまま引いて、作品の親子(`parent_story_id`)の木をブラウザで組む。タブに戻ったときに引き直す。
 *  親の付け替えは、見出し行のドラッグ&ドロップか、Move ボタンで移動モードに入って別の作品をクリックする
 *  (一番上の欄なら親なし)。行の右クリックで、子の作品・話を足すメニューを出す。 */
export default function StoryTree() {
  const openPage = useOpenPage();
  const [source, setSource] = useState<Source | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [draggingId, setDraggingId] = useState<number | null>(null);
  const [dropTarget, setDropTarget] = useState<DropId | null>(null);
  const [movingId, setMovingId] = useState<number | null>(null);
  const [menu, setMenu] = useState<ContextMenuState | null>(null);
  const openState = useTreeOpen("story");

  useEffect(() => {
    if (!menu && movingId === null) return;
    const close = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setMenu(null);
      setMovingId(null);
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [menu, movingId]);

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
  const activeId = draggingId ?? movingId;
  const blocked = useMemo(
    () => (nodes === null || activeId === null ? new Set<number>() : descendantIds(nodes, activeId)),
    [nodes, activeId],
  );
  const movingNode = useMemo(() => (nodes === null || movingId === null ? null : findNode(nodes, movingId)), [nodes, movingId]);

  const moveTo = useCallback(
    async (id: number, parentId: number | null) => {
      setSaveError(null);
      try {
        await updateRecord("story", id, { parent_story_id: parentId });
        await load();
        setMovingId(null);
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
  const move: MoveState = {
    draggingId,
    dropTarget,
    movingId,
    blocked,
    onDragStart: setDraggingId,
    onDragEnd,
    onDragOverTarget: setDropTarget,
    onDropOnTarget: (target) => {
      const id = draggingId;
      onDragEnd();
      if (id !== null) void moveTo(id, target === ROOT ? null : target);
    },
    onStartMove: setMovingId,
    onCancelMove: () => setMovingId(null),
    onMoveHere: (target) => {
      if (movingId === null || movingId === target) return;
      void moveTo(movingId, target === ROOT ? null : target);
    },
    onContextMenu: setMenu,
  };

  if (error) return <div className="status error">{error}</div>;
  if (!nodes) return <div className="status info">{T.loading}</div>;
  if (nodes.length === 0) return <div className="status info">{T.storyTree.noStories}</div>;

  return (
    <div className="panel">
      {saveError && <div className="status error">{saveError}</div>}
      {movingId !== null && (
        <div className="tree-move-hint">{T.storyTree.moveModeHint(movingNode?.name ?? `(id ${movingId})`)}</div>
      )}
      {draggingId !== null && (
        <div className={`tree-root-drop${dropTarget === ROOT ? " drop-target" : ""}`} {...dropHandlers(ROOT, move)}>
          {T.storyTree.moveToRoot}
        </div>
      )}
      {movingId !== null && (
        <button type="button" className="tree-root-drop" onClick={() => move.onMoveHere(ROOT)}>
          {T.storyTree.moveToRoot}
        </button>
      )}
      <button type="button" className="tree-root-drop" onClick={() => openState.closeAll(collapsibleIds(nodes))}>
        {T.storyTree.collapseAll}
      </button>
      <ul className="tree tree-root">
        {nodes.map((node) => (
          <StoryNodeView key={node.id} node={node} openState={openState} move={move} />
        ))}
      </ul>
      {menu && (
        <>
          <div
            className="context-menu-backdrop"
            onClick={() => setMenu(null)}
            onContextMenu={(e) => {
              e.preventDefault();
              setMenu(null);
            }}
          />
          <div className="context-menu" style={{ left: menu.x, top: menu.y }}>
            <button
              type="button"
              className="context-menu-item"
              onClick={(e) => {
                setMenu(null);
                openPage(`/tables/story/new?parent_story_id=${menu.node.id}`, e);
              }}
            >
              {T.storyTree.addChild}
            </button>
            <button
              type="button"
              className="context-menu-item"
              onClick={(e) => {
                setMenu(null);
                openPage(`/tables/episode/new?story_id=${menu.node.id}`, e);
              }}
            >
              {T.storyTree.addEpisode}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
