#!/usr/bin/env python3
"""web のセッションが API 越しに db に届くかを確かめる段(`data_access_logic/step.py`)。`web_session/check_api.py` が呼ぶ。"""
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from data_access_logic.step import db_step


class DbStatus(BaseModel):
    dialect: str
    alembic_current: str | None
    postgis: str | None


@db_step
def db_status(s: Session) -> DbStatus:
    dialect = s.get_bind().dialect.name
    return DbStatus(
        dialect=dialect,
        alembic_current=s.scalar(text("SELECT version_num FROM alembic_version")),
        postgis=s.scalar(text("SELECT extversion FROM pg_extension WHERE extname = 'postgis'"))
        if dialect == "postgresql" else None,
    )
