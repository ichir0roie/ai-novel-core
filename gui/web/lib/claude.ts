// リポジトリ名・環境は構築ごとの値なので、コードに書かずビルドの環境変数(Amplify・.env.local)から取る
const repositories = process.env.NEXT_PUBLIC_NOVEL_CLAUDE_REPOSITORIES ?? "";
const environment = process.env.NEXT_PUBLIC_NOVEL_CLAUDE_ENVIRONMENT ?? "";

/** Claude Code on the web の新しいセッションの画面の URL。リポジトリ・環境・初めのメッセージを選んだ状態で開く。
 * 置ける値は https://code.claude.com/docs/en/web-quickstart の「Pre-fill sessions」。 */
export function claudeSessionUrl(prompt: string): string {
  // URLSearchParams は空白を + にするので、文書の例どおり %20 になる encodeURIComponent で組む
  const params: [string, string][] = [["prompt", prompt]];
  if (repositories) params.push(["repositories", repositories]);
  if (environment) params.push(["environment", environment]);
  return `https://claude.ai/code?${params.map(([key, value]) => `${key}=${encodeURIComponent(value)}`).join("&")}`;
}
