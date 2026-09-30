import { createHash, timingSafeEqual } from "node:crypto";
import { Sha256 } from "@aws-crypto/sha256-js";
import { createServerRunner } from "@aws-amplify/adapter-nextjs";
import { defaultProvider } from "@aws-sdk/credential-provider-node";
import { SignatureV4 } from "@smithy/signature-v4";
import { fetchAuthSession } from "aws-amplify/auth/server";
import { cookies } from "next/headers";
import type { NextRequest } from "next/server";
import { amplifyConfig, loginRequired } from "@/lib/auth";
import { T } from "@/lib/text";

// ブラウザは同じオリジンの `/api/*` を叩き、ここがサーバー側で API(FastAPI)へ流す。
// 公開の API(Lambda の関数 URL)に置くときの合言葉 `NOVEL_API_KEY` はここでだけ足し、ブラウザには渡さない
const apiUrl = (process.env.NOVEL_API_URL ?? "http://127.0.0.1:8765").replace(/\/+$/, "");
const apiKey = process.env.NOVEL_API_KEY ?? "";
// web のセッションは Cognito に入らず、web 用の合言葉だけで `/api/*` を叩く。Lambda の `NOVEL_API_KEYS` の `web=` と同じ値
const webApiKey = process.env.NOVEL_WEB_API_KEY ?? "";
const API_KEY_HEADER = "x-novel-api-key";

// クッキーのトークンは、adapter-nextjs が Cognito の公開鍵で署名を確かめてから読む
const { runWithAmplifyServerContext } = createServerRunner({ config: amplifyConfig });

const REQUEST_HEADERS = ["content-type", "accept"];
const RESPONSE_HEADERS = ["content-type", "cache-control", "location"];

// Lambda の関数 URL は認証が AWS_IAM なので、Amplify の SSR のコンピュートロールで SigV4 の署名を付ける。手元の API には付けない
const lambdaUrlRegion = /\.lambda-url\.([a-z0-9-]+)\.on\.aws$/.exec(new URL(apiUrl).hostname)?.[1];
const signer = lambdaUrlRegion
  ? new SignatureV4({ service: "lambda", region: lambdaUrlRegion, credentials: defaultProvider(), sha256: Sha256, applyChecksum: true })
  : null;

export const dynamic = "force-dynamic";

// 長さや先頭の一致で比べる時間が変わらないよう、ハッシュを取って同じ長さにしてから比べる
function sameSecret(presented: string, expected: string): boolean {
  const digest = (value: string) => createHash("sha256").update(value).digest();
  return expected !== "" && timingSafeEqual(digest(presented), digest(expected));
}

async function signedIn(): Promise<boolean> {
  try {
    return await runWithAmplifyServerContext({
      nextServerContext: { cookies },
      operation: async (context) => (await fetchAuthSession(context)).tokens?.accessToken !== undefined,
    });
  } catch {
    return false;
  }
}

/** 要求を出したのが誰か。画面(Cognito に入ったブラウザ)なら "gui"、web のセッション(合言葉)なら "web"、どちらでもなければ null */
async function authorize(request: NextRequest): Promise<"gui" | "web" | null> {
  const presentedKey = request.headers.get(API_KEY_HEADER);
  if (!loginRequired) return presentedKey ? "web" : "gui";
  if (presentedKey) return sameSecret(presentedKey, webApiKey) ? "web" : null;
  return (await signedIn()) ? "gui" : null;
}

// 署名は問い合わせを RFC 3986 で符号化し直した形で計算するので、送る方も同じ形に揃える(`+` と `%20` の食い違いで署名が外れる)
function encodeQuery(params: URLSearchParams): string {
  const rfc3986 = (value: string) => encodeURIComponent(value).replace(/[!'()*]/g, (c) => `%${c.charCodeAt(0).toString(16).toUpperCase()}`);
  const pairs = [...params].map(([key, value]) => `${rfc3986(key)}=${rfc3986(value)}`);
  return pairs.length ? `?${pairs.join("&")}` : "";
}

async function sign(target: URL, method: string, headers: Headers, body: Uint8Array | undefined): Promise<Headers> {
  if (!signer) return headers;
  const query: Record<string, string[]> = {};
  for (const [key, value] of target.searchParams) (query[key] ??= []).push(value);
  const signed = await signer.sign({
    method,
    protocol: target.protocol,
    hostname: target.hostname,
    path: target.pathname,
    query,
    headers: { ...Object.fromEntries(headers), host: target.hostname },
    body,
  });
  // host は fetch が URL から付ける
  return new Headers(Object.entries(signed.headers).filter(([name]) => name.toLowerCase() !== "host"));
}

async function forward(request: NextRequest, context: { params: Promise<{ path: string[] }> }): Promise<Response> {
  const caller = await authorize(request);
  if (!caller) return Response.json({ detail: T.signInRequired }, { status: 401 });
  const { path } = await context.params;
  const target = new URL(`${apiUrl}/api/${path.map(encodeURIComponent).join("/")}`);
  target.search = encodeQuery(request.nextUrl.searchParams);
  const headers = new Headers();
  for (const name of REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  // web のセッションは自分の合言葉(web)を付けてくる。API が呼ぶ側を見分けられるよう、それはそのまま流す
  const callerKey = caller === "web" ? request.headers.get(API_KEY_HEADER) : apiKey;
  if (callerKey) headers.set(API_KEY_HEADER, callerKey);
  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  const body = hasBody ? new Uint8Array(await request.arrayBuffer()) : undefined;
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers: await sign(target, request.method, headers, body),
      body,
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
