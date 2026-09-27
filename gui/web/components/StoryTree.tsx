"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { listAllRecords, type Rec } from "@/lib/api";
import { buildStoryTree, type TreeNode, type TreeStory } from "@/lib/storyTree";
import { T } from "@/lib/text";

function StoryRow({ story }: { story: TreeStory }) {
  const span = [story.start, story.end].filter(Boolean).join(" 〜 ");
  return (
    <li className="tree-story">
      <Link href={`/tables/story/${story.id}`}>{story.name}</Link>
      <span className="tree-meta">
        {story.state && <span className="chip">{story.state}</span>}
        {span && <span>{span}</span>}
        <span>{T.storyTree.plots(story.plots)}</span>
      </span>
    </li>
  );
}

function PlaceNode({ node }: { node: TreeNode }) {
  return (
    <li className="tree-place">
      <details open>
        <summary>
          <span className="tree-name">{node.name ?? `(id ${node.id})`}</span>
          {node.kind && <span className="tree-kind">{node.kind}</span>}
          <span className="tree-count">{T.storyTree.stories(node.total)}</span>
          <Link href={`/tables/location/${node.id}`} className="tree-link" onClick={(e) => e.stopPropagation()}>
            {T.storyTree.openLocation}
          </Link>
        </summary>
        <ul className="tree">
          {node.stories.map((story) => (
            <StoryRow key={story.id} story={story} />
          ))}
          {node.children.map((child) => (
            <PlaceNode key={child.id} node={child} />
          ))}
        </ul>
      </details>
    </li>
  );
}

type Source = { locations: Rec[]; stories: Rec[]; plots: Rec[] };

/** 場所・作品・話の一覧をそのまま引いて、木はブラウザで組む。タブに戻ったときに引き直す。 */
export default function StoryTree() {
  const [source, setSource] = useState<Source | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [locations, stories, plots] = await Promise.all([
        listAllRecords("location", { sort: "id", order: "asc" }),
        listAllRecords("story", { sort: "id", order: "asc" }),
        listAllRecords("plot", { sort: "id", order: "asc" }),
      ]);
      setSource({ locations, stories, plots });
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

  const tree = useMemo(() => (source ? buildStoryTree(source.locations, source.stories, source.plots) : null), [source]);

  if (error) return <div className="status error">{error}</div>;
  if (!tree) return <div className="status info">{T.loading}</div>;
  if (tree.nodes.length === 0 && tree.unplaced.length === 0) return <div className="status info">{T.storyTree.noStories}</div>;

  return (
    <div className="panel">
      <ul className="tree tree-root">
        {tree.nodes.map((node) => (
          <PlaceNode key={node.id} node={node} />
        ))}
        {tree.unplaced.length > 0 && (
          <li className="tree-place">
            <details open>
              <summary>
                <span className="tree-name">{T.storyTree.noLocation}</span>
                <span className="tree-count">{T.storyTree.stories(tree.unplaced.length)}</span>
              </summary>
              <ul className="tree">
                {tree.unplaced.map((story) => (
                  <StoryRow key={story.id} story={story} />
                ))}
              </ul>
            </details>
          </li>
        )}
      </ul>
    </div>
  );
}
