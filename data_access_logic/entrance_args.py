"""JSON で来た引数(dict)から入口を組み立てる。API(`gui/api/interface.py`)とバッチ(`batch.run_batch.RunBatch`)が使う。"""
from __future__ import annotations

import inspect
import typing
from functools import cache
from typing import Any

from pydantic import BaseModel, TypeAdapter

from data_access_logic.entrypoint import Entrypoint


def _has_model(annotation: Any) -> bool:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return True
    return any(_has_model(argument) for argument in typing.get_args(annotation))


@cache
def _signature(cls: type[Entrypoint]) -> tuple[inspect.Signature, dict[str, TypeAdapter]]:
    """引数の signature と、型が pydantic のモデルの引数を読み込む TypeAdapter。"""
    hints = typing.get_type_hints(cls.__init__)
    return inspect.signature(cls), {name: TypeAdapter(hint) for name, hint in hints.items() if _has_model(hint)}


def built[E: Entrypoint](cls: type[E], args: dict[str, Any]) -> E:
    """引数を入口の signature に当て、型が pydantic のモデルの引数はモデルに読み込んでから組み立てる。
    引数の食い違いは ValueError にする(API は 400)。"""
    signature, adapters = _signature(cls)
    try:
        signature.bind(**args)
    except TypeError as error:
        raise ValueError(f"{cls.__module__.removeprefix('data_access_logic.')}.{cls.__name__} の引数が合わない: {error}") from error
    return cls(**{name: adapters[name].validate_python(value) if name in adapters else value for name, value in args.items()})
