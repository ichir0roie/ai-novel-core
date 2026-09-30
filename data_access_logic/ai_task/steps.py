#!/usr/bin/env python3
"""待ち行列(`ai_task`)を web のセッションから回すための db の段(`data_access_logic/step.py`)。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from data_access_logic.ai_task import queue
from data_access_logic.step import db_step
from db.schema import AiTask


class ClaimedTask(BaseModel):
    id: int
    entrance: str
    args: dict[str, Any]


class TaskOutcome(BaseModel):
    id: int
    result: Any = None
    error: str | None = None


class DbStatus(BaseModel):
    dialect: str
    alembic_current: str | None
    postgis: str | None
    ai_task_queued: int


@db_step
def claim_next_task(s: Session) -> ClaimedTask | None:
    task = queue.claim_next(s)
    return None if task is None else ClaimedTask(id=task.id, entrance=task.entrance, args=task.args or {})


@db_step
def finish_task(s: Session, outcome: TaskOutcome) -> str:
    task = s.get_one(AiTask, outcome.id)
    queue.finish(s, task, result=outcome.result, error=outcome.error)
    return task.status


@db_step
def requeue_running_tasks(s: Session) -> int:
    return queue.requeue_running(s)


@db_step
def db_status(s: Session) -> DbStatus:
    dialect = s.get_bind().dialect.name
    return DbStatus(
        dialect=dialect,
        alembic_current=s.scalar(text("SELECT version_num FROM alembic_version")),
        postgis=s.scalar(text("SELECT extversion FROM pg_extension WHERE extname = 'postgis'"))
        if dialect == "postgresql" else None,
        ai_task_queued=queue.pending_count(s),
    )
