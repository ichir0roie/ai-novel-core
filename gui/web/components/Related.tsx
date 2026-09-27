import Link from "next/link";

type Appearance = { table: string; id: number; label: string; synced?: boolean; letters?: number };
type Place = { location_id: number; location: string | null; start: string | null; end: string | null };

export default function Related({ related }: { related: Record<string, unknown> }) {
  const appearances = related.appearances as Appearance[] | undefined;
  const plots = related.plots as Appearance[] | undefined;
  const places = related.places as Place[] | undefined;
  if (!appearances?.length && !plots?.length && !places?.length) return null;
  return (
    <div className="panel related">
      {appearances && (
        <>
          <h2>出てきた所</h2>
          {appearances.length === 0 ? (
            <span className="hint">(結んだ本文なし)</span>
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
      {plots && (
        <>
          <h2>話</h2>
          <ul>
            {plots.map((p) => (
              <li key={p.id}>
                <Link href={`/tables/plot/${p.id}`}>{p.label || `id=${p.id}`}</Link>
                <span className="hint">
                  {" "}
                  {p.letters ?? 0} 字{p.synced ? "" : " / 未同期"}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
      {places && (
        <>
          <h2>出自・居場所</h2>
          <ul>
            {places.map((p, i) => (
              <li key={i}>
                <Link href={`/tables/location/${p.location_id}`}>{p.location ?? p.location_id}</Link>
                <span className="hint">
                  {" "}
                  {p.start ?? "…"} 〜 {p.end ?? "…"}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
