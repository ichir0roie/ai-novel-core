#!/usr/bin/env python3
"""事実確認の db の段(`data_access_logic/step.py`)。web のセッション(`web_session/fact_check.py`)が API 越しに呼ぶ。"""
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


class LastMemeId(BaseModel):
    last_id: int


@db_step
def check_sources(s: Session, form: CheckScope) -> list[SourceText]:
    return fact_checker.check_sources(s, form.table, form.ids, form.limit)


@db_step
def save_fact_checks(s: Session, form: NotesForm) -> int:
    return fact_checker.save_fact_checks(s, form.notes)


@db_step
def last_meme_id(s: Session) -> int:
    return fact_checker.last_meme_id(s)


@db_step
def new_meme_ids(s: Session, form: LastMemeId) -> list[int]:
    return fact_checker.new_meme_ids(s, form.last_id)
