"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type MouseEvent } from "react";
import { listAllRecords, updateStories, type Rec } from "@/lib/api";
import NameId from "./NameId";
import { buildStoryTree, collapsibleIds, descendantIds, findNode, type StoryNode } from "@/lib/storyTree";
import { useOpenPage } from "@/lib/nav";
import { T } from "@/lib/text";
import { useTreeOpen } from "@/lib/treeOpen";

type OpenState = ReturnType<typeof useTreeOpen>;

const ROOT = "root";
type MoveTarget = number | typeof ROOT;

type ContextMenuState = { node: StoryNode; x: number; y: number };

// 編集モードの状態。movingId は親を付け替えている作品、blocked はその子孫(親にすると循環になる)
type MoveState = {
  editing: boolean;
  movingId: number | null;
  blocked: Set<number>;
  onStartMove: (id: number) => void;
  onCancelMove: () => void;
  onMoveHere: (target: MoveTarget) => void;
  onContextMenu: (menu: ContextMenuState) => void;
  // 兄弟の中で一つ上(-1)・下(+1)へ並べ替える
  onShift: (siblings: StoryNode[], index: number, delta: -1 | 1) => void;
};

type RowProps = { node: StoryNode; siblings: StoryNode[]; index: number; move: MoveState };

function StoryRow({ node, siblings, index, move }: RowProps) {
  const inMoveMode = move.movingId !== null;
  const isSelf = move.movingId === node.id;
  const shiftButton = (delta: -1 | 1) => (
    <button
      type="button"
      className="tree-move-btn"
      title={delta < 0 ? T.storyTree.moveUp : T.storyTree.moveDown}
      disabled={inMoveMode || !siblings[index + delta]}
      onClick={(e) => {
        e.stopPropagation();
        e.preventDefault();
        move.onShift(siblings, index, delta);
      }}
    >
      {delta < 0 ? "▲" : "▼"}
    </button>
  );
  return (
    <>
      <Link
        href={`/tables/story/${node.id}`}
        className="tree-name"
        onClick={(e) => {
          e.stopPropagation();
          // 編集モードで画面を移ると溜めた変更が消えるので、開かない
          if (move.editing) e.preventDefault();
        }}
      >
        <NameId name={node.name} id={node.id} />
      </Link>
      <span className="tree-meta">
        <span>{T.storyTree.episodes(node.episodes)}</span>
        {node.children.length > 0 && <span>{T.storyTree.stories(node.children.length)}</span>}
      </span>
      {move.editing && (
        <>
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
            {isSelf ? T.storyTree.cancelMove : T.storyTree.changeParent}
          </button>
          {shiftButton(-1)}
          {shiftButton(1)}
        </>
      )}
    </>
  );
}

function StoryNodeView({ node, siblings, index, openState, move }: RowProps & { openState: OpenState }) {
  const inMoveMode = move.movingId !== null;
  const isSelf = move.movingId === node.id;
  const isBlocked = inMoveMode && (isSelf || move.blocked.has(node.id));
  const classes = ["tree-story-row"];
  if (isSelf) classes.push("moving");
  else if (isBlocked) classes.push("move-blocked");
  else if (inMoveMode) classes.push("move-target");
  const rowProps = {
    className: classes.join(" "),
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
          <StoryRow node={node} siblings={siblings} index={index} move={move} />
        </div>
      </li>
    );
  }
  const key = String(node.id);
  return (
    <li className="tree-parent">
      <details open={openState.isOpen(key)} onToggle={(e) => openState.setOpen(key, e.currentTarget.open)}>
        <summary {...rowProps}>
          <StoryRow node={node} siblings={siblings} index={index} move={move} />
        </summary>
        <ul className="tree">
          {node.children.map((child, i) => (
            <StoryNodeView key={child.id} node={child} siblings={node.children} index={i} openState={openState} move={move} />
          ))}
        </ul>
      </details>
    </li>
  );
}

type Source = { stories: Rec[]; episodes: Rec[] };
// 編集モードで溜めている作品ごとの変更。適用するまで db に書かない
type Patch = { parent_story_id?: number | null; display_order?: number };
type Draft = Map<number, Patch>;

// 兄弟の並びどおりに display_order を上から 1, 2, … に振り直す
const renumber = (draft: Draft, ids: number[]): Draft => {
  const next = new Map(draft);
  ids.forEach((id, i) => next.set(id, { ...next.get(id), display_order: i + 1 }));
  return next;
};

/** 作品・話の一覧をそのまま引いて、作品の親子(`parent_story_id`)の木をブラウザで組む。タブに戻ったときに引き直す。
 *  上の Move ボタンで編集モードに入ると、行に Change parent と ▲▼ が出る。
 *  親の付け替えは、Change parent を押して別の作品をクリックする(一番上の欄なら親なし)。新しい親の子の一番下に付く。
 *  兄弟の中の並びは ▲▼ で入れ替え、兄弟みんなの `display_order` を上から 1, 2, … に振り直す。
 *  変更はブラウザに溜め、Apply で `story.update_stories.UpdateStories` にまとめて渡す。
 *  ドラッグ&ドロップはタッチで動かず、量が多いとスクロールで見切れるので持たない。行の右クリックで、子の作品・話を足すメニューを出す。 */
export default function StoryTree() {
  const openPage = useOpenPage();
  const [source, setSource] = useState<Source | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [movingId, setMovingId] = useState<number | null>(null);
  const [menu, setMenu] = useState<ContextMenuState | null>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Draft>(new Map());
  const [saving, setSaving] = useState(false);
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

  const stories = useMemo(
    () => source?.stories.map((story) => ({ ...story, ...draft.get(Number(story.id)) })) ?? null,
    [source, draft],
  );
  // 溜めた変更のうち、db の値と違うもの。▲▼ を押して戻したものは出さない
  const changes = useMemo(
    () =>
      (source?.stories ?? []).flatMap((story) => {
        const patch = draft.get(Number(story.id)) ?? {};
        const changed = Object.entries(patch).filter(([key, value]) => (story[key] ?? null) !== value);
        return changed.length > 0 ? [{ id: Number(story.id), ...Object.fromEntries(changed) }] : [];
      }),
    [source, draft],
  );
  const nodes = useMemo(
    () => (source && stories ? buildStoryTree(stories, source.episodes) : null),
    [source, stories],
  );
  const blocked = useMemo(
    () => (nodes === null || movingId === null ? new Set<number>() : descendantIds(nodes, movingId)),
    [nodes, movingId],
  );
  const movingNode = useMemo(() => (nodes === null || movingId === null ? null : findNode(nodes, movingId)), [nodes, movingId]);

  useEffect(() => {
    if (changes.length === 0) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [changes.length]);

  const moveTo = (id: number, parentId: number | null) => {
    setMovingId(null);
    if (nodes === null) return;
    const siblings = parentId === null ? nodes : (findNode(nodes, parentId)?.children ?? []);
    if (siblings.some((n) => n.id === id)) return;
    const next = renumber(draft, [...siblings.map((n) => n.id), id]);
    next.set(id, { ...next.get(id), parent_story_id: parentId });
    setDraft(next);
  };

  const shift = (siblings: StoryNode[], index: number, delta: -1 | 1) => {
    const ids = siblings.map((n) => n.id);
    [ids[index], ids[index + delta]] = [ids[index + delta], ids[index]];
    setDraft(renumber(draft, ids));
  };

  const leaveEditing = () => {
    setDraft(new Map());
    setMovingId(null);
    setEditing(false);
  };

  const apply = async () => {
    setSaveError(null);
    setSaving(true);
    try {
      await updateStories(changes);
      await load();
      leaveEditing();
    } catch (e) {
      setSaveError(T.storyTree.applyFailed(e instanceof Error ? e.message : String(e)));
    } finally {
      setSaving(false);
    }
  };

  const move: MoveState = {
    editing,
    movingId,
    blocked,
    onStartMove: setMovingId,
    onCancelMove: () => setMovingId(null),
    onMoveHere: (target) => {
      if (movingId === null || movingId === target) return;
      moveTo(movingId, target === ROOT ? null : target);
    },
    onContextMenu: setMenu,
    onShift: shift,
  };

  if (error) return <div className="status error">{error}</div>;
  if (!nodes) return <div className="status info">{T.loading}</div>;
  if (nodes.length === 0) return <div className="status info">{T.storyTree.noStories}</div>;

  return (
    <div className="panel">
      <div className="toolbar">
        {editing ? (
          <>
            <button type="button" className="primary" disabled={changes.length === 0 || saving} onClick={() => void apply()}>
              {T.storyTree.apply(changes.length)}
            </button>
            <button
              type="button"
              disabled={saving}
              onClick={() => {
                if (changes.length === 0 || window.confirm(T.storyTree.confirmDiscard(changes.length))) leaveEditing();
              }}
            >
              {T.storyTree.discard}
            </button>
            <span className="tree-move-hint">{T.storyTree.editHint}</span>
          </>
        ) : (
          <button type="button" onClick={() => setEditing(true)}>
            {T.storyTree.move}
          </button>
        )}
      </div>
      {saveError && <div className="status error">{saveError}</div>}
      {movingId !== null && (
        <div className="tree-move-hint">{T.storyTree.moveModeHint(T.nameId(movingNode?.name, movingId))}</div>
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
        {nodes.map((node, i) => (
          <StoryNodeView key={node.id} node={node} siblings={nodes} index={i} openState={openState} move={move} />
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
