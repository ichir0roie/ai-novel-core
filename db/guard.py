#!/usr/bin/env python3
"""書き手(`db/writer.py`)ごとの守りと、展開の中で変えた行の記録。

行の書き込みのたびに SQLAlchemy の mapper の事象(足す・直す・消す)で走るので、入口ごとに守りを書かなくても、
来歴の配列をまるごと置き換える入口や、親を消して子が連れて消える場合まで同じに守る。
`delete(...)` / `update(...)` の一括の書き込みは mapper の事象を通らないので、`do_orm_execute` で当たる行を引いて守る。

- 作者(`user`): どの行も直せる。足した行の出自は `user`(AI の生成の流れの中なら `ai`)。AI の行を直すと、その行は作者の行になる
- 作者モード(`ai`): 出自 `ai` の行だけを直せる・消せる。作品・話・書き方など、AI に書かせない表には触れない
- 人物モード(`ai_append`): 足すことと、`end` で終わりを付けることだけ(同じトランザクションで足した行を整えるのは、足すことに数える)
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import Column, Numeric, event, insert, select
from sqlalchemy.orm import ORMExecuteState, Session, object_session
from sqlalchemy.orm.base import NO_VALUE
from sqlalchemy import inspect as sa_inspect

from db.schema import (
    TIMESTAMP_COLUMNS, Base, ChangeOp, ExpansionChange, Origin, OriginMixin, StampType,
)
from db.stamp import Stamp
from db.writer import Writer, current

# AI の書き手が足す・直す・消すことのできない表。筋は出来事で持ち、話・作品は作者だけが作る
AI_FORBIDDEN_TABLES = frozenset({
    "story", "episode", "episode_character", "oracle", "style_preference", "narou_part", "personality_level",
})
# 守りも記録もしない表(本文から作り直す派生と、展開の記録そのもの)
UNGUARDED_TABLES = frozenset({"event_summary", "expansion", "expansion_change", "expansion_conflict"})
# 人物モードが直してよい列。終わりを付ける(空なら時刻を入れ、入っていればそれより前に早める)ことだけを許す
APPENDABLE_COLUMN = "end"
# このトランザクションで足した行を、セッションの info に持つ鍵
_INSERTED_KEY = "guard_inserted"


class ProtectedRowError(PermissionError):
    pass


def _label(target: Base) -> str:
    return f"{target.__tablename__} id={target.id}"


def _jsonable(value: Any) -> Any:
    if isinstance(value, Stamp):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    return value


def restored_value(column: Column, value: Any) -> Any:
    """`before` に控えた値を、列に書ける値に戻す(`_jsonable` の逆)。"""
    if value is None:
        return None
    if isinstance(column.type, StampType):
        return Stamp.parse(value)
    if isinstance(column.type, Numeric):
        return Decimal(value)
    return value


def _old(target: Base, key: str) -> Any:
    """直す前の値。この flush で変えた列は変える前の値、ほかは今の値。読み込んでいない列は NO_VALUE。"""
    state = sa_inspect(target)
    if key in state.committed_state:
        return state.committed_state[key]
    return state.dict.get(key, NO_VALUE)


def _snapshot(connection, target: Base) -> dict[str, Any]:
    """直す・消す前の行の列の値。読み込んでいない列は、まだ書き換える前の db の行から読む。"""
    olds = {column.key: _old(target, column.key) for column in target.__table__.columns
            if column.key not in TIMESTAMP_COLUMNS}
    if NO_VALUE in olds.values():
        table = target.__table__
        stored = connection.execute(select(table).where(table.c.id == target.id)).mappings().one()
        olds = {key: stored[key] if value is NO_VALUE else value for key, value in olds.items()}
    return {key: _jsonable(value) for key, value in olds.items()}


def _changes(target: Base) -> dict[str, tuple[Any, Any]]:
    """この flush で値の変わった列(同じ値を入れ直しただけの列は入れない)。"""
    state = sa_inspect(target)
    changed = {}
    for column in target.__table__.columns:
        key = column.key
        if key in TIMESTAMP_COLUMNS or key not in state.committed_state:
            continue
        old, new = state.committed_state[key], state.dict.get(key)
        if old is NO_VALUE or old != new:
            changed[key] = (old, new)
    return changed


def _log(connection, target: Base, op: ChangeOp) -> None:
    """展開の id が立っていれば、変えた行を記録する。直す・消す行は、変える前の値を `before` に控える。"""
    expansion_id = current().expansion_id
    if expansion_id is None or target.__tablename__ in UNGUARDED_TABLES:
        return
    before = None if op is ChangeOp.ADD else _snapshot(connection, target)
    connection.execute(insert(ExpansionChange).values(
        expansion_id=expansion_id, table_name=target.__tablename__, row_id=target.id, op=op.value, before=before))


def _check_ai_table(target: Base, action: str) -> None:
    """`action` は「足せない」「直せない」「消せない」。"""
    table = target.__tablename__
    if table in AI_FORBIDDEN_TABLES or not isinstance(target, OriginMixin):
        raise ProtectedRowError(f"AI の書き手は {table} の行を{action}")


def _before_insert(_mapper, _connection, target: Base) -> None:
    if target.__tablename__ in UNGUARDED_TABLES:
        return
    state = current()
    if state.by_ai:
        _check_ai_table(target, "足せない")
    if isinstance(target, OriginMixin) and not state.restoring:
        target.origin = (Origin.AI if state.by_ai or state.generated else Origin.USER).value


def _inserted(target: Base) -> set[tuple[str, int]]:
    """このトランザクションで足した行。足した直後にその行を整える(親を結ぶ・終わりを入れる)のは、足すことのうちに数える。"""
    session = object_session(target)
    return set() if session is None else session.info.setdefault(_INSERTED_KEY, set())


def _forget_inserted(session: Session, *_args) -> None:
    session.info.pop(_INSERTED_KEY, None)


def _after_insert(_mapper, connection, target: Base) -> None:
    _inserted(target).add((target.__tablename__, target.id))
    _log(connection, target, ChangeOp.ADD)


def _check_append(target: Base, changes: dict[str, tuple[Any, Any]]) -> None:
    if set(changes) != {APPENDABLE_COLUMN}:
        raise ProtectedRowError(
            f"人物モードは {_label(target)} の {', '.join(sorted(changes))} を直せない(end で終わりを付けることだけ)")
    old, new = (Stamp.parse(value) for value in changes[APPENDABLE_COLUMN])
    # 没年まで続く居場所の行のように、先に入っている end より前で終えるのは、終わりを付けることに数える
    if new is None or (old is not None and not new < old):
        raise ProtectedRowError(f"人物モードは {_label(target)} の end を空に戻したり先へ延ばしたりできない")
    start = getattr(target, "start", None)
    if isinstance(start, Stamp) and new < start:
        raise ProtectedRowError(f"{_label(target)} の end を start より前にはできない")


def _before_update(_mapper, connection, target: Base) -> None:
    if target.__tablename__ in UNGUARDED_TABLES:
        return
    changes = _changes(target)
    state = current()
    if isinstance(target, OriginMixin) and "origin" in changes and not state.restoring:
        # 出自は守りだけが決める(入口・画面から渡された値は使わない)
        old = changes.pop("origin")[0]
        target.origin = _snapshot(connection, target)["origin"] if old is NO_VALUE else old
    if not changes or state.restoring:
        return
    if state.writer is Writer.AI_APPEND:
        _check_ai_table(target, "直せない")
        if (target.__tablename__, target.id) not in _inserted(target):
            _check_append(target, changes)
    elif state.by_ai:
        _check_ai_table(target, "直せない")
        if getattr(target, "origin", None) == Origin.USER:
            raise ProtectedRowError(f"AI の書き手は作者の行 {_label(target)} を直せない")
    elif isinstance(target, OriginMixin) and target.origin == Origin.AI and not state.generated:
        target.origin = Origin.USER.value
    _log(connection, target, ChangeOp.UPDATE)


def _check_ai_delete(target: Base) -> None:
    state = current()
    if not state.by_ai or target.__tablename__ in UNGUARDED_TABLES:
        return
    _check_ai_table(target, "消せない")
    if state.writer is Writer.AI_APPEND:
        raise ProtectedRowError(f"人物モードは {_label(target)} を消せない")
    if getattr(target, "origin", None) == Origin.USER:
        raise ProtectedRowError(f"AI の書き手は作者の行 {_label(target)} を消せない")


def _before_delete(_mapper, connection, target: Base) -> None:
    _check_ai_delete(target)
    _log(connection, target, ChangeOp.DELETE)


def _bulk(execute_state: ORMExecuteState) -> None:
    """`delete(...)` / `update(...)` の一括の書き込みを、当たる行ごとに守って記録する。"""
    if not (execute_state.is_delete or execute_state.is_update):
        return
    state = current()
    mapper = execute_state.bind_mapper
    if mapper is None or (not state.by_ai and state.expansion_id is None):
        return
    model = mapper.class_
    if model.__tablename__ in UNGUARDED_TABLES:
        return
    if state.by_ai and execute_state.is_update:
        raise ProtectedRowError(f"AI の書き手は {model.__tablename__} の行を一括では直せない")
    statement = execute_state.statement
    session = execute_state.session
    rows = session.scalars(select(model).where(statement.whereclause)).all()  # type: ignore[attr-defined]
    for row in rows:
        _check_ai_delete(row)
        _log(session.connection(), row, ChangeOp.DELETE if execute_state.is_delete else ChangeOp.UPDATE)


def install() -> None:
    event.listen(Base, "before_insert", _before_insert, propagate=True)
    event.listen(Base, "after_insert", _after_insert, propagate=True)
    event.listen(Base, "before_update", _before_update, propagate=True)
    event.listen(Base, "before_delete", _before_delete, propagate=True)
    event.listen(Session, "do_orm_execute", _bulk)
    event.listen(Session, "after_commit", _forget_inserted)
    event.listen(Session, "after_soft_rollback", _forget_inserted)
