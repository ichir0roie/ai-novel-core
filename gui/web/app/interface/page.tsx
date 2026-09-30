"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { getEntrances, getJobs, runEntrance, type EntranceList, type EntranceMeta, type JobInfo, type Rec } from "@/lib/api";
import { PageTitle } from "@/lib/meta";
import { T } from "@/lib/text";

/** 引数の欄。JSON として読めればその値、読めなければ文字列のまま渡す。 */
function parseArg(text: string): unknown {
  const trimmed = text.trim();
  if (trimmed === "") return undefined;
  try {
    return JSON.parse(trimmed);
  } catch {
    return text;
  }
}

function Runner({ entrance, claudeAvailable, onJob }: { entrance: EntranceMeta; claudeAvailable: boolean; onJob: () => void }) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [background, setBackground] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);
  const blocked = entrance.claude && !claudeAvailable;

  const run = async () => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const args: Rec = {};
      for (const [key, text] of Object.entries(values)) {
        const value = parseArg(text);
        if (value !== undefined) args[key] = value;
      }
      const response = await runEntrance(entrance.id, args, background);
      setResult(response);
      if ("status" in response) onJob();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel">
      <h2 title={entrance.doc || undefined} style={{ display: "flex", gap: "0.5rem", alignItems: "baseline", flexWrap: "wrap" }}>
        <code>{entrance.id}</code>
        {entrance.claude && <span className="chip">claude</span>}
        {entrance.writes && <span className="chip">{T.endpoints.writesDb}</span>}
      </h2>
      {blocked && <div className="status error">{T.endpoints.claudeOnly}</div>}
      {entrance.params.length > 0 && (
        <div className="form">
          {entrance.params.map((param) => (
            <div key={param.name} className="field">
              <label>
                {param.name}
                {param.required && <span className="hint">{T.required}</span>}
                {param.annotation && <span className="key">{param.annotation}</span>}
              </label>
              <input
                type="text"
                placeholder={param.default === null ? "" : JSON.stringify(param.default)}
                value={values[param.name] ?? ""}
                onChange={(e) => setValues({ ...values, [param.name]: e.target.value })}
              />
            </div>
          ))}
        </div>
      )}
      <div style={{ display: "flex", gap: "0.6rem", alignItems: "center", marginTop: "0.75rem" }}>
        <button className="primary" onClick={run} disabled={busy || blocked}>
          {busy ? T.endpoints.running : T.endpoints.run}
        </button>
        {!entrance.claude && (
          <label className="check">
            <input type="checkbox" checked={background} onChange={(e) => setBackground(e.target.checked)} /> {T.endpoints.runInBackground}
          </label>
        )}
        <span className="hint">{T.endpoints.jsonHint}</span>
      </div>
      {error && <div className="status error">{error}</div>}
      {result !== null && (
        <pre className="mono" style={{ whiteSpace: "pre-wrap", fontSize: "0.85rem", marginTop: "0.5rem" }}>
          {JSON.stringify(result, null, 2)}
        </pre>
      )}
    </div>
  );
}

export default function InterfacePage() {
  const [catalog, setCatalog] = useState<EntranceList | null>(null);
  const [jobs, setJobs] = useState<JobInfo[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);

  const loadJobs = useCallback(() => {
    getJobs().then((r) => setJobs(r.jobs)).catch(() => undefined);
  }, []);

  useEffect(() => {
    getEntrances().then(setCatalog).catch((e) => setError(e.message));
    loadJobs();
  }, [loadJobs]);

  const active = jobs.some((job) => job.status === "queued" || job.status === "running");
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(loadJobs, 2000);
    return () => clearInterval(timer);
  }, [active, loadJobs]);

  const groups = useMemo(() => {
    const q = filter.trim();
    const map = new Map<string, EntranceMeta[]>();
    for (const entrance of catalog?.entrances ?? []) {
      if (q && !entrance.id.includes(q) && !entrance.doc.includes(q)) continue;
      map.set(entrance.area, [...(map.get(entrance.area) ?? []), entrance]);
    }
    return map;
  }, [catalog, filter]);
  const current = catalog?.entrances.find((entrance) => entrance.id === selected) ?? null;

  return (
    <>
      <PageTitle kind={T.endpoints.title} />
      <h1>{T.endpoints.title}</h1>
      {error && <div className="status error">{error}</div>}
      {catalog && !catalog.claude_available && (
        <div className="status info">{T.endpoints.outsideClaude}</div>
      )}
      {catalog?.claude_mode === "queue" && <div className="status info">{T.endpoints.queueMode}</div>}
      <div className="toolbar">
        <input type="search" placeholder={T.endpoints.searchPlaceholder} value={filter} onChange={(e) => setFilter(e.target.value)} />
      </div>
      <div className="endpoints">
        <div>
          {[...groups.entries()].map(([area, entrances]) => (
            <div key={area} className="area">
              <div className="hint">
                {T.endpoints.area[area] ?? area}
              </div>
              {entrances.map((entrance) => (
                <div key={entrance.id}>
                  <button className={`ghost ${selected === entrance.id ? "primary" : ""}`} onClick={() => setSelected(entrance.id)}>
                    {entrance.name}
                    {entrance.claude ? " ✦" : ""}
                  </button>
                </div>
              ))}
            </div>
          ))}
        </div>
        <div>
          {current ? <Runner entrance={current} claudeAvailable={catalog?.claude_available ?? false} onJob={loadJobs} /> : <div className="status info">{T.endpoints.selectOne}</div>}
          <h2>{T.endpoints.jobs}</h2>
          {jobs.length === 0 ? (
            <div className="hint">{T.endpoints.noJobs}</div>
          ) : (
            <div className="scroll-x">
              <table className="list">
                <thead>
                  <tr>
                    <th>{T.endpoints.columns.status}</th>
                    <th>{T.endpoints.columns.entrance}</th>
                    <th>{T.endpoints.columns.args}</th>
                    <th>{T.endpoints.columns.result}</th>
                    <th>{T.endpoints.columns.time}</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((job) => (
                    <tr key={job.id}>
                      <td>{job.status}</td>
                      <td>
                        <code>{job.entrance}</code>
                      </td>
                      <td className="preview">{JSON.stringify(job.args)}</td>
                      <td className="preview" title={job.error ?? JSON.stringify(job.result)}>
                        {job.error ?? (job.result === null ? "" : JSON.stringify(job.result))}
                      </td>
                      <td className="hint">{job.finished_at ?? job.started_at ?? job.created_at}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
