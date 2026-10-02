# 作業指針

Claude はユーザへの返答を常に日本語で書く。

作品の中身は db(AWS の RDS)にだけあり、このリポジトリには無い。
プロット・時刻・登場人物を決めた話(プロットと本文をまとめて持つ `episode`)はスキル `episode` の手順で回す。

# 作業する場所

場所は環境変数 `CLAUDE_CODE_REMOTE` で見分ける。場所を限った行(下の表)と、場所ごとに分けたスキルの手順は、自分の場所のものだけを読む。

| 場所 | `CLAUDE_CODE_REMOTE` | SessionStart フック(`.claude/hooks/session-start.sh`) | db | git |
| --- | --- | --- | --- | --- |
| 手元(CLI・VS Code) | `true` でない | `.venv` を用意し、RDS への転送を起こして `DEM_DATABASE_URL` を渡す | 入口越しに直に読み書きする | 頼まれたときだけ |
| web のセッション(Claude Code on the web) | `true` | `.venv` を裏で用意する(python のコマンドだけ用意が済むまで待たされる) | 繋がない。API 越しに読み書きする | セッションの指示に従う |

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

# 条件付きのドキュメント

次の作業を始める前に、対応するファイルを Read して従う。当てはまらなければ読まなくてよい。パスはリポジトリのルートから。

| 条件 | 読むファイル |
| --- | --- |
| コマンドの実行でエラーが出た | `.claude/docs/command-errors.md` |
| AI へ渡す文面・生成関数を足す・直す、世界ごとの好み(舞台設定・文体の癖)を足す・直す・渡す、スキルから生成関数を呼ぶ | `.claude/docs/user-preferences.md` |
| ファイルを読み書きするコードを書く、日本語を出すコマンドを打つ | `.claude/docs/encoding.md` |
| リポジトリの構成・環境変数を扱う、python・pytest・alembic を動かす、`.venv` を用意する | `.claude/docs/setup.md` |
| git でコミット・push・merge・ブランチ操作をする、worktree での作業を頼まれた | `.claude/docs/git.md` |
| 手元で db を読み書きする(入口の呼び出し・作成、マイグレーションの確認、他のセッションとの同時作業を含む) | `.claude/docs/db.md` |
| web のセッションで db を読み書きする(id・行を引く、入口・AI の入口を呼ぶ) | `.claude/docs/web-db.md` |
| テストを明確に頼まれた、網羅テストを回す、デバッグ・動作確認で db を読み書きする | `.claude/docs/testing.md` |
| テスト・動作確認で GUI(API・画面)を動かす | `.claude/docs/gui.md` |
| ミームを扱う、本文・人物の芯(`text`)・来歴(`histories`)を書く | `.claude/docs/meme.md` |
| 列名・型を確かめる、`db/schema.py` やマイグレーションを変える | `.claude/docs/schema.md` |
| db を読む処理・AI とやり取りする処理(pydantic のマテリアル・出力モデル)を書く・直す、リファクタする | `.claude/docs/data-access.md` |
| PostgreSQL の構成・AWS へのデプロイ・GitHub Actions を調べる・直す | `.docs/README.md` から当たる文書 |
| AWS の db・資源に触れる、API(Lambda)の段・web の流れ(`web_session/`)・AI の待ち行列(`ai_task`)のコードを書く | `.claude/docs/aws.md`(仕組みの詳しい説明は `.docs/README.md` から当たる) |

# コーディング規約

- コードを読んで内容を理解する。
- コメントは、コードを読んでも分からない理由だけに書く。
- 途中経過や失敗の知らせは `logging`(モジュールごとの `logger`)で出す。`print` は、標準出力に出すものが結果そのものの所(`show()` など)だけに使う。
- SQLAlchemy のセッションは、引数も変数も `s` と書く(`s: Session`、`with get_env_session() as s:`)。
- python を直したら、ルートで `uvx ruff check .` と `npx pyright --pythonpath .venv/bin/python` を回す(設定は `ruff.toml` / `pyrightconfig.json`)。
