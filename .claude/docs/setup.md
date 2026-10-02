# 環境構築

このリポジトリ(`ai-novel-core`)だけで動く。以前の世界リポジトリ(`my-novel-world`、アーカイブ済み)と SQLite の `novel.db`(RDS へ写し終えた)は使わない。

## python

- python・pytest・alembic は、リポジトリのルートを cwd にし、ルートの `.venv/bin/python`(Windows は `.venv\Scripts\python.exe`)で呼ぶ
- python の版は `.python-version`(3.14)に書く
- `.venv` は SessionStart フック(`.claude/hooks/session-start.sh`)が用意する。web のセッションでは裏で用意し(ログは `.cache/session-setup.log`)、python を使うコマンドだけを PreToolUse フック(`.claude/hooks/wait-setup.sh`)が用意の済むまで待たせる
- 手で用意するときは、uvx で新しめの uv を使う(python 本体は uv が取ってくる。古い uv は新しい版を知らない):

```
uvx --from 'uv>=0.9' uv venv --python 3.14 .venv
uvx --from 'uv>=0.9' uv pip install --python .venv/bin/python -r requirements.txt
```

- `.venv` に pip は入らない
- 素の `uv`(`/root/.local/bin/uv` など)は使わない。古いことがあり、python の rc 版を選んで pydantic が落ちる。rc 版の `.venv` ができたら、上の uvx の uv で作り直す
- `.venv` が無い(`.venv/bin/python: No such file or directory`)のは、SessionStart フックが走っていないとき(後から足したリポジトリ・コンテナが戻ったとき)。web のセッションでは `CLAUDE_CODE_REMOTE=true bash .claude/hooks/session-start.sh` を手で回す
- フック(`.claude/hooks/`)と `.claude/settings.json` は、書き換える前に何を変えるかをユーザに示して承認を取る(auto mode も自己の書き換えとして止める)
- 書き換えたフックは、作業ツリーをスクラッチパッドに写し、`CLAUDE_CODE_REMOTE=true CLAUDE_ENV_FILE=<写しの中のファイル>` を付けて動かして確かめてから登録する。確かめずに登録すると、このセッションのツールの呼び出しを待たせ続けることがある
- `requirements.txt` は、依存の依存まで版とハッシュを固定したもの。手では書かない。直接使うパッケージは `requirements.in` に書き、そこから作る(`--universal` は Windows でも同じファイルで入れるため)
- パッケージを足す・版を上げるときは、`requirements.in` を直してから:

```
uvx --from 'uv>=0.9' uv pip compile requirements.in --universal --python-version 3.14 --generate-hashes -o requirements.txt
uvx --from 'uv>=0.9' uv pip install --python .venv/bin/python -r requirements.txt
```

- 固定した版の中で上げるだけなら、1 行目に `--upgrade-package <名前>`(全部なら `--upgrade`)を足す

## db と環境変数

| 環境変数 | 中身 | 渡す所 |
| --- | --- | --- |
| `DEM_DATABASE_URL` | 読み書きする db。手元は踏み台越しの RDS(`postgresql+psycopg://novel_app@127.0.0.1:15432/novel?sslmode=require`) | SessionStart フック・`.vscode`(ターミナル・タスク・デバッグ) |
| `DEM_DATABASE_IAM_AUTH` | `1` なら IAM データベース認証のトークンで繋ぐ | 同上 |
| `DEM_DEV_DATABASE_URL` | 開発用の空の PostgreSQL + PostGIS(`infra_local/postgis.sh`)。テストの db もこのサーバーに作る | `.vscode` は固定の値。Claude Code では渡さず、テスト(`tool.test`)が要ったときに用意する |
| `PYTHONUTF8` | `1`(Windows の文字化け除け。`.claude/docs/encoding.md`) | 同上 |

- 手元から RDS へは踏み台越しの転送で繋ぐ(VS Code ではタスク「db tunnel」で起こす。決まりは `.claude/docs/db.md`)
- web のセッションは RDS に繋がず API を通す(`.claude/docs/web-db.md`)
- テストは `novel_test` に差し替える(`.claude/docs/testing.md`)
- `DEM_DATABASE_URL` が無くても import はできる(web のセッションは表の定義だけを使う)。繋いだ時点で止まる

## git

git のコマンドはリポジトリのルートで打つ。決まりは `.claude/docs/git.md`。
