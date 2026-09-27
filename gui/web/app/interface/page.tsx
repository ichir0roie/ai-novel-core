"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { getEntrances, getJobs, runEntrance, type EntranceList, type EntranceMeta, type JobInfo, type Rec } from "@/lib/api";

const AREA_LABEL: Record<string, string> = {
  world: "世界を読む", story: "作品・話", randomizer: "足す・直す・消す", idea: "アイデアの中間段",
  meme: "ミーム", review: "レビュー", fact_check: "検証", time_keeper: "常駐ループ(claude)",
};

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
      <h2 style={{ display: "flex", gap: "0.5rem", alignItems: "baseline", flexWrap: "wrap" }}>
        <code>{entrance.id}</code>
        {entrance.claude && <span className="chip">claude</span>}
        {entrance.writes && <span className="chip">db に書く</span>}
      </h2>
      {entrance.doc && <p className="hint">{entrance.doc}</p>}
      {blocked && <div className="status error">claude コマンドを叩く入口は、Claude Code の環境(CLAUDECODE=1)で起こした API でだけ実行できる</div>}
      {entrance.params.length > 0 && (
        <div className="form">
          {entrance.params.map((param) => (
            <div key={param.name} className="field">
              <label>
                {param.name}
                {param.required && <span className="hint">必須</span>}
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
          {busy ? "実行中…" : "実行"}
        </button>
        {!entrance.claude && (
          <label className="check">
            <input type="checkbox" checked={background} onChange={(e) => setBackground(e.target.checked)} /> 裏で走らせる
          </label>
        )}
        <span className="hint">辞書・配列は JSON で書く(例: {`{"id": 3, "kind": "概念"}`} / [1, 2])</span>
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
      <h1>入口を呼ぶ</h1>
      {error && <div className="status error">{error}</div>}
      {catalog && !catalog.claude_available && (
        <div className="status info">この API は Claude Code の外で起きているので、claude を叩く入口(常駐ループ・確定後に AI を回す入口)は実行できない</div>
      )}
      <div className="toolbar">
        <input type="search" placeholder="入口を探す" value={filter} onChange={(e) => setFilter(e.target.value)} />
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "minmax(240px, 320px) 1fr", gap: "1rem" }}>
        <div>
          {[...groups.entries()].map(([area, entrances]) => (
            <div key={area} style={{ marginBottom: "0.75rem" }}>
              <div className="hint" style={{ fontWeight: 600 }}>
                {AREA_LABEL[area] ?? area}
              </div>
              {entrances.map((entrance) => (
                <div key={entrance.id}>
                  <button className={`ghost ${selected === entrance.id ? "primary" : ""}`} style={{ width: "100%", textAlign: "left", padding: "0.2rem 0.5rem" }} onClick={() => setSelected(entrance.id)}>
                    {entrance.name}
                    {entrance.claude ? " ✦" : ""}
                  </button>
                </div>
              ))}
            </div>
          ))}
        </div>
        <div>
          {current ? <Runner entrance={current} claudeAvailable={catalog?.claude_available ?? false} onJob={loadJobs} /> : <div className="status info">左から入口を選ぶ</div>}
          <h2>裏で走らせた job</h2>
          {jobs.length === 0 ? (
            <div className="hint">まだ無い</div>
          ) : (
            <table className="list">
              <thead>
                <tr>
                  <th>状態</th>
                  <th>入口</th>
                  <th>引数</th>
                  <th>結果 / エラー</th>
                  <th>時刻</th>
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
          )}
        </div>
      </div>
    </>
  );
}
