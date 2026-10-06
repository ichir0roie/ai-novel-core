"use client";

import Link from "next/link";
import { useState } from "react";
import EpisodeContext from "@/components/EpisodeContext";
import SkillsModal from "@/components/SkillsModal";
import { T } from "@/lib/text";

type EpisodeLink = { table: string; id: number; label: string; synced: boolean; letters: number };

/** label は見出しに出す名前(スキルのモーダルの題に使う) */
type Owner = { table: string; id: number | string; label?: string };

type EpisodeCharactersProps = {
  characterIds: number[];
  onChangeCharacterIds: (ids: number[]) => void;
  episodeStart: unknown;
  episodeLocationId: unknown;
  episodeStoryId: unknown;
};

export default function Related({
  related, owner, characterIds, onChangeCharacterIds, episodeStart, episodeLocationId, episodeStoryId,
}: { related: Record<string, unknown>; owner?: Owner } & Partial<EpisodeCharactersProps>) {
  const episodes = related.episodes as EpisodeLink[] | undefined;
  const context = related.context as Parameters<typeof EpisodeContext>[0]["context"] | undefined;
  const graph = owner?.table === "character" ? { href: `/relations?character=${owner.id}`, ...T.related.relationGraph }
    : owner?.table === "location" ? { href: `/maps?location=${owner.id}`, ...T.related.mapCentered }
    : owner?.table === "story" ? { href: `/maps?story=${owner.id}`, ...T.related.storyRoute }
    : owner?.table === "episode" && episodeStoryId != null
      ? { href: `/maps?story=${episodeStoryId}&episode=${owner.id}`, ...T.related.episodeRoute }
    : null;
  const [skillsOpen, setSkillsOpen] = useState(false);
  const skills = owner?.table === "character" ? owner : null;
  const hasContext = context && Object.values(context).some((block) => block.items.length > 0);
  const showCharacters = characterIds !== undefined && onChangeCharacterIds !== undefined;
  if (!episodes && !graph && !hasContext && !showCharacters) return null;
  return (
    <>
      {(episodes || graph) && (
        <div className="panel related">
          {graph && (
            <Link href={graph.href} className="jump">
              <span className="jump-title">{graph.title}</span>
              <span className="jump-sub">{graph.sub}</span>
            </Link>
          )}
          {skills && (
            <button type="button" className="jump" onClick={() => setSkillsOpen(true)}>
              <span className="jump-title">{T.related.skills.title}</span>
              <span className="jump-sub">{T.related.skills.sub}</span>
            </button>
          )}
          {owner?.table === "story" && (
            <Link href={`/timeline?story_id=${owner.id}&focus=story`} className="jump">
              <span className="jump-title">{T.related.storyTimeline.title}</span>
              <span className="jump-sub">{T.related.storyTimeline.sub}</span>
            </Link>
          )}
          {episodes && owner?.table === "story" && (
            <Link href={`/tables/episode?story_id=${owner.id}`} className="jump">
              <span className="jump-title">{T.related.episodeList}</span>
              <span className="jump-sub">
                {T.related.episodeSummary(episodes.length, episodes.reduce((sum, p) => sum + p.letters, 0))}
                {episodes.some((p) => !p.synced) ? T.related.unsynced(episodes.filter((p) => !p.synced).length) : ""}
              </span>
            </Link>
          )}
        </div>
      )}
      {skills && skillsOpen && (
        <SkillsModal characterId={Number(skills.id)} characterName={skills.label ?? T.idMark(skills.id)} onClose={() => setSkillsOpen(false)} />
      )}
      {(hasContext || showCharacters) && (
        <EpisodeContext
          context={context ?? {}}
          characterIds={characterIds}
          onChangeCharacterIds={onChangeCharacterIds}
          episodeStart={episodeStart}
          episodeLocationId={episodeLocationId}
        />
      )}
    </>
  );
}
