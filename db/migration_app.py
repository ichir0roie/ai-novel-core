#!/usr/bin/env python3
"""マイグレーションだけを流す Lambda(novel-migrate)の口。

API と同じイメージを、コマンドだけ差し替えて動かす(`infra/lib/api-stack.ts`)。Lambda Web Adapter は、HTTP でない呼び出し
(CI の `aws lambda invoke`)を `POST /events` として流し、その応答をそのまま呼び出しの結果として返す。
db へは表の持ち主のロール(`novel_migrator`。`infra/sql/novel_migrator.sql`)で、IAM データベース認証で繋ぐ。
呼び出しの中身は見ず、イメージに入っている版まで `alembic upgrade head` を流すだけにする(任意の SQL は受けない)。
"""
from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import FastAPI
from pydantic import BaseModel

from db.schema import engine

logger = logging.getLogger(__name__)

ALEMBIC_INI = Path(__file__).parent / "alembic" / "alembic.ini"

app = FastAPI()


class MigrationResult(BaseModel):
    before: str | None
    after: str | None
    head: str | None


def _current() -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


# Lambda Web Adapter が起動を確かめる道(イメージの AWS_LWA_READINESS_CHECK_PATH)
@app.get("/api/ping")
def ping() -> dict[str, bool]:
    return {"ok": True}


@app.post("/events")
def migrate() -> MigrationResult:
    config = Config(str(ALEMBIC_INI))
    before = _current()
    command.upgrade(config, "head")
    result = MigrationResult(before=before, after=_current(), head=ScriptDirectory.from_config(config).get_current_head())
    logger.info(f"マイグレーション: {result.before} → {result.after}(head={result.head})")
    return result
