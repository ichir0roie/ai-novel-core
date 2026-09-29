#!/usr/bin/env python3
"""未確認のアイデア・ミームを一件ずつ出し、承認・非承認を付けて次へ進む。"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from data_access_logic.entrypoint import loading
from data_access_logic.label import label_of
from data_access_logic.material import Material
from data_access_logic.query import review_query
from db.schema import ConfirmStatus
from gui.api import records
from gui.api.models import ReviewNext, ReviewSummary, ReviewTable
from gui.api.tables import TABLES, TableSpec

REVIEW_TABLES: tuple[TableSpec, ...] = tuple(spec for spec in TABLES if spec.reviewable)


def review_spec(table: str) -> TableSpec:
    for spec in REVIEW_TABLES:
        if spec.name == table:
            return spec
    raise KeyError(f"レビューの対象でないテーブル: {table}")


def _count(s: Session, spec: TableSpec, status: ConfirmStatus) -> int:
    return s.scalar(
        select(func.count()).select_from(spec.model).where(spec.model.confirmed == status)) or 0


def summary(s: Session) -> ReviewSummary:
    return ReviewSummary(tables=[
        ReviewTable(table=spec.name, label=spec.label,
                    pending=_count(s, spec, ConfirmStatus.PENDING),
                    approved=_count(s, spec, ConfirmStatus.APPROVED),
                    rejected=_count(s, spec, ConfirmStatus.REJECTED))
        for spec in REVIEW_TABLES])


def next_pending(s: Session, spec: TableSpec, after: int = 0) -> ReviewNext:
    """`after` より後ろの id で最初の未確認。飛ばした(スキップした)ものは次に回るので、`after` に飛ばした id を渡す。"""
    model = spec.model
    remaining = _count(s, spec, ConfirmStatus.PENDING)
    row = s.scalar(loading(review_query.pending_select(model).where(model.id > after).limit(1), spec.record_model))
    if row is None and after:
        # 末尾まで飛ばしたら先頭に戻る
        row = s.scalar(loading(review_query.pending_select(model).limit(1), spec.record_model))
    if row is None:
        return ReviewNext(record=None, label=None, remaining=remaining)
    record = spec.record_model.model_validate(row)
    return ReviewNext(record=record.model_dump(mode="json"), label=label_of(model, row), remaining=remaining,
                      labels=records.reference_labels(s, spec, [record]),
                      related=records.related_of(s, record).model_dump(mode="json"))


def decide(s: Session, spec: TableSpec, record_id: int, decision: ConfirmStatus,
           changes: dict[str, Any]) -> Material:
    # 画面は直しの欄から確認(confirmed)を外して送り、ボタンで選んだ判定を別に渡す
    return spec.updater(spec.update_form(id=record_id, confirmed=decision, **changes)).execute(s)
