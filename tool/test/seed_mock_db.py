#!/usr/bin/env python3
from tool.test import copy_production_db  # db をテスト用の db に固定する(schema より先に読む)

import argparse
import random

from factory.random import reseed_random
from sqlalchemy import func, select

from db.schema import Base, engine
from randomizer import mock_factories


def seed_mock_db(n: int, seed: int, recreate: bool = False) -> dict[str, int]:
    if recreate:
        copy_production_db()
    reseed_random(seed)

    mock_factories.bind(engine)
    try:
        for factory_class in mock_factories.ALL_FACTORIES:
            factory_class.create_batch(n)
        mock_factories.commit()
    finally:
        mock_factories.close()

    with engine.connect() as conn:
        return {table.name: conn.execute(select(func.count()).select_from(table)).scalar_one()
                for table in Base.metadata.sorted_tables}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=100, help="各テーブルに足す件数")
    p.add_argument("--seed", type=int, help="乱数シード(省略時は自動生成して表示)")
    p.add_argument("--recreate", action="store_true", help="本番の db を写してテスト用の db を作り直してから足す")
    args = p.parse_args()

    seed = args.seed if args.seed is not None else random.randrange(10**9)
    print(f"seed = {seed}")
    for name, count in seed_mock_db(args.n, seed, args.recreate).items():
        print(f"{name}\t{count}")


if __name__ == "__main__":
    main()
