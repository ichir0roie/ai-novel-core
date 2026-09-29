#!/usr/bin/env python3
from tool.test import TEST_DB_PATH, copy_novel_db  # db を novel.test.db に固定する(schema より先に読む)

import argparse
import os
import random

from factory.random import reseed_random
from sqlalchemy import create_engine, func, select

from db.schema import Base
from randomizer import mock_factories


def seed_mock_db(n=100, seed=None, recreate=False) -> dict[str, int]:
    path = os.path.abspath(TEST_DB_PATH)
    if recreate:
        copy_novel_db()
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)

    seed = seed if seed is not None else random.randrange(10**9)
    reseed_random(seed)

    mock_factories.bind(engine)
    try:
        for factory_class in mock_factories.ALL_FACTORIES:
            factory_class.create_batch(n)
        mock_factories.commit()
    finally:
        mock_factories._session.remove()

    with engine.connect() as conn:
        counts = {
            table.name: conn.execute(select(func.count()).select_from(table)).scalar_one()
            for table in Base.metadata.sorted_tables
        }
    engine.dispose()
    return counts


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=100, help="各テーブルに足す件数")
    p.add_argument("--seed", type=int, help="乱数シード(省略時は自動生成して表示)")
    p.add_argument("--recreate", action="store_true", help="本番の novel.db を写して作り直してから足す")
    args = p.parse_args()

    seed = args.seed if args.seed is not None else random.randrange(10**9)
    print(f"seed = {seed}")
    counts = seed_mock_db(n=args.n, seed=seed, recreate=args.recreate)
    for name, count in counts.items():
        print(f"{name}\t{count}")


if __name__ == "__main__":
    main()
