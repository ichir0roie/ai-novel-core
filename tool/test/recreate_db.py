#!/usr/bin/env python3
"""テスト用の db(`novel_test`)を消し、本番の db を写して作り直す。リポジトリのルートから:

    .venv/bin/python -m tool.test.recreate_db

写し元は `DEM_DATABASE_URL`(手元は転送越しの RDS)なので、転送(`tool.aws.rds --serve`)を張っておく。
pytest は、テスト用の db に行があればそのまま使うので、本番の行を取り込み直したいときや、マイグレーションを足したあとに回す。
"""
from tool.test import copy_production_db  # db をテスト用の db に固定する(schema より先に読む)

from data_access_logic.logs import configure_logging


def main() -> None:
    configure_logging()
    for name, count in copy_production_db().items():
        print(f"{name}\t{count}")


if __name__ == "__main__":
    main()
