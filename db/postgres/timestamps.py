#!/usr/bin/env python3
"""すべての表が持つ作った時刻・直した時刻(`db/schema.py` の `Base.created_at` / `Base.updated_at`)を、db が入れる仕組み。

作った時刻は列の既定値(`now()`)で入り、直した時刻は PostgreSQL の関数 `set_updated_at` を表ごとのトリガーから呼んで入れ直す。
どちらもコードからは書かない。GUI・入口・SQL を手で打つときのどこから直しても同じ時刻が入る。

表を足したときのトリガーは自分で書かなくてよい:

- `init_db`(`Base.metadata.create_all`)で作る表には、`db/schema.py` が作った直後に掛ける
- alembic の `revision --autogenerate` で表を足すマイグレーションには、`db/alembic/env.py` が掛ける文を書き足す
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
    """`table` の行を直すたびに `set_updated_at` を呼ぶトリガー。何度打っても同じになる。"""
    return (f'CREATE OR REPLACE TRIGGER {FUNCTION} BEFORE UPDATE ON "{table}" '
            f"FOR EACH ROW EXECUTE FUNCTION {FUNCTION}()")


def install_updated_at(conn: Connection, tables: Iterable[str]) -> None:
    """関数を作り、`tables` にトリガーを掛ける。何度打っても同じになる。"""
    conn.execute(text(CREATE_FUNCTION))
    for table in tables:
        conn.execute(text(trigger_sql(table)))
