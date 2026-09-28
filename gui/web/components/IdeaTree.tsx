"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { listAllRecords, updateRecord, type Rec } from "@/lib/api";
import { buildIdeaTree, descendantIds, findNode, type IdeaNode } from "@/lib/ideaTree";
import { useOpenPage } from "@/lib/nav";
import { T } from "@/lib/text";
import { useTreeOpen } from "@/lib/treeOpen";

type OpenState = ReturnType<typeof useTreeOpen>;

type RowProps = {
  node: IdeaNode;
  openState: OpenState;
  movingId: number | null;
  blocked: Set<number>;
  onStartMove: (id: number) => void;
  onCancelMove: () => void;
  onMoveHere: (id: number) => void;
};

function IdeaRow({ node, openState, movingId, blocked, onStartMove, onCancelMove, onMoveHere }: RowProps) {
  const openPage = useOpenPage();
  const inMoveMode = movingId !== null;
  const isSelf = movingId === node.id;
  const isBlocked = inMoveMode && (isSelf || blocked.has(node.id));
  const classes = ["tree-idea-summary"];
  if (isSelf) classes.push("moving");
  else if (isBlocked) classes.push("move-blocked");
  else if (inMoveMode) classes.push("move-target");
  const span = [node.start, node.end].filter(Boolean).join(" 〜 ");
  const key = String(node.id);

  return (
    <li className="idea-tree-node">
      <details open>
        <summary
          className={classes.join(" ")}
          onClick={(e) => {
            e.preventDefault();
            if (inMoveMode) {
              if (!isBlocked) onMoveHere(node.id);
              return;
            }
            openPage(`/tables/idea/${node.id}`, e);
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
          <button
            type="button"
            className="tree-move-btn"
            disabled={inMoveMode && !isSelf}
            onClick={(e) => {
              e.stopPropagation();
              e.preventDefault();
              if (isSelf) onCancelMove();
              else if (!inMoveMode) onStartMove(node.id);
            }}
          >
            {isSelf ? T.ideaTree.cancelMove : T.ideaTree.move}
          </button>
          <button
            type="button"
            className="tree-add-child-btn"
            disabled={inMoveMode}
            onClick={(e) => {
              e.stopPropagation();
              e.preventDefault();
              openPage(`/tables/idea/new?parent_idea_id=${node.id}`, e);
            }}
          >
            {T.ideaTree.addChild}
          </button>
        </summary>
        {node.children.length > 0 && openState.isOpen(key) && (
          <ul className="idea-tree">
            {node.children.map((child) => (
              <IdeaRow
                key={child.id}
                node={child}
                openState={openState}
                movingId={movingId}
                blocked={blocked}
                onStartMove={onStartMove}
                onCancelMove={onCancelMove}
                onMoveHere={onMoveHere}
              />
            ))}
          </ul>
        )}
      </details>
    </li>
  );
}

/** アイデア一覧をツリーで表示する。各行の Move ボタンで移動モードに入り、そのあと別のアイデアをクリックすると
 * `parent_idea_id` をそこへ差し替える(量が多いとスクロールで見切れるドラッグ&ドロップは使わない)。 */
export default function IdeaTree() {
  const [ideas, setIdeas] = useState<Rec[] | null>(null);
  const [locations, setLocations] = useState<Rec[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [movingId, setMovingId] = useState<number | null>(null);
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
  const blocked = useMemo(() => (movingId === null ? new Set<number>() : descendantIds(nodes, movingId)), [nodes, movingId]);
  const movingNode = useMemo(() => (movingId === null ? null : findNode(nodes, movingId)), [nodes, movingId]);

  const moveTo = useCallback(
    async (id: number, parentId: number | null) => {
      setSaveError(null);
      try {
        await updateRecord("idea", id, { parent_idea_id: parentId });
        await load();
        setMovingId(null);
      } catch (e) {
        setSaveError(T.ideaTree.moveFailed(e instanceof Error ? e.message : String(e)));
      }
    },
    [load],
  );

  const onMoveHere = (parentId: number | null) => {
    if (movingId === null || movingId === parentId) return;
    void moveTo(movingId, parentId);
  };

  if (error) return <div className="status error">{error}</div>;
  if (!ideas) return <div className="status info">{T.loading}</div>;
  if (nodes.length === 0) return <div className="status info">{T.ideaTree.empty}</div>;

  return (
    <div className="panel">
      {saveError && <div className="status error">{saveError}</div>}
      {movingId !== null && (
        <div className="tree-move-hint">{T.ideaTree.moveModeHint(movingNode?.name ?? `(id ${movingId})`)}</div>
      )}
      {movingId !== null && (
        <button type="button" className="tree-root-drop" onClick={() => onMoveHere(null)}>
          {T.ideaTree.moveToRoot}
        </button>
      )}
      <ul className="idea-tree idea-tree-root">
        {nodes.map((node) => (
          <IdeaRow
            key={node.id}
            node={node}
            openState={openState}
            movingId={movingId}
            blocked={blocked}
            onStartMove={setMovingId}
            onCancelMove={() => setMovingId(null)}
            onMoveHere={onMoveHere}
          />
        ))}
      </ul>
    </div>
  );
}
