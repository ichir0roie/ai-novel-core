#!/usr/bin/env python3
from tool.test import NOVEL_DB_PATH, TEST_DB_PATH, copy_novel_db  # db を novel.test.db に固定する(schema より先に読む)

import argparse
import os

from ai.time_keeper.main import loop_time
from db.schema import Stamp
from tool.danger import reset_world
from tool.test.mock_ai_client import MockAIClient


def prepare_test_db(copy_from: str | None = None) -> None:
    if copy_from is None:
        if os.path.exists(TEST_DB_PATH):
            return
        copy_from = NOVEL_DB_PATH
    copy_novel_db(copy_from)
    print(f"[redrive_mock] {copy_from} → {TEST_DB_PATH}")


def redrive_mock_world(
    year: int = 2025, max_days: int | None = 120, seed: int | None = None,
    copy_from: str | None = None,
) -> MockAIClient:
    prepare_test_db(copy_from)
    reset_world.reset_world()
    ai = MockAIClient(seed)
    last = loop_time(ai, Stamp(year), max_days)
    print(f"[redrive_mock] {TEST_DB_PATH}: {last} まで / {ai.usage_summary()}")
    return ai


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--year", type=int, default=2025, help="始める年")
    p.add_argument("--max-days", type=int, default=120,
                   help="ループを回す回数(0 ならプロットが尽きるまで)")
    p.add_argument("--seed", type=int, help="モック AI の乱数シード")
    p.add_argument("--copy-from", help="回す前にこの db を novel.test.db へ写す")
    args = p.parse_args()
    redrive_mock_world(
        year=args.year, max_days=args.max_days or None, seed=args.seed,
        copy_from=args.copy_from)


if __name__ == "__main__":
    main()
