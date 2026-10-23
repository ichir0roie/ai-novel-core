#!/usr/bin/env python3
"""直した時刻(`Base.updated_at`)を db が入れるトリガー。GUI・入口・手で打つ SQL のどこから直しても同じ時刻が入る。

表を足したときは自動で掛かる: `create_all` で作る表には `db/schema.py` が、autogenerate のマイグレーションには
`db/alembic/env.py` が掛ける。
"""
from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import Connection, text

FUNCTION = "set_updated_at"

CREATE_FUNCTION = f"""
CREATE OR REPLACE FUNCTION {FUNCTION}() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
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
