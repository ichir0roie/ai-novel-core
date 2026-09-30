import type { NextRequest } from "next/server";

// ブラウザは同じオリジンの `/api/*` を叩き、ここがサーバー側で API(FastAPI)へ流す。
// 公開の API(Lambda の関数 URL)に置くときの合言葉 `NOVEL_API_KEY` はここでだけ足し、ブラウザには渡さない
const apiUrl = (process.env.NOVEL_API_URL ?? "http://127.0.0.1:8765").replace(/\/+$/, "");
const apiKey = process.env.NOVEL_API_KEY ?? "";

const REQUEST_HEADERS = ["content-type", "accept"];
const RESPONSE_HEADERS = ["content-type", "cache-control", "location"];

export const dynamic = "force-dynamic";

async function forward(request: NextRequest, context: { params: Promise<{ path: string[] }> }): Promise<Response> {
  const { path } = await context.params;
  const target = `${apiUrl}/api/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`;
  const headers = new Headers();
  for (const name of REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  if (apiKey) headers.set("x-novel-api-key", apiKey);
  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
      cache: "no-store",
      redirect: "manual",
    });
  } catch (e) {
    const detail = `API(${apiUrl})に届かない: ${e instanceof Error ? e.message : String(e)}`;
    return Response.json({ detail }, { status: 502 });
  }
  const responseHeaders = new Headers();
  for (const name of RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
}

export { forward as GET, forward as POST, forward as PATCH, forward as PUT, forward as DELETE };
