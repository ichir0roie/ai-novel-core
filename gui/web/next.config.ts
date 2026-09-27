import type { NextConfig } from "next";

// API(FastAPI)の場所。`/api/*` をそのまま流すので、ブラウザから見ると同じオリジンになる
const apiUrl = process.env.NOVEL_API_URL ?? "http://127.0.0.1:8765";

const nextConfig: NextConfig = {
  // dev 起動のたびに AGENTS.md / CLAUDE.md を生やさない
  agentRules: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }];
  },
};

export default nextConfig;
