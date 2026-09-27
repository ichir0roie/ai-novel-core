import Link from "next/link";
import { T } from "@/lib/text";

type Appearance = { table: string; id: number; label: string; synced?: boolean; letters?: number };

type Owner = { table: string; id: number | string };

export default function Related({ related, owner }: { related: Record<string, unknown>; owner?: Owner }) {
  const appearances = related.appearances as Appearance[] | undefined;
  const plots = related.plots as Appearance[] | undefined;
  const graph = owner?.table === "character" ? { href: `/relations?character=${owner.id}`, ...T.related.relationGraph }
    : owner?.table === "location" ? { href: `/maps?location=${owner.id}`, ...T.related.mapCentered }
    : null;
  if (!appearances?.length && !plots && !graph) return null;
  return (
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
      {plots && owner?.table === "story" && (
        <Link href={`/tables/plot?story_id=${owner.id}`} className="jump">
          <span className="jump-title">{T.related.plotList}</span>
          <span className="jump-sub">
            {T.related.plotSummary(plots.length, plots.reduce((sum, p) => sum + (p.letters ?? 0), 0))}
            {plots.some((p) => !p.synced) ? T.related.unsynced(plots.filter((p) => !p.synced).length) : ""}
          </span>
        </Link>
      )}
    </div>
  );
}
