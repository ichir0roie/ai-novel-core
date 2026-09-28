#!/usr/bin/env python3
"""novel.db(sqlite)の全行を、DEM_DATABASE_URL の Postgres へ一度だけコピーする。

先に `db.bootstrap_postgres` でスキーマだけ作った、空の Postgres に対して使う。
テーブルは外部キーの向く先が先に来る順(`Base.metadata.sorted_tables`)でコピーし、
明示した id で入れた後は、次の自動採番が衝突しないよう各テーブルの sequence を最大 id へ進める。

    DEM_DATABASE_URL=postgresql+psycopg://... .venv/bin/python -m db.migrate_sqlite_to_postgres
"""
from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine, select, text

from db.schema import Base, DATABASE_URL, NOVEL_DB_PATH


def _self_fk_columns(table) -> list[str]:
    """idea.parent_idea_id のように同じテーブルの行を指す列。挿入順に関係なく後で埋める。"""
    return [col.name for col in table.columns if any(fk.column.table is table for fk in col.foreign_keys)]


def main() -> None:
    if not DATABASE_URL:
        sys.exit("DEM_DATABASE_URL が無い")
    sqlite_engine = create_engine(f"sqlite:///{os.path.abspath(NOVEL_DB_PATH)}")
    pg_engine = create_engine(DATABASE_URL)
    tables = Base.metadata.sorted_tables

    with pg_engine.connect() as check:
        for table in tables:
            if check.execute(select(table).limit(1)).first() is not None:
                sys.exit(f"移行先の {table.name} に既に行がある。二重に流さないよう止める")

    with sqlite_engine.connect() as src, pg_engine.begin() as dst:
        for table in tables:
            rows = [dict(row._mapping) for row in src.execute(select(table))]
            if not rows:
                continue
            self_cols = _self_fk_columns(table)
            # 自己参照の列は、指す先がまだ入っていない行があり得るので、いったん空で入れてから埋め直す
            deferred = [{col: row[col] for col in self_cols} for row in rows] if self_cols else None
            if self_cols:
                for row in rows:
                    for col in self_cols:
                        row[col] = None
            dst.execute(table.insert(), rows)
            if self_cols:
                for row, values in zip(rows, deferred):
                    if any(v is not None for v in values.values()):
                        dst.execute(table.update().where(table.c.id == row["id"]).values(**values))
            print(f"{table.name}: {len(rows)} 行")
            if "id" in table.c:
                dst.execute(text(
                    f'SELECT setval(pg_get_serial_sequence(\'"{table.name}"\', \'id\'), '
                    f'(SELECT MAX(id) FROM "{table.name}"))'
                ))


if __name__ == "__main__":
    main()
