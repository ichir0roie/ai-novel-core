"""展開の記録が指す行(表の名前と id)を引く。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import UnknownRecordError
from db.schema import Base, OriginMixin


def model_of(table_name: str) -> type[Base]:
    for mapper in Base.registry.mappers:
        if mapper.class_.__tablename__ == table_name:
            return mapper.class_
    raise UnknownRecordError(f"表が無い: {table_name}")


def user_row(s: Session, table_name: str, row_id: int) -> Base:
    """作者の行。食い違いは作者の行にだけ残す(AI の行は展開が直せる)。"""
    model = model_of(table_name)
    row = s.get(model, row_id)
    if row is None:
        raise UnknownRecordError(f"id={row_id} の {table_name} が見つからない")
    if not isinstance(row, OriginMixin) or row.origin != "user":
        raise ValueError(f"{table_name} id={row_id} は作者の行でない。AI の行の食い違いは、展開の中で直す")
    return row
