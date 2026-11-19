#!/usr/bin/env python3
"""db だけを読み書きする一段。API(`POST /api/steps/{id}`)が一つのトランザクションで回す。

流れ(`data_access_logic/flows/`)は db に触る所だけをこの段で呼ぶ(`data_access_logic/caller.py`)。手元では自分のセッションで回し、
db に繋がない web のセッションでは API に頼む。
段は `(s: Session, 入力のモデル) -> 出力` か `(s: Session) -> 出力` の関数に `@db_step` を付けて、
`data_access_logic/<領域>/steps.py` に置く。id は `<領域>.steps.<関数名>`。
入力も出力も pydantic のモデル(出力は一覧・数・None でもよい)にし、型注釈から JSON を読み書きする。
"""
from __future__ import annotations

import importlib
import inspect
import typing
from collections.abc import Callable
from functools import cache
from typing import Any

from pydantic import BaseModel, TypeAdapter

from data_access_logic.entrypoint import UnknownRecordError
from db.schema import get_env_session
from db.stamp import using_calendar

_STEPS: dict[str, Callable[..., Any]] = {}


class RowId(BaseModel):
    """一つの行を指す、段の入力。"""

    id: int


class RowIds(BaseModel):
    ids: list[int]


def step_id(step: Callable[..., Any]) -> str:
    return f"{step.__module__.removeprefix('data_access_logic.')}.{step.__name__}"


def db_step[F: Callable[..., Any]](step: F) -> F:
    _STEPS[step_id(step)] = step
    return step


def step_of(id_: str) -> Callable[..., Any]:
    """登録した段だけを返す(API に、段でない関数を呼ばせない)。"""
    module_name, _, _ = id_.rpartition(".")
    if not module_name.endswith(".steps"):
        raise UnknownRecordError(f"段が無い: {id_}")
    module = f"data_access_logic.{module_name}"
    try:
        importlib.import_module(module)
    except ModuleNotFoundError as error:
        # 段のモジュールそのものが無いときだけ。中で他の import が落ちたのは実装の誤りなので通す
        if error.name is None or not module.startswith(error.name):
            raise
        raise UnknownRecordError(f"段が無い: {id_}") from error
    step = _STEPS.get(id_)
    if step is None:
        raise UnknownRecordError(f"段が無い: {id_}")
    return step


# 型注釈の読み取りと TypeAdapter は重いので、段ごとに一度だけ作る

@cache
def form_adapter(step: Callable[..., Any]) -> TypeAdapter | None:
    """入力のモデルを読む TypeAdapter。入力を取らない段は None。"""
    parameters = list(inspect.signature(step).parameters)
    if len(parameters) < 2:
        return None
    return TypeAdapter(typing.get_type_hints(step)[parameters[1]])


@cache
def output_adapter(step: Callable[..., Any]) -> TypeAdapter:
    return TypeAdapter(typing.get_type_hints(step)["return"])


def run[Out](step: Callable[..., Out], form: Any = None) -> Out:
    """段を一つのトランザクションで回す(API と、手元の流れの `caller.call`)。手元の流れは、流れを始めた入口の作品の文脈
    (`db/story_scope.py`)のまま回る。"""
    with get_env_session() as s, s.begin():
        return step(s) if form_adapter(step) is None else step(s, form)


def run_json(id_: str, body: Any, story_id: int | None = None, story_given: bool = False) -> Any:
    """API から。JSON の入力を型注釈のモデルに読み、結果を JSON にして返す。入力と結果の時刻は暦に依らない西暦の表記で運ぶ
    (`web_session/api.call`)。段そのものは、web のセッションが運んだ流れの作品(`story_given`。作品が無いことも含む)の文脈で
    回す(手元の流れが段を流れの作品のまま回すのと揃える)。運ばれなければ、入力から決めた作品で回す。"""
    from data_access_logic.story.scope import args_scope, story_scope_of

    step = step_of(id_)
    given = form_adapter(step)
    with using_calendar(None):
        form = None if given is None else given.validate_python(body)
    scope = story_scope_of(story_id) if story_given else args_scope(body if isinstance(body, dict) else {}, story_id)
    with scope:
        result = run(step, form)
    with using_calendar(None):
        return output_adapter(step).dump_python(result, mode="json")
