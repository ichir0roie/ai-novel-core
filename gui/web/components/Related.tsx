import Link from "next/link";
import EpisodeContext from "@/components/EpisodeContext";
import { T } from "@/lib/text";

type EpisodeLink = { table: string; id: number; label: string; synced: boolean; letters: number };

type Owner = { table: string; id: number | string };

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
  const skills = owner?.table === "character" ? { href: `/tables/character_skill?character_id=${owner.id}`, ...T.related.skills } : null;
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
            <Link href={skills.href} className="jump">
              <span className="jump-title">{skills.title}</span>
              <span className="jump-sub">{skills.sub}</span>
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
