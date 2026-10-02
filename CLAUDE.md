# 作業指針

Claude はユーザへの返答を常に日本語で書く。

作品の中身は db(AWS の RDS)にだけあり、このリポジトリには無い。
プロット・時刻・登場人物を決めた話(プロットと本文をまとめて持つ `episode`)はスキル `episode` の手順で回す。

# 作業する場所

作業する場所は二つあり、環境変数 `CLAUDE_CODE_REMOTE` で見分ける。db への道と git の進め方が違うので、
下の表で場所を限った行は、その場所の行だけを読む(もう一方は読まない)。スキルも、場所で違う手順は別のファイルに分けてある。

| 場所 | `CLAUDE_CODE_REMOTE` | SessionStart フック(`.claude/hooks/session-start.sh`) | db | git |
| --- | --- | --- | --- | --- |
| 手元(CLI・VS Code) | `true` でない | `.venv` を用意し、RDS への転送を起こして `DEM_DATABASE_URL` を渡す | 入口越しに直に読み書きする | 頼まれたときだけ |
| web のセッション(Claude Code on the web) | `true` | `.venv` を裏で用意する(python のコマンドだけ用意が済むまで待たされる) | 繋がない。API 越しに読み書きする | セッションの指示に従う |

# デバッグ・テストの db

**デバッグ・テスト・動作確認(GUI を起こして見る・スクショを撮る・行を足して試す)で db を読み書きするときは、
手元でも web のセッションでも、必ず手元の PostGIS のテスト用の db(`novel_test`)を使う。
本番の RDS(手元の転送・web の API)には決して向けない。** 用意の仕方は `.claude/docs/testing.md`。

# 実装からプルリクまで

手元でも web のセッションでも、実装からプルリクまでは次の順で進める。

1. 実装する。途中でデバッグのための単体テスト(直している所だけを確かめるテスト・小さな実行)は回してよい
2. 実装したら、UI の画像(画面を変えたとき。テスト用の db で起こして撮る)と、変えた処理の場所(`ファイル:行`)を示し、
   実装の内容をユーザに確かめてもらう。直す指示があれば 1 に戻る
3. ユーザが実装を認めてから、網羅テストを回す(`.claude/docs/testing.md` の「網羅テスト」)。網羅テストは実装が済むまで回さない
4. 網羅テストが通ってから、プルリクを作る。それより前には作らない

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
| 手元で db を読み書きするとき(入口の呼び出し・作成、マイグレーションの確認、他のセッションとの同時作業を含む) | `.claude/docs/db.md` |
| web のセッションで db を読み書きするとき(id・行を引く、入口・AI の入口を呼ぶ) | `.claude/docs/web-db.md` |
| テストをしてと明確に依頼されたとき、網羅テストを回すとき、デバッグ・動作確認で db を読み書きするとき | `.claude/docs/testing.md` |
| テスト・動作確認で GUI(API・画面)を動かすとき | `.claude/docs/gui.md` |
| ミームを扱うとき、本文・人物の芯(`text`)・来歴(`histories`)を書くとき | `.claude/docs/meme.md` |
| 列名・型を確かめるとき、`db/schema.py` やマイグレーションを変えるとき | `.claude/docs/schema.md` |
| db を読む処理・AI とやり取りする処理(pydantic のマテリアル・出力モデル)を書く・直すとき、リファクタするとき | `.claude/docs/data-access.md` |
| PostgreSQL(`DEM_DATABASE_URL`)・AWS へのデプロイ・GitHub Actions・AI の待ち行列(`ai_task`)と web のセッションで回す仕組み(`web_session/`・`steps.py`)を扱うとき | `.docs/README.md` から当たる文書 |
| AWS の db・資源に触れるとき、API(Lambda)の段・web の流れ(`web_session/`)のコードを書くとき | `.claude/docs/aws.md` |

# コーディング規約

コードを読んで内容を理解すること。
コードを読んでも分からない理由のみコメントにする。
途中経過や失敗の知らせは `logging`(モジュールごとの `logger`)で出す。`print` は `show()` のように、標準出力に出すものが結果そのものの所だけに使う。
SQLAlchemy のセッションは、引数も変数も `s` と書く(`s: Session`、`with get_env_session() as s:`)。
python を直したら、ルートで `uvx ruff check .` と `npx pyright --pythonpath .venv/bin/python` を回す(設定は `ruff.toml` / `pyrightconfig.json`)。
