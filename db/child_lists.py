#!/usr/bin/env python3
"""`ContentBase.CHILD_LISTS` に挙げた子の行を、配列としてまるごと置き換える。

入口と GUI では、子の行は id と親への外部キーを持たない(行は配列の並びで決まる)。
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from pydantic import BaseModel
from sqlalchemy import inspect as sa_inspect

from db.schema import Character, CharacterHistory, CharacterHistoryCharacter, IdeaHistory, IdeaHistoryCharacter

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
    """来歴の行を `replaced_rows` と同じく置き換え、行の `knower_ids` で知る人を置き換える。
    `knower_ids` を渡さない行は、今ある行なら知る人をそのままにし、新しい行なら `owner`(人物の来歴の本人)だけを知る人にする。"""
    replaced = []
    for index, row in enumerate(rows):
        target = current[index] if index < len(current) else child()
        for name, value in row:
            if name != "knower_ids":
                setattr(target, name, value)
        knower_ids = getattr(row, "knower_ids")
        if knower_ids is not None:
            _set_knowers(target, list(dict.fromkeys(knower_ids)))
        elif index >= len(current) and owner is not None:
            _set_knowers(target, [owner])
        replaced.append(target)
    return replaced


def _set_knowers(history: CharacterHistory | IdeaHistory, knowers: Sequence[int | Character]) -> None:
    """残る人の行を使い回す(消して足し直すと、同じ組の挿入が削除より先に走って一意制約に当たる)。
    まだ id の無い人物(足している最中の本人)は行そのもので渡す。"""
    def kept_or_new[Knower: (CharacterHistoryCharacter, IdeaHistoryCharacter)](
            current: Sequence[Knower], model: type[Knower]) -> list[Knower]:
        by_id = {knower.character_id: knower for knower in current}
        return [model(character=knower) if isinstance(knower, Character) else by_id.get(knower) or model(character_id=knower)
                for knower in knowers]
    if isinstance(history, CharacterHistory):
        history.knowers = kept_or_new(history.knowers, CharacterHistoryCharacter)
    else:
        history.knowers = kept_or_new(history.knowers, IdeaHistoryCharacter)
