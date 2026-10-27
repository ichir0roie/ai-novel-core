#!/usr/bin/env python3
"""`ContentBase.CHILD_LISTS` に挙げた子の行を、配列としてまるごと置き換える。来歴の行を一つだけ直すのは `changed_history`。

入口と GUI では、子の行は親への外部キーを持たない。来歴の行は id を持ち、渡されればその行に対応させる。id の無い行は、
今ある行と並びで対応させる(来歴・知る相手は鍵で対応させる)。
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from pydantic import BaseModel
from sqlalchemy import inspect as sa_inspect

from db.schema import (
    MANAGED_COLUMNS, Base, Character, CharacterHistory, CharacterSkillHistory, IdeaHistory, Location, LocationHistory,
)

Child = TypeVar("Child")
History = TypeVar("History", CharacterHistory, CharacterSkillHistory, IdeaHistory, LocationHistory)


def child_model(model: type, name: str) -> type:
    return sa_inspect(model).relationships[name].mapper.class_


def child_columns(model: type, name: str) -> list[str]:
    relationship = sa_inspect(model).relationships[name]
    foreign_keys = {remote.key for _, remote in relationship.local_remote_pairs}
    return [column.key for column in relationship.mapper.class_.__table__.columns
            if column.key != "id" and column.key not in foreign_keys and column.key not in MANAGED_COLUMNS]


def _write[Row](target: Row, row: BaseModel, skip: str | None = None) -> Row:
    # id は今ある行を指すのに使うだけで、行には書かない
    for name, value in row:
        if name not in (skip, "id"):
            setattr(target, name, value)
    return target


def _claimed[Row](current: Sequence[Row], rows: Sequence[BaseModel], table: str) -> dict[int, Row]:
    """`rows` が id で指した今ある行。今ある行に無い id、同じ id の二重指しは止める。"""
    ids = [row_id for row in rows if (row_id := getattr(row, "id", None)) is not None]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{table} の同じ id の行が二つ渡された")
    by_id = {getattr(existing, "id"): existing for existing in current}
    unknown = [row_id for row_id in ids if row_id not in by_id]
    if unknown:
        raise ValueError(f"{table} id={unknown} は、この行の子の行に無い")
    return {row_id: by_id[row_id] for row_id in ids}


def replaced_rows(current: Sequence[Child], rows: Sequence[BaseModel], child: type[Child]) -> list[Child]:
    """id を持つ行はその id の今ある行を、持たない行は、id で指されなかった今ある行を並びの順に使い回す(並びを変えなければ
    id が変わらない)。余った行は、返したリストで置き換えると消える。`rows` の欄は子の列と同じ名前で持つ(`CharacterParameterRow` など)。"""
    claimed = _claimed(current, rows, getattr(child, "__tablename__"))
    free = iter([existing for existing in current if getattr(existing, "id") not in claimed])
    replaced = []
    for row in rows:
        row_id = getattr(row, "id", None)
        target = claimed[row_id] if row_id is not None else next(free, None) or child()
        replaced.append(_write(target, row))
    return replaced


def _history_key(child: type, row: object) -> tuple[object, ...]:
    """今ある来歴の行と渡された行を対応させる鍵。人物・スキル・関係・場所の来歴は始まりの時刻、アイデアの履歴は効く場所と始まり。"""
    if child is IdeaHistory:
        return getattr(row, "location_id"), getattr(row, "start")
    return (getattr(row, "start"),)


def _replaced_knowers(current: Sequence[Child], rows: Sequence[BaseModel], child: type[Child]) -> list[Child]:
    """知る相手の行は、同じ人物・場所の今ある行だけを使い回す(位置で使い回すと、別の相手へ書き換える途中で
    `(来歴, knower_id)` の一意制約に当たる)。"""
    kept = {(getattr(knower, "knower_id"), getattr(knower, "location_id")): knower for knower in current}
    return [_write(kept.pop((getattr(row, "knower_id"), getattr(row, "location_id")), None) or child(), row)
            for row in rows]


def appended_history(row: BaseModel, child: type[History], owner: Character | Location | None = None) -> History:
    """来歴の行を一つ作る。今ある行には触れない(知る相手の既定は `replaced_histories` の新しい行と同じ)。"""
    return replaced_histories([], [row], child, owner)[0]


def replaced_histories(current: Sequence[History], rows: Sequence[BaseModel], child: type[History],
                       owner: Character | Location | None = None) -> list[History]:
    """来歴の行を置き換え、行の `knowers`(知る相手の行の配列)で知る相手を置き換える。
    id を持つ行は、その id の今ある行に対応させる。id の無い行は、id で指されなかった今ある行と、並びではなく鍵(`_history_key`)で
    対応させる(読み出しの入口は古い順に、relationship は新しい順に並べるので、並びで対応させると別の時刻の行を書き換えてしまう)。
    鍵の同じ行が幾つもあれば、その中では並びの順に対応させる。
    `knowers` を渡さない行は、今ある行に当たれば知る相手をそのままにし、当たらない新しい行なら `owner`(人物の来歴・
    スキルの来歴の本人、場所の来歴の場所)だけを知る相手にする(`owner` が無ければ行の無いまま)。余った今ある行は、返したリストで置き換えると消える。"""
    knower = child_model(child, "knowers")
    claimed = _claimed(current, rows, child.__tablename__)
    by_key: dict[tuple[object, ...], list[History]] = {}
    for existing in current:
        if existing.id not in claimed:
            by_key.setdefault(_history_key(child, existing), []).append(existing)
    replaced = []
    for row in rows:
        row_id = getattr(row, "id", None)
        same = [claimed[row_id]] if row_id is not None else by_key.get(_history_key(child, row))
        is_new = not same
        target = _write(same.pop(0) if same else child(), row, skip="knowers")
        # 知る相手の行の型は来歴の型ごとに違い、型を一つに決めて代入できないので、ほかの列と同じく setattr で書く
        knowers = getattr(row, "knowers")
        if knowers is not None:
            setattr(target, "knowers", _replaced_knowers(target.knowers, knowers, knower))
        elif is_new and isinstance(owner, Character):
            setattr(target, "knowers", [knower(knower=owner)])
        elif is_new and owner is not None:
            # 場所の来歴は、その場所に住む人物が知る
            setattr(target, "knowers", [knower(location_id=owner.id)])
        replaced.append(target)
    return replaced


def changed_history(target: Base, change: BaseModel) -> None:
    """来歴の行を一つだけ直す。`change` で渡された欄だけを書き、ほかの欄と同じ親のほかの行には触れない。
    `knowers` を渡せば知る相手をまるごと置き換え、渡さなければそのままにする。"""
    columns = type(target).__table__.columns
    for name in change.model_fields_set:
        if name != "id" and name in columns:
            setattr(target, name, getattr(change, name))
    knowers = getattr(change, "knowers", None)
    if knowers is not None:
        setattr(target, "knowers", _replaced_knowers(getattr(target, "knowers"), knowers, child_model(type(target), "knowers")))
