#!/bin/bash
# 開発用の PostgreSQL + PostGIS を用意し、空の db の SQLAlchemy の URL を標準出力に出す(.docs/postgres.md「開発用の db」)。
# 何度走らせてもよい。サーバーが無ければ入れて起動し、db が無ければ schema.py から空の db を作る。
# クラウド(Claude Code on the web)では apt で入れた既定のクラスタ、それ以外では Docker のコンテナで動かす。
# リポジトリのルートを cwd にし、引数に python を渡して呼ぶ。
set -euo pipefail

py=${1:-.venv/bin/python}
db=novel_dev
user=novel
password=novel

if [ "${CLAUDE_CODE_REMOTE:-}" = true ]; then
  port=5432
  if ! ls /usr/share/postgresql/*/extension/postgis.control >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq >&2
    apt-get install -y -qq postgresql postgis >&2
  fi
  service postgresql start >&2
  psql_on() { runuser -u postgres -- psql -d "$1" -v ON_ERROR_STOP=1 -qtAc "$2"; }
  is_ready() { pg_isready -q -h 127.0.0.1 -p "$port"; }
else
  port=55432
  container=novel-postgis
  if ! docker container inspect "$container" >/dev/null 2>&1; then
    docker run -d --name "$container" --restart unless-stopped \
      -e POSTGRES_USER="$user" -e POSTGRES_PASSWORD="$password" \
      -p "127.0.0.1:$port:5432" -v novel-postgis-data:/var/lib/postgresql/data \
      postgis/postgis:16-3.5 >&2
  elif [ "$(docker container inspect -f '{{.State.Running}}' "$container")" != true ]; then
    docker start "$container" >&2
  fi
  psql_on() { docker exec "$container" psql -U "$user" -d "$1" -v ON_ERROR_STOP=1 -qtAc "$2"; }
  # 初回の初期化中は、ソケットだけで聞く仮のサーバーが立つ。TCP で聞くまで待てば、その後の本番のサーバーに当たる
  is_ready() { docker exec "$container" pg_isready -q -h 127.0.0.1 -U "$user"; }
fi

for _ in $(seq 60); do
  is_ready && break
  sleep 1
done
is_ready || { echo "PostgreSQL が 60 秒で起動しなかった" >&2; exit 1; }

if [ "${CLAUDE_CODE_REMOTE:-}" = true ] && [ "$(psql_on postgres "SELECT 1 FROM pg_roles WHERE rolname = '$user'")" != 1 ]; then
  # CREATE EXTENSION postgis と CREATE DATABASE をこのユーザでするので、開発用に superuser にする
  psql_on postgres "CREATE ROLE $user LOGIN SUPERUSER PASSWORD '$password'"
fi

url="postgresql+psycopg://$user:$password@127.0.0.1:$port/$db"
initialized=f
if [ "$(psql_on postgres "SELECT 1 FROM pg_database WHERE datname = '$db'")" = 1 ]; then
  initialized=$(psql_on "$db" "SELECT to_regclass('public.alembic_version') IS NOT NULL")
fi
if [ "$initialized" != t ]; then
  "$py" -m db.postgres.init_db --url "$url" --create-database >&2
fi

echo "$url"
