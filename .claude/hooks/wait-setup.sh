#!/bin/bash
# web のセッションで、裏で用意している .venv(session-start.sh)を使うコマンドを、用意が済むまで待たせる。
# curl で API を叩く・git・ファイルを読むといった python の要らないコマンドは待たせない。
set -uo pipefail
[ "${CLAUDE_CODE_REMOTE:-}" = true ] || exit 0
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

setup_dir=.cache/session-setup
# 無ければ、このセッションは裏の用意を起こしていない(前の版のフックで始まったなど)ので待つものが無い
[ -d "$setup_dir" ] || exit 0
[ -e "$setup_dir/python" ] && exit 0
# 用意が止まったことは一度だけ伝え、あとは通す(手で直したあとも止め続けないように)
[ -e "$setup_dir/reported" ] && exit 0

command=$(jq -r '.tool_input.command // ""')
grep -qE 'python|pytest|alembic|\.venv|pyright|uvicorn' <<< "$command" || exit 0

for _ in $(seq 300); do
  [ -e "$setup_dir/python" ] && exit 0
  [ -e "$setup_dir/failed" ] && break
  sleep 1
done
touch "$setup_dir/reported"
{
  echo ".venv の用意が済んでいない(SessionStart フックが裏で回す .claude/hooks/session-start.sh --background)。"
  echo "ログ .cache/session-setup.log の末尾:"
  tail -n 20 .cache/session-setup.log 2>/dev/null
  echo "直してから .claude/hooks/session-start.sh --background を回し直すか、同じコマンドをもう一度打つ。"
} >&2
exit 2
