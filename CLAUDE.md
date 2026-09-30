# 作業指針

Claude はユーザへの返答を常に日本語で書く。

Claude Code では `.claude/hooks/session-start.sh`(SessionStart フック)が、`.venv` の用意、開発用の PostgreSQL の用意、
手元では RDS への転送の起動と環境変数の設定を行う。作品の中身は db(AWS の RDS)にだけあり、このリポジトリには無い。
プロット・時刻・登場人物を決めた話(プロットと本文をまとめて持つ `episode`)はスキル `episode` の手順で回す。

# 条件付きのドキュメント

次の表の条件に当てはまる作業をするときは、始める前に対応するファイルを Read し、それに従う。
当てはまらなければ読まなくてよい。パスはリポジトリのルートから書いてある。

| 条件 | 読むファイル |
| --- | --- |
| コマンドの実行でエラーが出たとき | `.claude/docs/command-errors.md` |
| AI へ渡す文面・生成関数を足す・直すとき、世界ごとの好み(舞台設定・文体の癖)を足す・直す・渡すとき、スキルから生成関数を呼ぶとき | `.claude/docs/user-preferences.md` |
| ファイルを読み書きするコードを書くとき、日本語を出すコマンドを打つとき | `.claude/docs/encoding.md` |
| リポジトリの構成・環境変数を扱うとき、python・pytest・alembic を動かすとき、`.venv` を用意するとき | `.claude/docs/setup.md` |
| git でコミット・push・merge・ブランチ操作をするとき、worktree で作業してと頼まれたとき | `.claude/docs/git.md` |
| db を読み書きするとき(入口の呼び出し・作成、マイグレーションの確認、他のセッションとの同時作業を含む) | `.claude/docs/db.md` |
| テストをしてと明確に依頼されたとき | `.claude/docs/testing.md` |
| テスト・動作確認で GUI(API・画面)を動かすとき | `.claude/docs/gui.md` |
| ミームを扱うとき、本文・人物の `text` を書くとき | `.claude/docs/meme.md` |
| 列名・型を確かめるとき、`db/schema.py` やマイグレーションを変えるとき | `.claude/docs/schema.md` |
| db を読む処理・AI とやり取りする処理(pydantic のマテリアル・出力モデル)を書く・直すとき、リファクタするとき | `.claude/docs/data-access.md` |
| PostgreSQL(`DEM_DATABASE_URL`)・AWS へのデプロイ・GitHub Actions・AI の待ち行列(`ai_task`)と web のセッションで回す仕組み(`web_session/`・`steps.py`)を扱うとき | `.docs/README.md` から当たる文書 |
| AWS の db・資源に触れるとき、Claude Code on the web(`CLAUDE_CODE_REMOTE=true`)で db が要る作業をするとき | `.claude/docs/aws.md` |

# コーディング規約

コードを読んで内容を理解すること。
コードを読んでも分からない理由のみコメントにする。
途中経過や失敗の知らせは `logging`(モジュールごとの `logger`)で出す。`print` は `show()` のように、標準出力に出すものが結果そのものの所だけに使う。
SQLAlchemy のセッションは、引数も変数も `s` と書く(`s: Session`、`with get_env_session() as s:`)。
python を直したら、ルートで `uvx ruff check .` と `npx pyright --pythonpath .venv/bin/python` を回す(設定は `ruff.toml` / `pyrightconfig.json`)。
