"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { listAllRecords, updateRecord, type Rec } from "@/lib/api";
import { buildStoryTree, type TreeNode, type TreeStory } from "@/lib/storyTree";
import { T } from "@/lib/text";
import { useTreeOpen } from "@/lib/treeOpen";

type OpenState = ReturnType<typeof useTreeOpen>;

const UNPLACED = "unplaced";
type DropId = number | typeof UNPLACED;

type DragState = {
  draggingId: number | null;
  dropTarget: DropId | null;
  onDragStart: (id: number) => void;
  onDragEnd: () => void;
  onDragOverTarget: (target: DropId) => void;
  onDropOnTarget: (target: DropId) => void;
};

function StoryRow({ story, drag }: { story: TreeStory; drag: DragState }) {
  const span = [story.start, story.end].filter(Boolean).join(" 〜 ");
  const classes = ["tree-story", "tree-draggable"];
  if (drag.draggingId === story.id) classes.push("dragging");
  return (
    <li
      className={classes.join(" ")}
      draggable={drag.draggingId === null}
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = "move";
        drag.onDragStart(story.id);
      }}
      onDragEnd={drag.onDragEnd}
    >
      <Link href={`/tables/story/${story.id}`} draggable={false}>
        {story.name}
      </Link>
      <span className="tree-meta">
        {story.state && <span className="chip">{story.state}</span>}
        {span && <span>{span}</span>}
        <span>{T.storyTree.episodes(story.episodes)}</span>
      </span>
    </li>
  );
}

function PlaceNode({ node, openState, drag }: { node: TreeNode; openState: OpenState; drag: DragState }) {
  const key = String(node.id);
  return (
    <li className="tree-place">
      <details open={openState.isOpen(key)} onToggle={(e) => openState.setOpen(key, e.currentTarget.open)}>
        <summary
          className={drag.dropTarget === node.id ? "drop-target" : ""}
          onDragOver={(e) => {
            if (drag.draggingId === null) return;
            e.preventDefault();
            e.dataTransfer.dropEffect = "move";
            drag.onDragOverTarget(node.id);
          }}
          onDrop={(e) => {
            e.preventDefault();
            drag.onDropOnTarget(node.id);
          }}
        >
          <span className="tree-name">{node.name ?? `(id ${node.id})`}</span>
          {node.kind && <span className="tree-kind">{node.kind}</span>}
          <span className="tree-count">{T.storyTree.stories(node.total)}</span>
          <Link href={`/tables/location/${node.id}`} className="tree-link" onClick={(e) => e.stopPropagation()}>
            {T.storyTree.openLocation}
          </Link>
        </summary>
        <ul className="tree">
          {node.stories.map((story) => (
            <StoryRow key={story.id} story={story} drag={drag} />
          ))}
          {node.children.map((child) => (
            <PlaceNode key={child.id} node={child} openState={openState} drag={drag} />
          ))}
        </ul>
      </details>
    </li>
  );
}

type Source = { locations: Rec[]; stories: Rec[]; episodes: Rec[] };

/** 場所・作品・話の一覧をそのまま引いて、木はブラウザで組む。タブに戻ったときに引き直す。
 *  作品(StoryRow)の見出し行はドラッグ&ドロップで `place_id` を差し替える。 */
export default function StoryTree() {
  const [source, setSource] = useState<Source | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [draggingId, setDraggingId] = useState<number | null>(null);
  const [dropTarget, setDropTarget] = useState<DropId | null>(null);
  const openState = useTreeOpen("story");

  const load = useCallback(async () => {
    try {
      const [locations, stories, episodes] = await Promise.all([
        listAllRecords("location", { sort: "id", order: "asc" }),
        listAllRecords("story", { sort: "id", order: "asc" }),
        listAllRecords("episode", { sort: "id", order: "asc" }),
      ]);
      setSource({ locations, stories, episodes });
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

  const tree = useMemo(() => (source ? buildStoryTree(source.locations, source.stories, source.episodes) : null), [source]);

  const moveTo = useCallback(
    async (id: number, placeId: number | null) => {
      setSaveError(null);
      try {
        await updateRecord("story", id, { place_id: placeId });
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
  const onDropOnTarget = (target: DropId) => {
    const id = draggingId;
    onDragEnd();
    if (id !== null) void moveTo(id, target === UNPLACED ? null : target);
  };
  const drag: DragState = {
    draggingId,
    dropTarget,
    onDragStart: setDraggingId,
    onDragEnd,
    onDragOverTarget: setDropTarget,
    onDropOnTarget,
  };

  if (error) return <div className="status error">{error}</div>;
  if (!tree) return <div className="status info">{T.loading}</div>;
  if (tree.nodes.length === 0 && tree.unplaced.length === 0) return <div className="status info">{T.storyTree.noStories}</div>;

  return (
    <div className="panel">
      {saveError && <div className="status error">{saveError}</div>}
      <ul className="tree tree-root">
        {tree.nodes.map((node) => (
          <PlaceNode key={node.id} node={node} openState={openState} drag={drag} />
        ))}
        <li className="tree-place">
          <details open={openState.isOpen(UNPLACED)} onToggle={(e) => openState.setOpen(UNPLACED, e.currentTarget.open)}>
            <summary
              className={dropTarget === UNPLACED ? "drop-target" : ""}
              onDragOver={(e) => {
                if (draggingId === null) return;
                e.preventDefault();
                e.dataTransfer.dropEffect = "move";
                setDropTarget(UNPLACED);
              }}
              onDrop={(e) => {
                e.preventDefault();
                onDropOnTarget(UNPLACED);
              }}
            >
              <span className="tree-name">{T.storyTree.noLocation}</span>
              <span className="tree-count">{T.storyTree.stories(tree.unplaced.length)}</span>
            </summary>
            {tree.unplaced.length > 0 && (
              <ul className="tree">
                {tree.unplaced.map((story) => (
                  <StoryRow key={story.id} story={story} drag={drag} />
                ))}
              </ul>
            )}
          </details>
        </li>
      </ul>
    </div>
  );
}
