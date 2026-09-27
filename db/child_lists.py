#!/usr/bin/env python3
"""`TextBase.CHILD_LISTS` に挙げた子の行を、辞書の配列として出し入れする。

確定・修正の入口と GUI の API がこれを通す。辞書には id と親への外部キーを持たせない
(行は配列の並びで決まる)。
"""
from __future__ import annotations

from sqlalchemy import inspect as sa_inspect

from db.schema import StampType
from db.stamp import Stamp


class ChildListError(ValueError):
    pass


def child_model(model: type, name: str) -> type:
    return sa_inspect(model).relationships[name].mapper.class_


def child_columns(model: type, name: str) -> list[str]:
    relationship = sa_inspect(model).relationships[name]
    foreign_keys = {remote.key for _, remote in relationship.local_remote_pairs}
    return [column.key for column in relationship.mapper.class_.__table__.columns
            if column.key != "id" and column.key not in foreign_keys]


def dump_children(record, name: str) -> list[dict]:
    columns = child_columns(type(record), name)
    return [{column: getattr(row, column) for column in columns} for row in getattr(record, name)]


def load_children(record, name: str, items) -> None:
    """同じ位置にある既存の行を使い回す(並びを変えなければ id が変わらない)。余った行は消える。"""
    model = type(record)
    child = child_model(model, name)
    columns = child_columns(model, name)
    stamp_columns = {column for column in columns
                     if isinstance(child.__table__.columns[column].type, StampType)}
    if not isinstance(items, list):
        raise ChildListError(f"{name} は配列で渡す: {items!r}")

    existing = list(getattr(record, name))
    rows = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ChildListError(f"{name}[{index}] は辞書で渡す: {item!r}")
        unknown = set(item) - set(columns)
        if unknown:
            raise ChildListError(f"{name}[{index}]: {child.__tablename__} のスキーマに無い欄 {sorted(unknown)}")
        values = {column: item.get(column) for column in columns}
        for column in stamp_columns:
            values[column] = Stamp.parse(values[column])
        validate = getattr(child, "validate", None)
        if validate is not None:
            validate(values)
        row = existing[index] if index < len(existing) else child()
        for column, value in values.items():
            setattr(row, column, value)
        rows.append(row)
    setattr(record, name, rows)
