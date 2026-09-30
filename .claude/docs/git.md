# git 運用

進め方は場所で違う。

- 手元(`CLAUDE_CODE_REMOTE` が `true` でない): コミット・push・merge・PR の作成・ブランチや worktree の作成は、ユーザに頼まれたときだけ行う。
  作業を終えても自分からはしない(ユーザは VS Code タスク `git push` でコミット・push する)。
  今いるブランチで作業し、worktree は「worktree で作業して」と頼まれたときだけ切る
- web のセッション(`CLAUDE_CODE_REMOTE=true`): セッションの指示(作業するブランチ・コミット・push・PR の作成)に従う。
  GitHub の操作は `gh` ではなく GitHub の MCP のツールで行う

どちらでも守ること:

- このリポジトリは公開なので、コミットの前に `.claude/docs/aws.md` の「core は公開リポジトリ」の grep で、
  構築の値(アカウント ID・リソースの ID・エンドポイント・関数 URL・合言葉)が紛れていないか確かめる
- 作品の中身(話・人物・設定)は db(RDS)にだけ置く。リポジトリには入れない
