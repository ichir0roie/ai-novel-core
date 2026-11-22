"use client";

import Link from "next/link";
import { useState } from "react";
import EpisodeContext from "@/components/EpisodeContext";
import SkillsModal from "@/components/SkillsModal";
import type { EpisodeLink } from "@/components/StoryEpisodes";
import { T } from "@/lib/text";

/** label は見出しに出す名前(スキルのモーダルの題に使う) */
type Owner = { table: string; id: number | string; label?: string };

type EpisodeCharactersProps = {
  characterIds: number[];
  onChangeCharacterIds: (ids: number[]) => void;
  episodeStart: unknown;
  episodeStoryId: unknown;
};

export default function Related({
  related, owner, characterIds, onChangeCharacterIds, episodeStart, episodeStoryId,
}: { related: Record<string, unknown>; owner?: Owner } & Partial<EpisodeCharactersProps>) {
  const episodes = related.episodes as EpisodeLink[] | undefined;
  const context = related.context as Parameters<typeof EpisodeContext>[0]["context"] | undefined;
  // 詳細の場所は全体の地図に出ないので、親の詳細マップで選んだ形で開く
  const detailMapId = related.detail_map_id as number | null | undefined;
  const detailChildren = (related.detail_children as number | undefined) ?? 0;
  const graph = owner?.table === "character" ? { href: `/relations?character=${owner.id}`, ...T.related.relationGraph }
    : owner?.table === "location" && detailMapId != null
      ? { href: `/maps/detail?location=${detailMapId}&focus=${owner.id}`, ...T.related.detailMapHere }
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
        <div className="panel related jumps">
          {graph && <Link href={graph.href} className="button-link" title={graph.sub}>{graph.title}</Link>}
          {owner?.table === "location" && detailChildren > 0 && (
            <Link href={`/maps/detail?location=${owner.id}`} className="button-link" title={T.related.detailMap.sub}>
              {T.detailMap.detailMap(detailChildren)}
            </Link>
          )}
          {skills && (
            <button type="button" title={T.related.skills.sub} onClick={() => setSkillsOpen(true)}>{T.related.skills.title}</button>
          )}
          {owner?.table === "story" && (
            <Link href={`/timeline?story_id=${owner.id}&focus=story`} className="button-link" title={T.related.storyTimeline.sub}>
              {T.related.storyTimeline.title}
            </Link>
          )}
          {episodes && owner?.table === "story" && (
            <Link href={`/tables/episode?story_id=${owner.id}`} className="button-link">{T.related.episodeList}</Link>
          )}
          {episodes && owner?.table === "story" && (
            <span className="jumps-note">
              {T.related.episodeSummary(episodes.length, episodes.reduce((sum, p) => sum + p.letters, 0))}
            </span>
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
          episodeStoryId={episodeStoryId}
        />
      )}
    </>
  );
}
