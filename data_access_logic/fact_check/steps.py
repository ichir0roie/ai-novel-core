#!/usr/bin/env python3
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.orm import Session

from ai.claude_code import fact_checker
from data_access_logic.source_text import SourceText
from data_access_logic.step import db_step


class CheckScope(BaseModel):
    table: str
    # 渡さなければ、まだ検めていない行
    ids: list[int] | None = None
    limit: int | None = None


class NotesForm(BaseModel):
    notes: list[fact_checker.FactCheckNote]


@db_step
def check_sources(s: Session, form: CheckScope) -> list[SourceText]:
    return fact_checker.check_sources(s, form.table, form.ids, form.limit)


@db_step
def save_fact_checks(s: Session, form: NotesForm) -> int:
    return fact_checker.save_fact_checks(s, form.notes)
