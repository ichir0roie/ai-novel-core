#!/usr/bin/env python3
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.orm import Session

from data_access_logic.label import label_of
from data_access_logic.query import review_query
from db.schema import Base


class PendingReview(BaseModel):
    # 同じものを二度タスクにしないための印
    key: str
    kind: str
    title: str
    detail: str


def gui_path(record: Base) -> str:
    """GUI(`gui/`)で開く場所"""
    return f"gui: /tables/{type(record).__tablename__}/{record.id}"


def todo_items(s: Session) -> list[PendingReview]:
    items = []
    for model in review_query.text_models():
        for record in s.scalars(review_query.todo_select(model)).all():
            lines = [line.strip() for name in model.TEXT_COLUMNS
                     for line in (getattr(record, name) or "").splitlines()
                     if review_query.TODO_MARK in line]
            items.append(PendingReview(
                key=f"todo:{model.__tablename__}:{record.id}",
                kind="TODO",
                title=f"TODO を片付ける: {model.__tablename__}「{label_of(model, record)}」",
                detail="\n".join([*lines, gui_path(record)]),
            ))
    return items
