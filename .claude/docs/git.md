# git 運用

- 手元(`CLAUDE_CODE_REMOTE` が `true` でない):
  - コミット・push・merge・PR の作成・ブランチや worktree の作成は、ユーザに頼まれたときだけ。作業を終えても自分からしない(ユーザは VS Code タスク `git push` でコミット・push する)
  - 今いるブランチで作業する。worktree は「worktree で作業して」と頼まれたときだけ切る
- web のセッション(`CLAUDE_CODE_REMOTE=true`):
  - セッションの指示(作業するブランチ・コミット・push)に従う
  - 返答を終える前に、変えたものをコミットして指示のブランチへ push する(未コミットの変更を残すと Stop フックに止められる)
  - PR は `CLAUDE.md` の「実装からプルリクまで」の順が来るまで作らない
  - GitHub の操作は `gh` ではなく GitHub の MCP のツールで行う。`merge_pull_request` などに渡す `sha` は 40 桁(`git rev-parse HEAD` で取る)
- どちらでも:
  - 公開リポジトリなので、コミットの前に `.claude/docs/aws.md` の「core は公開リポジトリ」の grep で、構築の値が紛れていないか確かめる
  - 作業中の変更は、ユーザが捨ててよいと言うまで捨てない(`git checkout -- .`・`git reset --hard`・`git stash drop` をしない)
  - 指示が取り消しか作り直しか読み切れないときは、捨てる前に尋ねる
  - 「まて」「ストップ」で止まっているあいだに Stop フックがコミットを求めたら、捨てずに WIP としてコミットして push する
