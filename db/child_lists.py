#!/usr/bin/env python3
"""`ContentBase.CHILD_LISTS` に挙げた子の行を、配列としてまるごと置き換える。

入口と GUI では、子の行は id と親への外部キーを持たない。今ある行とは並びで対応させる(来歴・知る相手は鍵で対応させる)。
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from pydantic import BaseModel
from sqlalchemy import inspect as sa_inspect

from db.schema import Character, CharacterHistory, CharacterSkillHistory, IdeaHistory

Child = TypeVar("Child")
History = TypeVar("History", CharacterHistory, CharacterSkillHistory, IdeaHistory)


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


def _history_key(child: type, row: object) -> tuple[object, ...]:
    """今ある来歴の行と渡された行を対応させる鍵。人物・スキルの来歴は一年に一行なので年、アイデアの履歴は効く場所と始まり。"""
    if child is IdeaHistory:
        return getattr(row, "location_id"), getattr(row, "start")
    return (getattr(row, "start"),)


def _replaced_knowers(current: Sequence[Child], rows: Sequence[BaseModel], child: type[Child]) -> list[Child]:
    """知る相手の行は、同じ人物・場所の今ある行だけを使い回す(位置で使い回すと、別の相手へ書き換える途中で
    `(来歴, knower_id)` の一意制約に当たる)。"""
    kept = {(getattr(knower, "knower_id"), getattr(knower, "location_id")): knower for knower in current}
    replaced = []
    for row in rows:
        target = kept.pop((getattr(row, "knower_id"), getattr(row, "location_id")), None) or child()
        for name, value in row:
            setattr(target, name, value)
        replaced.append(target)
    return replaced


def replaced_histories(current: Sequence[History], rows: Sequence[BaseModel], child: type[History],
                       owner: Character | None = None) -> list[History]:
    """来歴の行を置き換え、行の `knowers`(知る相手の行の配列)で知る相手を置き換える。
    今ある行とは、並びではなく鍵(`_history_key`)で対応させる(読み出しの入口は古い順に、relationship は新しい順に並べるので、
    並びで対応させると別の年の行を書き換えてしまう)。鍵の同じ行が幾つもあれば、その中では並びの順に対応させる。
    `knowers` を渡さない行は、今ある行に当たれば知る相手をそのままにし、当たらない新しい行なら `owner`(人物の来歴・
    スキルの来歴の本人)だけを知る相手にする(`owner` が無ければ行の無いまま)。余った今ある行は、返したリストで置き換えると消える。"""
    knower = child_model(child, "knowers")
    by_key: dict[tuple[object, ...], list[History]] = {}
    for existing in current:
        by_key.setdefault(_history_key(child, existing), []).append(existing)
    replaced = []
    for row in rows:
        same = by_key.get(_history_key(child, row))
        target = same.pop(0) if same else None
        is_new = target is None
        if target is None:
            target = child()
        for name, value in row:
            if name != "knowers":
                setattr(target, name, value)
        # 知る相手の行の型は来歴の型ごとに違い、型を一つに決めて代入できないので、ほかの列と同じく setattr で書く
        knowers = getattr(row, "knowers")
        if knowers is not None:
            setattr(target, "knowers", _replaced_knowers(target.knowers, knowers, knower))
        elif is_new and owner is not None:
            setattr(target, "knowers", [knower(knower=owner)])
        replaced.append(target)
    return replaced
