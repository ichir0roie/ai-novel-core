# 環境とコマンド

このリポジトリ(`ai-novel-core`)だけで動く。以前の世界リポジトリ(`my-novel-world`、アーカイブ済み)と SQLite の `novel.db`(RDS へ写し終えた)は使わない。

## python

- python・pytest・alembic は、リポジトリのルートを cwd にし、ルートの `.venv/bin/python`(Windows は `.venv\Scripts\python.exe`)で呼ぶ
- python のバージョンは `.python-version`(3.14)に書く
- `.venv` は SessionStart フック(`.claude/hooks/session-start.sh`)が用意する。web のセッションでは裏で用意し(ログは `.cache/session-setup.log`)、python を使うコマンドだけを PreToolUse フック(`.claude/hooks/wait-setup.sh`)が用意の済むまで待たせる
- 手で用意するときは、uvx で新しめの uv を使う(python 本体は uv が取ってくる。古い uv は新しいバージョンを知らない):

```
uvx --from 'uv>=0.9' uv venv --python 3.14 .venv
uvx --from 'uv>=0.9' uv pip install --python .venv/bin/python -r requirements.txt
```

- `.venv` に pip は入らない
- 素の `uv`(`/root/.local/bin/uv` など)は使わない。古いことがあり、python の rc バージョンを選んで pydantic が落ちる。rc バージョンの `.venv` ができたら、上の uvx の uv で作り直す
- `.venv` が無い(`.venv/bin/python: No such file or directory`)のは、SessionStart フックが走っていないとき(後から足したリポジトリ・コンテナが戻ったとき)。web のセッションでは `CLAUDE_CODE_REMOTE=true bash .claude/hooks/session-start.sh` を手で回す
- フック(`.claude/hooks/`)と `.claude/settings.json` は、書き換える前に何を変えるかをユーザに示して承認を取る(auto mode も自己の書き換えとして止める)
- 書き換えたフックは、作業ツリーをスクラッチパッドに写し、`CLAUDE_CODE_REMOTE=true CLAUDE_ENV_FILE=<写しの中のファイル>` を付けて動かして確かめてから登録する。確かめずに登録すると、このセッションのツールの呼び出しを待たせ続けることがある
- `requirements.txt` は、依存の依存までバージョンとハッシュを固定したもの。手では書かない。直接使うパッケージは `requirements.in` に書き、そこから作る(`--universal` は Windows でも同じファイルで入れるため)
- パッケージを足す・バージョンを上げるときは、`requirements.in` を直してから:

```
uvx --from 'uv>=0.9' uv pip compile requirements.in --universal --python-version 3.14 --generate-hashes -o requirements.txt
uvx --from 'uv>=0.9' uv pip install --python .venv/bin/python -r requirements.txt
```

- 固定したバージョンの中で上げるだけなら、1 行目に `--upgrade-package <名前>`(全部なら `--upgrade`)を足す

## db と環境変数

| 環境変数 | 中身 | 渡す所 |
| --- | --- | --- |
| `DEM_DATABASE_URL` | 読み書きする db。手元は踏み台越しの RDS(`postgresql+psycopg://novel_app@127.0.0.1:15432/novel?sslmode=require`) | SessionStart フック・`.vscode`(ターミナル・タスク・デバッグ) |
| `DEM_DATABASE_IAM_AUTH` | `1` なら IAM データベース認証のトークンで繋ぐ | 同上 |
| `DEM_DEV_DATABASE_URL` | 開発用の空の PostgreSQL + PostGIS(`infra_local/postgis.sh`)。テストの db もこのサーバーに作る | `.vscode` は固定の値。Claude Code では渡さず、テスト(`tool.test`)が要ったときに用意する |
| `PYTHONUTF8` | `1`(Windows の文字化け除け。下の「文字コード」) | 同上 |

- 手元から RDS へは踏み台越しの転送で繋ぐ(VS Code ではタスク「db tunnel」で起こす。決まりは `.claude/docs/db.md`)
- web のセッションは RDS に繋がず API を通す(`.claude/docs/web-db.md`)
- テストは `novel_test` に差し替える(`.claude/docs/testing.md`)
- `DEM_DATABASE_URL` が無くても import はできる(web のセッションは表の定義だけを使う)。繋いだ時点で止まる

## 文字コード

- リポジトリのテキスト(`.py` `.md` `.json` `.yaml` など)はすべて UTF-8(BOM 無し)。ファイルを開くときは必ず `encoding="utf-8"` を付ける
- db(PostgreSQL)も UTF-8 で作る(`db.postgres.init_db` の `CREATE DATABASE ... ENCODING 'UTF8'`)
- 日本語を出すコマンドは `PYTHONUTF8=1` を付けて実行する(Windows の python は標準出力が cp932 になり、文字化け・`UnicodeEncodeError` になる)

## コマンドのエラー

エラーは握りつぶさず、原因を特定して対策してから作業に戻る。原因がコードならコードを、呼び出し方(引数・環境変数・手順)なら指示書(`CLAUDE.md`・`.claude/docs/`・スキル)を直す。

- exit 144 でシェルごと止まった: `pkill -f` / `pgrep -f` のパターンが自分のシェルにも当たった。一字を `[]` で囲む(`'[n]ext dev'`)
- 裏で回しているコマンドを止める: `pkill` ではなく、そのタスクの id で `TaskStop` する。残りは `pgrep -af '[g]enerate_episode'` などで見る
- 使い捨てのスクリプトで import が落ちた: スクラッチパッドのファイル名が標準ライブラリを隠した(`inspect.py` など)。`check_<対象>.py` のように名付ける
- 一括置換が当たらないまま進んだ: python の `str.replace` は当たらなくても黙る。`assert t.count(old) == 1` を付ける
- auto mode の判定が返らず(no verdict)ツールが止まった: 一時的なもの。少し置いてやり直す
- `npm ci`・`pip`・`curl` がプロキシで落ちた(`proxy`・`403`・TLS): `/root/.ccr/README.md` と `curl -sS "$HTTPS_PROXY/__agentproxy/status"` を見て、道具ごとの直し方でやり直す。通らなければユーザに伝えて止まる。落ちたチェック(typecheck・lint など)を飛ばして先へ進まない
- AWS の MCP が `expired or invalid AWS credentials` で落ちた: 打ち直しても直らない。ユーザに伝え、実データを見ずに答えるならそう明記する
