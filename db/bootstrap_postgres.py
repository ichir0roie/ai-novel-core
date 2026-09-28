#!/usr/bin/env python3
"""RDS など、まだ何も無い Postgres に novel.db と同じ形(スキーマ)を作る。

このリポジトリの alembic 履歴は、sqlite で `Base.metadata.create_all` して作った db への
差分としてしか書かれていない(最初の revision がテーブル作成を含まない)。そのため空の db に
`alembic upgrade head` をそのまま当てると、まだ無いテーブルを触ろうとして落ちる(実機で確認済み)。
空の db にはまず `create_all` で直接 head の形を作り、`alembic stamp head` で「もう head まで
当ててある」ことにしてから、以後は普通に `upgrade head` を使えるようにする。

    DEM_DATABASE_URL=postgresql+psycopg://... .venv/bin/python -m db.bootstrap_postgres
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from db.schema import Base, DATABASE_URL, engine

ALEMBIC_INI = Path(__file__).resolve().parent / "alembic" / "alembic.ini"


def main() -> None:
    if not DATABASE_URL:
        sys.exit("DEM_DATABASE_URL が無い(sqlite にこの処理は要らない)")
    Base.metadata.create_all(engine)
    subprocess.run([sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "stamp", "head"], check=True)
    print(f"{DATABASE_URL} に head の形でスキーマを作った")


if __name__ == "__main__":
    main()
