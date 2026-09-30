# 条件付きのドキュメント

次の表の条件に当てはまる作業をするときは、始める前に対応するファイルを Read し、それに従う。
当てはまらなければ読まなくてよい。パスは core リポジトリのルートから書いてある。世界リポジトリから
作業しているときは、前に `core/` を付ける(例: `core/.claude/docs/testing.md`)。

| 条件 | 読むファイル |
| --- | --- |
| コマンドの実行でエラーが出たとき | `.claude/docs/command-errors.md` |
| AI へ渡す文面・生成関数を足す・直すとき、世界ごとの好み(舞台設定・文体の癖)の渡し方を扱うとき | `.claude/docs/user-preferences.md` |
| ファイルを読み書きするコードを書くとき、日本語を出すコマンドを打つとき | `.claude/docs/encoding.md` |
| リポジトリの構成・環境変数・サブモジュールを扱うとき、git のコマンドを打つとき | `.claude/docs/setup.md` |
| テストをしてと明確に依頼されたとき | `.claude/docs/testing.md` |
| 列名・型を確かめるとき、`db/schema.py` やマイグレーションを変えるとき | `.claude/docs/schema.md` |
| db を読む処理・AI とやり取りする処理(pydantic のマテリアル・出力モデル)を書く・直すとき、リファクタするとき | `.claude/docs/data-access.md` |
| PostgreSQL(`DEM_DATABASE_URL`)・AWS へのデプロイ・GitHub Actions・AI の待ち行列(`ai_task`)とルーチンを扱うとき | `.docs/README.md` から当たる文書 |

# コーディング規約

コードを読んで内容を理解すること。
コードを読んでも分からない理由のみコメントにする。
途中経過や失敗の知らせは `logging`(モジュールごとの `logger`)で出す。`print` は `show()` のように、標準出力に出すものが結果そのものの所だけに使う。
SQLAlchemy のセッションは、引数も変数も `s` と書く(`s: Session`、`with get_env_session() as s:`)。
python を直したら、core のルートで `uvx ruff check .` と `npx pyright --pythonpath ../.venv/bin/python` を回す(設定は `ruff.toml` / `pyrightconfig.json`)。
