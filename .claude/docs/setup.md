# 環境構築

このリポジトリ(`ai-novel-core`)だけで動く。作品の中身(話・人物・設定)は db(AWS の RDS)にだけ置き、リポジトリには入れない。
以前の世界リポジトリ(`my-novel-world`)と SQLite の `novel.db` は使わない(`novel.db` は RDS へ写し終え、世界リポジトリはアーカイブした)。

## python

python・pytest・alembic はリポジトリのルートを cwd にし、ルートの `.venv/bin/python`(Windows は `.venv\Scripts\python.exe`)で呼ぶ。
python の版は `.python-version`(3.14)に書く。Claude Code のセッションでは SessionStart フック(`.claude/hooks/session-start.sh`)が
`.venv` を用意する。web のセッションでは起動を待たせないよう裏で用意し(ログは `.cache/session-setup.log`)、python を使うコマンドだけを
PreToolUse フック(`.claude/hooks/wait-setup.sh`)が用意の済むまで待たせる。手で用意するときは(python 本体は uv が取ってくる。uv が古いと新しい版を知らないので、uvx で新しめの uv を使う):

```
uvx --from 'uv>=0.9' uv venv --python 3.14 .venv
uvx --from 'uv>=0.9' uv pip install --python .venv/bin/python -r requirements.txt
```

`.venv` に pip は入らない。

`requirements.txt` は、依存の依存まで版とハッシュを固定したもので、手では書かない。直接使うパッケージは `requirements.in` に書き、
そこから作る(Windows でも同じファイルで入るよう `--universal` で作る)。パッケージを足す・版を上げるときは、`requirements.in` を直してから:

```
uvx --from 'uv>=0.9' uv pip compile requirements.in --universal --python-version 3.14 --generate-hashes -o requirements.txt
uvx --from 'uv>=0.9' uv pip install --python .venv/bin/python -r requirements.txt
```

固定した版の中で上げるだけなら、1 行目に `--upgrade-package <名前>`(全部なら `--upgrade`)を足す。

## db と環境変数

| 環境変数 | 中身 | 渡す所 |
| --- | --- | --- |
| `DEM_DATABASE_URL` | 読み書きする db。手元は踏み台越しの RDS(`postgresql+psycopg://novel_app@127.0.0.1:15432/novel?sslmode=require`) | SessionStart フック・`.vscode`(ターミナル・タスク・デバッグ) |
| `DEM_DATABASE_IAM_AUTH` | `1` なら IAM データベース認証のトークンで繋ぐ | 同上 |
| `DEM_DEV_DATABASE_URL` | 開発用の空の PostgreSQL + PostGIS(`infra_local/postgis.sh`)。テストの db もこのサーバーに作る | `.vscode` は固定の値。Claude Code では渡さず、テスト(`tool.test`)が要ったときに用意する |
| `PYTHONUTF8` | `1`(Windows の文字化け除け。`.claude/docs/encoding.md`) | 同上 |

- 手元から RDS へは、踏み台越しの転送(`.venv/bin/python -m tool.aws.rds --serve`)を張って繋ぐ。SessionStart フックが裏で起こし、
  VS Code ではタスク「db tunnel」で起こす。繋ぎ方の決まりは `.claude/docs/db.md`、AWS の側は `.claude/docs/aws.md`
- `DEM_DATABASE_URL` が無くても import はできる(web のセッションは db に繋がず、表の定義だけを使う)。繋いだ時点で止まる
- web のセッション(`CLAUDE_CODE_REMOTE=true`)は RDS に繋がない。API を通す(`.docs/web-session.md`)
- テストは `DEM_DATABASE_URL` を手元の PostGIS のテスト用の db に差し替える(`.claude/docs/testing.md`)

## git

git のコマンドはリポジトリのルートで打つ。決まりは `.claude/docs/git.md`。
