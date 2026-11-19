#!/usr/bin/env python3
"""直した時刻(`Base.updated_at`)を db が入れるトリガー。GUI・入口・手で打つ SQL のどこから直しても同じ時刻が入る。

表を足したときは自動で掛かる: `create_all` で作る表には `db/schema.py` が、autogenerate のマイグレーションには
`db/alembic/env.py` が掛ける。
"""
from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import Connection, text

FUNCTION = "set_updated_at"
# 立てた取引の中では直した時刻を進めない(`SET LOCAL novel.keep_updated_at = 'on'`)。時刻の暦の読み替えのように、
# 画面に出る中身を変えない書き直しが、話を直したことにならないようにする(なろうの書き換え・自動推敲の順は直した時刻を見る)
KEEP_SETTING = "novel.keep_updated_at"

CREATE_FUNCTION = f"""
CREATE OR REPLACE FUNCTION {FUNCTION}() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF coalesce(current_setting('{KEEP_SETTING}', true), '') = 'on' THEN
        NEW.updated_at := OLD.updated_at;
    ELSE
        NEW.updated_at := now();
    END IF;
    RETURN NEW;
END
$$
"""


def trigger_sql(table: str) -> str:
    """何度打っても同じになる。"""
    return (f'CREATE OR REPLACE TRIGGER {FUNCTION} BEFORE UPDATE ON "{table}" '
            f"FOR EACH ROW EXECUTE FUNCTION {FUNCTION}()")


def install_updated_at(conn: Connection, tables: Iterable[str]) -> None:
    """何度打っても同じになる。"""
    conn.execute(text(CREATE_FUNCTION))
    for table in tables:
        conn.execute(text(trigger_sql(table)))


def keep_updated_at(conn: Connection) -> None:
    """この取引の中の書き直しで、直した時刻を進めない。"""
    conn.execute(text(f"SET LOCAL {KEEP_SETTING} = 'on'"))
