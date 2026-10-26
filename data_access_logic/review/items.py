#!/usr/bin/env python3
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.orm import Session

from data_access_logic.expansion.rows import model_of
from data_access_logic.label import label_of
from data_access_logic.query import expansion_query, review_query
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


def conflict_items(s: Session) -> list[PendingReview]:
    """世界の展開が残した、作者の行との食い違い(`expansion_conflict`)。"""
    items = []
    for conflict in s.scalars(expansion_query.open_conflicts_select()).all():
        model = model_of(conflict.table_name)
        row = s.get(model, conflict.row_id)
        label = conflict.table_name if row is None else f"{conflict.table_name}「{label_of(model, row)}」"
        detail = [conflict.detail]
        if conflict.proposal:
            detail.append(f"案: {conflict.proposal}")
        detail.append(f"展開 id={conflict.expansion_id} の食い違い id={conflict.id}"
                      "(受けたら作者の手で直し、ResolveConflict で accepted に。捨てるなら dismissed に)")
        if row is not None:
            detail.append(gui_path(row))
        items.append(PendingReview(
            key=f"conflict:{conflict.id}", kind="食い違い", title=f"展開との食い違いを決める: {label}",
            detail="\n".join(detail)))
    return items


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
