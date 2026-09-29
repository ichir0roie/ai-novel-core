#!/usr/bin/env python3
"""`TextBase.CHILD_LISTS` に挙げた子の行を、配列としてまるごと置き換える。

入口と GUI では、子の行は id と親への外部キーを持たない(行は配列の並びで決まる)。
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from pydantic import BaseModel
from sqlalchemy import inspect as sa_inspect

Child = TypeVar("Child")


def child_model(model: type, name: str) -> type:
    return sa_inspect(model).relationships[name].mapper.class_


def child_columns(model: type, name: str) -> list[str]:
    relationship = sa_inspect(model).relationships[name]
    foreign_keys = {remote.key for _, remote in relationship.local_remote_pairs}
    return [column.key for column in relationship.mapper.class_.__table__.columns
            if column.key != "id" and column.key not in foreign_keys]


def replaced_rows(current: Sequence[Child], rows: Sequence[BaseModel], child: type[Child]) -> list[Child]:
    """同じ位置にある既存の行を使い回す(並びを変えなければ id が変わらない)。余った行は、返したリストで置き換えると消える。
    `rows` の欄は子の列と同じ名前で持つ(`CharacterParameterRow` など)。"""
    replaced = []
    for index, row in enumerate(rows):
        target = current[index] if index < len(current) else child()
        for name, value in row:
            setattr(target, name, value)
        replaced.append(target)
    return replaced
