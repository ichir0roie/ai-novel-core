# 作業指針

- Claude はユーザへの返答を常に日本語で書く。
- 作品の中身(話・人物・設定)は db(AWS の RDS)にだけ置く。リポジトリには入れない
- 次の合図で、対応するスキルを使う(何をするかはスキルに書いてある)

| 合図 | スキル |
| --- | --- |
| 「ep<話id>」(Claude が語り部のセミオート)・「ep<話id> 書いた」(ユーザが書いた本文を反映) | `episode` |
| 「ep<話id> in」(ユーザが作者として書き、語り部と人物役が続ける) | `interactive-episode` |
| すでに本文のある話を直す | `revise-episode` |
| 「<人物名>を呼んで」・「<歳>の<人物名>を呼んで」 | `call-character` |
| 「st<作品id>」(本文は書かずに作品全体を整える) | `story-director` |
| 「自動推敲」(直した時刻の古い話から、5 時間ごとの使用量が切れる前まで推敲し続ける) | `auto-revision` |

# 作業する場所

場所は環境変数 `CLAUDE_CODE_REMOTE` で見分ける。場所を限った決まり・手順は、自分の場所のものだけを読む。

| 場所 | `CLAUDE_CODE_REMOTE` | SessionStart フック(`.claude/hooks/session-start.sh`) | db |
| --- | --- | --- | --- |
| 手元(CLI・VS Code) | `true` でない | `.venv` を用意し、RDS への転送を起こして `DEM_DATABASE_URL` を渡す | 入口越しに直に読み書きする(`.claude/docs/db.md`) |
| web のセッション(Claude Code on the web) | `true` | `.venv` を裏で用意する(python のコマンドだけ用意が済むまで待たされる) | 繋がない。API 越しに読み書きする(`.claude/docs/web-db.md`) |

# ツールの使い分け

長い Bash の結果は、Claude Code が頭だけを見せて残りをファイルに逃がす。見えた頭だけで読んだつもりになると、残りを読み落とす(人物役が、知り合いを知らない人として演じた)。

- ファイルを読むのは Read、直すのは Edit、新しく書くのは Write。Bash の `cat`・`sed`・`head`・`tail` で読まない。python・`sed` の置換で書き換えない
- 文字列を探すのは Grep ツール。そのセッションに無ければ Bash の `grep` で、`-n`・`-c`・`cut` などで出力を短く絞る
- 入口・API・コマンドの結果のうち、長くなりうるもの(人物・話の一覧・材料・本文)は、Bash の出力のまま読まない。スクラッチパッドのファイルへ書き出してから、Read(長ければ `allow_large: true`)で最後の行まで読む。Read が途中で止まった(PARTIAL)なら、示された `offset` から続きを読む
  - 要る所だけを `jq` で抜くときは、ファイルに書き出さずに出力をそのまま読んでよい(抜いた結果が短いとき)
  - 日本語の見出しの JSON(`ReadEpisodeCasting`・`ReadEpisodeBrief` など)は、jq で組み立てずに、書き出したファイルを Read で読む。jq で抜くのは、`.["見出し"]` の形で数個の値を抜くときだけにする(`.登場人物` や `{名前, 年齢}` の省略形は落ちる。`.claude/docs/setup.md` の「jq」)。抜いた値を並べ替える・組み合わせるときは、jq でなく `python -I -c` で `json` を読んで組む
- コマンドへ渡す JSON(手番・語の配列など)と、本文・プロットのような長い文は、Write でスクラッチパッドのファイルに書き、そのパスを渡す(ヒアドキュメントで渡さない。中身に区切りの語があると途中で切れる)。一行で済む短い引数(人物役の一手の欄など)は、引数のまま渡してよい

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

# AWS の CLI と MCP

手元だけの決まり(web のセッションには AWS の認証情報を置かない)。

- 資源の状態を調べるのは AWS CLI で行い、`--profile` と `--region` を毎回明示する。資源を作る・変えるのは CLI でなく CDK(`.claude/docs/aws.md`)
- AWS の仕様・エラーを調べるのは aws-mcp のドキュメント検索(`search_documentation`・`read_documentation`)
- 全リージョンの棚卸しのように API を大量に呼ぶ読み取りは、aws-mcp の `run_script` でまとめて流す。aws-mcp のプロファイルは起動時に決まり呼び出しごとに変えられないので、先に対象のアカウントか(`sts` の `GetCallerIdentity`)を確かめる

# 条件付きのドキュメント

次の作業を始める前に、対応するファイルを Read して従う。パスはリポジトリのルートから。

| 作業 | 読むファイル |
| --- | --- |
| `.venv`・python・pytest・alembic を動かす、環境変数・文字コードを扱う、コマンドがエラーになった | `.claude/docs/setup.md` |
| 手元で db を読み書きする・入口を呼ぶ | `.claude/docs/db.md` |
| web のセッションで db を読み書きする・入口を呼ぶ | `.claude/docs/web-db.md` |
| テスト・デバッグ・動作確認をする(GUI を起こすときも) | `.claude/docs/testing.md` |
| db・AI とやり取りするコード、`db/schema.py`・マイグレーション、AI へ渡す文面・世界ごとの好みを書く・直す、列名を確かめる | `.claude/docs/data-access.md` |
| AWS の資源に触れる、API(Lambda)の段・流れ(`data_access_logic/flows/`)・web の口(`web_session/`)のコードを書く | `.claude/docs/aws.md` |
| PostgreSQL の構成・AWS へのデプロイ・GitHub Actions を調べる・直す | `.docs/README.md` から当たる文書 |

# コーディング規約

- コードを読んで内容を理解する。
- コメントは、コードを読んでも分からない理由だけに書く。
- 文書・コメントで version は「版」でなく「バージョン」と書く。
- 途中経過や失敗の知らせは `logging`(モジュールごとの `logger`)で出す。`print` は、標準出力に出すものが結果そのものの所(`show()` など)だけに使う。
- SQLAlchemy のセッションは、引数も変数も `s` と書く(`s: Session`、`with get_env_session() as s:`)。
- python を直したら、ルートで `uvx ruff check .` と `npx pyright --pythonpath .venv/bin/python` を回す(設定は `ruff.toml` / `pyrightconfig.json`)。
