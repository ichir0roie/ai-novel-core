import Link from "next/link";
import EpisodeContext from "@/components/EpisodeContext";
import { T } from "@/lib/text";

type Appearance = { table: string; id: number; label: string; synced?: boolean; letters?: number };

type Owner = { table: string; id: number | string };

type EpisodeCharactersProps = {
  characterIds: number[];
  onChangeCharacterIds: (ids: number[]) => void;
  episodeStart: unknown;
  episodeLocationId: unknown;
};

export default function Related({
  related, owner, characterIds, onChangeCharacterIds, episodeStart, episodeLocationId,
}: { related: Record<string, unknown>; owner?: Owner } & Partial<EpisodeCharactersProps>) {
  const appearances = related.appearances as Appearance[] | undefined;
  const episodes = related.episodes as Appearance[] | undefined;
  const context = related.context as Parameters<typeof EpisodeContext>[0]["context"] | undefined;
  const graph = owner?.table === "character" ? { href: `/relations?character=${owner.id}`, ...T.related.relationGraph }
    : owner?.table === "location" ? { href: `/maps?location=${owner.id}`, ...T.related.mapCentered }
    : null;
  const hasContext = context && Object.values(context).some((block) => block.items.length > 0);
  const showCharacters = characterIds !== undefined && onChangeCharacterIds !== undefined;
  if (!appearances?.length && !episodes && !graph && !hasContext && !showCharacters) return null;
  return (
    <>
      {(appearances || episodes || graph) && (
        <div className="panel related">
          {graph && (
            <Link href={graph.href} className="jump">
              <span className="jump-title">{graph.title}</span>
              <span className="jump-sub">{graph.sub}</span>
            </Link>
          )}
          {appearances && (
            <>
              <h2>{T.related.appearsIn}</h2>
              {appearances.length === 0 ? (
                <span className="hint">{T.related.noLinkedText}</span>
              ) : (
                <ul>
                  {appearances.map((a) => (
                    <li key={`${a.table}:${a.id}`}>
                      <Link href={`/tables/${a.table}/${a.id}`}>
                        {a.table}「{a.label}」(id={a.id})
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
          {episodes && owner?.table === "story" && (
            <Link href={`/tables/episode?story_id=${owner.id}`} className="jump">
              <span className="jump-title">{T.related.episodeList}</span>
              <span className="jump-sub">
                {T.related.episodeSummary(episodes.length, episodes.reduce((sum, p) => sum + (p.letters ?? 0), 0))}
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
