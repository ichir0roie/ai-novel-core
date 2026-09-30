#!/bin/bash
# .venv(リポジトリのルート直下)を用意して、環境変数を渡す。
# 手元では、RDS への転送(tool.aws.rds --serve)を裏で起こし、ふだんの読み書きをそこへ向ける(.claude/docs/setup.md)。
# web のセッション(CLAUDE_CODE_REMOTE=true)は db に繋がず API を通すので、転送も RDS の URL も用意しない。
# API を叩くだけの作業に python は要らないので、web では環境変数だけ渡してすぐ戻り、.venv は裏で用意する。
# 開発用の PostgreSQL はここでは用意しない。テストで要ったときに tool.test が infra_local/postgis.sh で用意する。
# gui.dev がブラウザに使う専用プロファイル(.brave-profile/)も用意する。
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

mkdir -p .brave-profile .cache

# 裏で回した用意の進み具合。.venv が揃えば python を置き、途中で止まれば failed を置く。
# .claude/hooks/wait-setup.sh(PreToolUse フック)が、python を使うコマンドをこれが揃うまで待たせる
setup_dir=.cache/session-setup
background=0
[ "${1:-}" = --background ] && background=1
if [ "${CLAUDE_CODE_REMOTE:-}" = true ] && [ "$background" = 0 ]; then
  if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
    {
      echo 'export PYTHONUTF8=1'
      echo "export PYTHONPATH='$PWD'"
    } >> "$CLAUDE_ENV_FILE"
  fi
  rm -rf "$setup_dir"
  mkdir -p "$setup_dir"
  setsid nohup .claude/hooks/session-start.sh --background >> .cache/session-setup.log 2>&1 < /dev/null &
  echo ".venv は裏で用意している(ログは .cache/session-setup.log)" >&2
  exit 0
fi
if [ "$background" = 1 ]; then
  mkdir -p "$setup_dir"
  # compact などでフックがまた走っても、裏の用意が重ならないよう一つずつ回す
  exec 9> .cache/session-setup.lock
  flock 9
  trap '[ -e "$setup_dir/python" ] || touch "$setup_dir/failed"' EXIT
fi

# python の版は .python-version に書く。版の違う .venv は作り直す。
# uv が古いと新しい版の python を知らないので、uvx で新しめの uv を使う(python もそれが取ってくる)
python_version=$(tr -d '[:space:]' < .python-version)
uv=(uvx -q --from 'uv>=0.9' uv)
py=.venv/bin/python
[ -x "$py" ] || py=.venv/Scripts/python.exe
if [ -x "$py" ] && [ "$("$py" -c 'import sys; print("%d.%d" % sys.version_info[:2])')" != "$python_version" ]; then
  rm -rf .venv
fi
if [ ! -x .venv/bin/python ] && [ ! -x .venv/Scripts/python.exe ]; then
  "${uv[@]}" venv -q --python "$python_version" .venv >&2
fi
py=.venv/bin/python
[ -x "$py" ] || py=.venv/Scripts/python.exe
"${uv[@]}" pip install -q --python "$py" -r requirements.txt >&2
if [ "$background" = 1 ]; then
  touch "$setup_dir/python"
  exit 0
fi

# RDS の在りかは、CDK が置いた SSM パラメータで確かめる。AWS に建てていない人・資格情報の無い手元では飛ばす
rds=0
if [ "${CLAUDE_CODE_REMOTE:-}" != true ] && command -v aws >/dev/null \
    && timeout 20 aws ssm get-parameter --name /novel/db/endpoint --query Parameter.Name --output text >/dev/null 2>&1; then
  rds=1
  if ! (exec 3<>/dev/tcp/127.0.0.1/15432) 2>/dev/null; then
    # セッションが閉じても残す。止めるのは `pkill -f 'tool.aws.rds --serve'`(自分で起こした踏み台も止まる)
    setsid nohup "$py" -m tool.aws.rds --serve >> .cache/rds-tunnel.log 2>&1 < /dev/null &
    echo "RDS への転送を裏で起こした(ログは .cache/rds-tunnel.log。踏み台が止まっていれば 1 分ほどかかる)" >&2
  fi
fi

if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  {
    echo 'export PYTHONUTF8=1'
    echo "export PYTHONPATH='$PWD'"
    if [ "$rds" = 1 ]; then
      # novel_app(行の読み書きだけ)で、パスワードの代わりに IAM データベース認証のトークンで繋ぐ
      echo "export DEM_DATABASE_URL='postgresql+psycopg://novel_app@127.0.0.1:15432/novel?sslmode=require'"
      echo 'export DEM_DATABASE_IAM_AUTH=1'
    fi
  } >> "$CLAUDE_ENV_FILE"
fi
