#!/usr/bin/env python3
"""`ContentBase.CHILD_LISTS` に挙げた子の行を、配列としてまるごと置き換える。

入口と GUI では、子の行は id と親への外部キーを持たない(行は配列の並びで決まる)。
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from pydantic import BaseModel
from sqlalchemy import inspect as sa_inspect

from db.schema import Character, CharacterHistory, CharacterHistoryKnower, IdeaHistory, IdeaHistoryKnower

Child = TypeVar("Child")
History = TypeVar("History", CharacterHistory, IdeaHistory)


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


def replaced_histories(current: Sequence[History], rows: Sequence[BaseModel], child: type[History],
                       owner: Character | None = None) -> list[History]:
    """来歴の行を `replaced_rows` と同じく置き換え、行の `knowers`(知る相手の行の配列)で知る相手を置き換える。
    `knowers` を渡さない行は、今ある行なら知る相手をそのままにし、新しい行なら `owner`(人物の来歴の本人)だけを知る相手にする。"""
    replaced = []
    for index, row in enumerate(rows):
        target = current[index] if index < len(current) else child()
        for name, value in row:
            if name != "knowers":
                setattr(target, name, value)
        knowers = getattr(row, "knowers")
        if isinstance(target, CharacterHistory):
            if knowers is not None:
                target.knowers = replaced_rows(target.knowers, knowers, CharacterHistoryKnower)
            elif index >= len(current) and owner is not None:
                target.knowers = [CharacterHistoryKnower(knower=owner)]
        elif knowers is not None:
            target.knowers = replaced_rows(target.knowers, knowers, IdeaHistoryKnower)
        replaced.append(target)
    return replaced
