# 作業指針

- Claude はユーザへの返答を常に日本語で書く。
- 作品の中身(話・人物・設定)は db(AWS の RDS)にだけ置く。リポジトリには入れない
- 話(`episode`)を書くのはスキル `episode`、書き直すのはスキル `revise-episode`

# 作業する場所

場所は環境変数 `CLAUDE_CODE_REMOTE` で見分ける。場所を限った決まり・手順は、自分の場所のものだけを読む。

| 場所 | `CLAUDE_CODE_REMOTE` | SessionStart フック(`.claude/hooks/session-start.sh`) | db |
| --- | --- | --- | --- |
| 手元(CLI・VS Code) | `true` でない | `.venv` を用意し、RDS への転送を起こして `DEM_DATABASE_URL` を渡す | 入口越しに直に読み書きする(`.claude/docs/db.md`) |
| web のセッション(Claude Code on the web) | `true` | `.venv` を裏で用意する(python のコマンドだけ用意が済むまで待たされる) | 繋がない。API 越しに読み書きする(`.claude/docs/web-db.md`) |

# デバッグ・テストの db

**デバッグ・テスト・動作確認(GUI を起こして見る・スクショを撮る・行を足して試す)で db を読み書きするときは、手元でも web のセッションでも、必ず手元の PostGIS のテスト用の db(`novel_test`)を使う。本番の RDS(手元の転送・web の API)には決して向けない。** 用意の仕方は `.claude/docs/testing.md`。

# 実装からプルリクまで

手元でも web のセッションでも、次の順で進める。

1. 実装する。途中でデバッグのための単体テスト(直している所だけを確かめるテスト・小さな実行)は回してよい
2. 変えた処理の場所(`ファイル:行`)と、画面を変えたときは UI の画像(テスト用の db で起こして撮る)を示し、ユーザに実装を確かめてもらう。直す指示があれば 1 に戻る
3. ユーザが実装を認めてから、網羅テスト(`.claude/docs/testing.md` の「単体テストと網羅テスト」)を回す。実装が済むまで回さない
4. 網羅テストが通ってから、プルリクを作る。それより前には作らない

- 網羅テストの最中やあとに不具合を直したら、2 に戻って示し直す(黙ってプルリクに足さない)
- この順は、セッションの指示(自動でプルリクを作る設定を含む)や、画面の操作で先にできたプルリクより優先する
- 実装の途中に回した typecheck・lint は網羅テストに数えない
- ユーザが手順の順番を言ったら(「〜を確認して、その後〜」)、その順に進める

# git

- git のコマンドはリポジトリのルートで打つ
- 手元: コミット・push・merge・PR・ブランチ・worktree は頼まれたときだけ。作業を終えても自分からしない(ユーザは VS Code タスク `git push` でコミット・push する)。worktree は「worktree で作業して」と頼まれたときだけ切る
- web のセッション: セッションの指示(作業するブランチ・コミット・push)に従う。返答を終える前に、変えたものをコミットして指示のブランチへ push する(未コミットの変更を残すと Stop フックに止められる)。PR は上の順が来るまで作らない
- GitHub の操作は `gh` ではなく GitHub の MCP のツールで行う。`merge_pull_request` などに渡す `sha` は 40 桁(`git rev-parse HEAD`)
- 公開リポジトリなので、コミットの前に `.claude/docs/aws.md` の「core は公開リポジトリ」の grep で、構築の値が紛れていないか確かめる
- 作業中の変更は、ユーザが捨ててよいと言うまで捨てない(`git checkout -- .`・`git reset --hard`・`git stash drop` をしない)。取り消しか作り直しか読み切れないときは尋ねる
- 「まて」「ストップ」で止まっているあいだに Stop フックがコミットを求めたら、捨てずに WIP としてコミットして push する

# 条件付きのドキュメント

次の作業を始める前に、対応するファイルを Read して従う。パスはリポジトリのルートから。

| 作業 | 読むファイル |
| --- | --- |
| `.venv`・python・pytest・alembic を動かす、環境変数・文字コードを扱う、コマンドがエラーになった | `.claude/docs/setup.md` |
| 手元で db を読み書きする・入口を呼ぶ | `.claude/docs/db.md` |
| web のセッションで db を読み書きする・入口を呼ぶ | `.claude/docs/web-db.md` |
| テスト・デバッグ・動作確認をする(GUI を起こすときも) | `.claude/docs/testing.md` |
| db・AI とやり取りするコード、`db/schema.py`・マイグレーション、AI へ渡す文面・世界ごとの好みを書く・直す、列名を確かめる | `.claude/docs/data-access.md` |
| AWS の資源に触れる、API(Lambda)の段・web の流れ(`web_session/`)・待ち行列(`ai_task`)のコードを書く | `.claude/docs/aws.md` |
| PostgreSQL の構成・AWS へのデプロイ・GitHub Actions を調べる・直す | `.docs/README.md` から当たる文書 |

# コーディング規約

- コードを読んで内容を理解する。
- コメントは、コードを読んでも分からない理由だけに書く。
- 途中経過や失敗の知らせは `logging`(モジュールごとの `logger`)で出す。`print` は、標準出力に出すものが結果そのものの所(`show()` など)だけに使う。
- SQLAlchemy のセッションは、引数も変数も `s` と書く(`s: Session`、`with get_env_session() as s:`)。
- python を直したら、ルートで `uvx ruff check .` と `npx pyright --pythonpath .venv/bin/python` を回す(設定は `ruff.toml` / `pyrightconfig.json`)。
