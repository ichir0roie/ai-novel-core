import type { NextConfig } from "next";

// `/api/*` は `app/api/[...path]/route.ts` が API(FastAPI、`NOVEL_API_URL`)へ流す
const nextConfig: NextConfig = {
  // next dev はビルド先ごとに 1 つしか動かせないので、テストで起こすときは別のビルド先(`.next-test`)を渡す
  distDir: process.env.NOVEL_WEB_DIST_DIR ?? ".next",
  // dev 起動のたびに AGENTS.md / CLAUDE.md を生やさない
  agentRules: false,
};

export default nextConfig;
