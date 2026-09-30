#!/usr/bin/env python3
"""ある db の中身を、`init_db` で作った PostgreSQL へ写す。リポジトリのルートから:

    .venv/bin/python -m db.postgres.copy_db --source-url sqlite:////path/to/novel.db \\
        --url postgresql+psycopg://user:pass@host:5432/novel

写し元は SQLite(昔の `novel.db`)でも PostgreSQL でもよい。テストの db に本番を写すのにも使う(`tool.test.copy_production_db`)。

- 写し元と写し先は同じ alembic の版(head)にそろえておく。食い違えば止まる
- 写し先は `init_db` 直後の空の db を前提にする。行があれば止まる(`--truncate` で消してから写す)
- 写し元の外部キーが指す先の無い行(SQLite は外部キーを確かめない)があれば、写す前に並べて止まる
- 一つのトランザクションで写すので、途中で落ちれば何も入らない

値は列の型(Stamp・confirmed など)を通さず、db に入っている生の値のまま運ぶ(型を通すと、今の型が受け付けない古い値で止まる)。
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import warnings
from typing import Any

logger = logging.getLogger(__name__)

_BATCH = 1000


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source-url", required=True, help="写し元の SQLAlchemy の URL(SQLite は sqlite:////<絶対パス>)")
    p.add_argument("--url", help="写し先の SQLAlchemy の URL。省けば DEM_DATABASE_URL")
    p.add_argument("--truncate", action="store_true", help="写し先の表を空にしてから写す(写し先の行は消える)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    url = args.url or os.environ.get("DEM_DATABASE_URL")
    if not url:
        sys.exit("URL が無い。--url か DEM_DATABASE_URL で PostgreSQL の URL を渡す")
    os.environ["DEM_DATABASE_URL"] = url

    from sqlalchemy.engine import make_url

    from data_access_logic.logs import configure_logging
    from db.schema import engine, make_url_engine

    configure_logging()
    source_url = make_url(args.source_url)
    if source_url.get_backend_name() == "sqlite":
        if not source_url.database or not os.path.exists(source_url.database):
            sys.exit(f"写し元が無い: {source_url.database}")
        # 他の処理が書き込み中でも半端に読まないよう、読み取り専用で開く
        source = make_url_engine(f"sqlite:///file:{os.path.abspath(source_url.database)}?mode=ro&uri=true")
    else:
        source = make_url_engine(args.source_url)
    counts = copy_database(source, engine, truncate=args.truncate)
    source.dispose()
    for name, count in counts.items():
        print(f"{name}\t{count}")


def copy_database(source, engine, truncate: bool = False) -> dict[str, int]:
    """source の全表の行を engine(PostgreSQL)へ写し、表ごとの行数を返す。"""
    from sqlalchemy import MetaData, func, select, text

    from db.schema import Base

    if engine.dialect.name != "postgresql":
        sys.exit("写し先が PostgreSQL ではない")
    source_meta = MetaData()
    target_meta = MetaData()
    with warnings.catch_warnings():
        # PostGIS の幾何の列(生成列。写さない)の型を SQLAlchemy が知らないという警告
        warnings.filterwarnings("ignore", message="Did not recognize type 'geometry'")
        source_meta.reflect(bind=source)
        target_meta.reflect(bind=engine)
    tables = [table for table in Base.metadata.sorted_tables if table.name in target_meta.tables]

    with source.connect() as src, engine.begin() as dst:
        _check_revision(src, dst)
        _check_orphans(src, source_meta, tables)
        if truncate:
            names = ", ".join(f'"{table.name}"' for table in tables)
            dst.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
        else:
            _check_empty(dst, target_meta, tables)
            # init_db が入れたマスターは写し元にもあるので、写し元の値で入れ直す
            dst.execute(text('TRUNCATE "personality_level" RESTART IDENTITY CASCADE'))

        counts: dict[str, int] = {}
        for table in tables:
            if table.name not in source_meta.tables:
                logger.info(f"{table.name}: 写し元に無いので飛ばす")
                continue
            counts[table.name] = _copy_table(src, dst, source_meta.tables[table.name], target_meta.tables[table.name],
                                             self_refs=_self_ref_columns(table))
            _sync_sequence(dst, table.name)

        for name, count in counts.items():
            copied = dst.scalar(select(func.count()).select_from(target_meta.tables[name]))
            if copied != count:
                raise RuntimeError(f"{name}: 写し元 {count} 行に対し、写し先 {copied} 行")
    return counts


def _check_revision(src, dst) -> None:
    from sqlalchemy import text

    def revision(conn) -> str | None:
        try:
            return conn.scalar(text("SELECT version_num FROM alembic_version"))
        except Exception:
            return None

    source_rev, target_rev = revision(src), revision(dst)
    if source_rev != target_rev:
        sys.exit(f"alembic の版が食い違う(写し元 {source_rev} / 写し先 {target_rev})。"
                 "両方に upgrade head を当ててから写す")


def _check_empty(dst, target_meta, tables) -> None:
    from sqlalchemy import func, select

    filled = [table.name for table in tables if table.name != "personality_level"
              and dst.scalar(select(func.count()).select_from(target_meta.tables[table.name]))]
    if filled:
        sys.exit(f"写し先に行がある({', '.join(filled)})。空の db に写すか、--truncate を付ける")


def _check_orphans(src, source_meta, tables) -> None:
    from sqlalchemy import func, select

    found = []
    for table in tables:
        if table.name not in source_meta.tables:
            continue
        child = source_meta.tables[table.name]
        for fk in table.foreign_keys:
            column, parent_name = fk.parent.name, fk.column.table.name
            if column not in child.c or parent_name not in source_meta.tables:
                continue
            parent = source_meta.tables[parent_name]
            orphan = child.c[column].is_not(None) & child.c[column].not_in(select(parent.c[fk.column.name]))
            count = src.scalar(select(func.count()).select_from(child).where(orphan))
            if count:
                ids = src.scalars(select(child.c.id).where(orphan).limit(20)).all()
                found.append(f"{table.name}.{column} → {parent_name}: {count} 行(id {ids})")
    if found:
        sys.exit("指す先の無い外部キーがある。写し元を直してから写す:\n  " + "\n  ".join(found))


def _self_ref_columns(table) -> list[str]:
    """自分の表を指す外部キー(親の場所・親の出来事など)。親が後ろの id にあると入れる順で落ちるので、後から埋める。"""
    return [fk.parent.name for fk in table.foreign_keys if fk.column.table.name == table.name]


def _plain(value: Any, column) -> Any:
    from sqlalchemy import Boolean

    if value is not None and isinstance(column.type, Boolean):
        # SQLite は真偽を 0/1 で持つ。PostgreSQL の boolean は整数を受け付けない
        return bool(value)
    return value


def _copy_table(src, dst, source_table, target_table, self_refs: list[str]) -> int:
    from sqlalchemy import JSON, bindparam, select
    from sqlalchemy.dialects.postgresql import JSONB

    from db.postgres.postgis import POSTGIS_COLUMNS

    # PostGIS の幾何は生成列なので写さない(写し先が値から作り直す)
    columns = [column.name for column in source_table.columns
               if column.name in target_table.c and (source_table.name, column.name) not in POSTGIS_COLUMNS]
    for name in columns:
        # 読み取った jsonb の型は None を JSON の null で入れるので、SQL の NULL で入れる型に替える
        if isinstance(target_table.c[name].type, JSON):
            target_table.c[name].type = JSONB(none_as_null=True)
    order = source_table.c.id if "id" in source_table.c else None
    rows = src.execute(select(*(source_table.c[name] for name in columns)).order_by(order)).mappings().all()
    later: list[dict[str, Any]] = []
    batch = []
    for row in rows:
        values = {name: _plain(row[name], target_table.c[name]) for name in columns}
        deferred = {name: values[name] for name in self_refs if values.get(name) is not None}
        if deferred:
            later.append({"_id": values["id"], **deferred})
            values.update(dict.fromkeys(deferred))
        batch.append(values)
        if len(batch) >= _BATCH:
            dst.execute(target_table.insert(), batch)
            batch = []
    if batch:
        dst.execute(target_table.insert(), batch)
    for name in self_refs:
        updates = [{"_id": item["_id"], "_value": item[name]} for item in later if name in item]
        if updates:
            dst.execute(target_table.update().where(target_table.c.id == bindparam("_id"))
                        .values({name: bindparam("_value")}), updates)
    logger.info(f"{source_table.name}: {len(rows)} 行")
    return len(rows)


def _sync_sequence(dst, table_name: str) -> None:
    from sqlalchemy import text

    # id を明示して入れたので、次の insert が既存の id とぶつからないよう連番を最大の id へ寄せる
    dst.execute(text(
        f"SELECT setval(pg_get_serial_sequence('\"{table_name}\"', 'id'), "
        f"COALESCE((SELECT max(id) FROM \"{table_name}\"), 1), "
        f"(SELECT max(id) FROM \"{table_name}\") IS NOT NULL)"))


if __name__ == "__main__":
    main()
