#!/usr/bin/env python3
"""db だけを読み書きする一段。API(`POST /api/steps/{id}`)が一つのトランザクションで回す。

web のセッション(`web_session/`)は db に繋がないので、流れと AI(`claude -p`)を自分で持ち、db に触る所だけをこの段で API に頼む。
段は `(s: Session, 入力のモデル) -> 出力` か `(s: Session) -> 出力` の関数に `@db_step` を付けて、
`data_access_logic/<領域>/steps.py` に置く。id は `<領域>.steps.<関数名>`。
入力も出力も pydantic のモデル(出力は一覧・数・None でもよい)にし、型注釈から JSON を読み書きする。
"""
from __future__ import annotations

import importlib
import inspect
import typing
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, TypeAdapter

from db.schema import get_env_session

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
        raise KeyError(f"段が無い: {id_}")
    importlib.import_module(f"data_access_logic.{module_name}")
    step = _STEPS.get(id_)
    if step is None:
        raise KeyError(f"段が無い: {id_}")
    return step


def form_type(step: Callable[..., Any]) -> Any | None:
    """入力のモデルの型。入力を取らない段は None。"""
    parameters = list(inspect.signature(step).parameters)
    if len(parameters) < 2:
        return None
    return typing.get_type_hints(step)[parameters[1]]


def output_type(step: Callable[..., Any]) -> Any:
    return typing.get_type_hints(step)["return"]


def run(step: Callable[..., Any], form: Any) -> Any:
    with get_env_session() as s, s.begin():
        return step(s) if form_type(step) is None else step(s, form)


def run_json(id_: str, body: Any) -> Any:
    """API から。JSON の入力を型注釈のモデルに読み、結果を JSON にして返す。"""
    step = step_of(id_)
    given = form_type(step)
    form = None if given is None else TypeAdapter(given).validate_python(body)
    return TypeAdapter(output_type(step)).dump_python(run(step, form), mode="json")
