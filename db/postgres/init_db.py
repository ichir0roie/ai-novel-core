#!/usr/bin/env python3
"""空の PostgreSQL(+ PostGIS)に、`db/schema.py` の表を作る。リポジトリのルートから:

    DEM_DATABASE_URL=postgresql+psycopg://user:pass@host:5432/novel \\
        .venv/bin/python -m db.postgres.init_db --create-database

過去のマイグレーション(SQLite 向けに積んできたもの)は流さず、`schema.py` から今の形をそのまま作って
alembic を head に stamp する。以降の変更は `alembic upgrade head` で当てる。
表が一つでもあれば何もせずに止まる(作り直すなら db ごと消してからやり直す)。
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

logger = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", help="作る先の SQLAlchemy の URL。省けば DEM_DATABASE_URL")
    p.add_argument("--create-database", action="store_true",
                   help="URL の db が無ければ、同じサーバーの postgres db に繋いで CREATE DATABASE する")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    url = args.url or os.environ.get("DEM_DATABASE_URL")
    if not url:
        sys.exit("URL が無い。--url か DEM_DATABASE_URL で PostgreSQL の URL を渡す")
    # db.schema は import 時に engine を決めるので、読む前に URL を渡しておく
    os.environ["DEM_DATABASE_URL"] = url

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect, text
    from sqlalchemy.engine import make_url

    from data_access_logic.logs import configure_logging
    from db.postgres.postgis import install_postgis
    from db.schema import Base, engine, make_url_engine, seed_master_rows

    configure_logging()
    target = make_url(url)
    if target.get_backend_name() != "postgresql":
        sys.exit(f"PostgreSQL の URL ではない: {target.render_as_string(hide_password=True)}")

    if args.create_database:
        _create_database(make_url_engine, target)

    with engine.connect() as conn:
        existing = sorted(set(inspect(conn).get_table_names()) & set(Base.metadata.tables))
    if existing:
        sys.exit(f"表が既にある({', '.join(existing)})。空の db にだけ作る")

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        Base.metadata.create_all(conn)
        install_postgis(conn)
    seed_master_rows(engine)
    with engine.begin() as conn:
        # マスターは id を明示して入れたので、連番を追いつかせる
        conn.execute(text("SELECT setval(pg_get_serial_sequence('personality_level', 'id'), "
                          "(SELECT max(id) FROM personality_level))"))

    alembic_ini = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "alembic", "alembic.ini")
    command.stamp(Config(alembic_ini), "head")
    logger.info(f"作った: {target.render_as_string(hide_password=True)}")


def _create_database(make_url_engine, target) -> None:
    from sqlalchemy import text

    name = target.database
    admin = make_url_engine(target.set(database="postgres").render_as_string(hide_password=False))
    with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        if conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}):
            logger.info(f"db {name} は既にある")
        else:
            # 名前は bind できないので、識別子として引用して埋める
            conn.execute(text(f'CREATE DATABASE "{name.replace(chr(34), chr(34) * 2)}" ENCODING \'UTF8\' TEMPLATE template0'))
            logger.info(f"db {name} を作った")
    admin.dispose()


if __name__ == "__main__":
    main()
