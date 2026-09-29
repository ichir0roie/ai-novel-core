#!/usr/bin/env python3
"""`data_access_logic/<領域>/` の入口を API から呼ぶ。

入口の一覧は import 時にディレクトリを歩いて集める(`data_access_logic/readme.md` の表と同じ「領域.ファイル.クラス」で呼ぶ)。
`claude -p` を回すもの(確定のあとに AI を回す `run()` を持つ入口、AI を受け取る入口)は
`claude=True` にし、Claude Code の環境でだけ、裏の job として走らせる。
"""
from __future__ import annotations

import importlib
import inspect
import os
import typing
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, TypeAdapter

import data_access_logic
from data_access_logic.entrypoint import CommitEntrypoint, Entrypoint, RandomDraft, SessionEntrypoint

# `result()` を上書きしていない(= 確定のあとに AI を回さない)基底
_PLAIN_RESULTS = {SessionEntrypoint.result, CommitEntrypoint.result, RandomDraft.result}



@dataclass(frozen=True)
class Param:
    name: str
    required: bool
    default: Any
    annotation: str


@dataclass(frozen=True)
class Entrance:
    id: str          # 例: location.list_places.ListPlaces
    area: str
    name: str
    doc: str
    params: tuple[Param, ...]
    claude: bool     # claude コマンドを叩く(裏の job として、Claude Code の環境でだけ走る)
    writes: bool     # db に書く
    target: type[Entrypoint]


def _jsonable_default(value: Any) -> Any:
    if value is inspect.Parameter.empty:
        return None
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _params(callable_: Callable) -> tuple[Param, ...]:
    params = []
    for parameter in inspect.signature(callable_).parameters.values():
        if parameter.name in ("self", "ai"):
            continue
        if parameter.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        annotation = parameter.annotation
        params.append(Param(
            name=parameter.name, required=parameter.default is inspect.Parameter.empty,
            default=_jsonable_default(parameter.default),
            annotation="" if annotation is inspect.Parameter.empty else str(annotation).replace("typing.", "")))
    return tuple(params)


def _doc(obj) -> str:
    doc = inspect.getdoc(obj) or ""
    return doc.strip().splitlines()[0] if doc.strip() else ""


def _uses_claude(cls: type) -> bool:
    if cls.result not in _PLAIN_RESULTS:
        return True
    return "ai" in inspect.signature(cls.__init__).parameters


def _collect_interface() -> list[Entrance]:
    """`data_access_logic/<領域>/*.py` を歩き、そのファイルで定義した入口のクラスを拾う。領域のディレクトリは
    `__init__.py` を持たない(名前空間パッケージ)ので、pkgutil ではなくファイルを直接見る。"""
    found = []
    root = next(iter(data_access_logic.__path__))
    for area_name in sorted(os.listdir(root)):
        area_dir = os.path.join(root, area_name)
        if area_name.startswith(("_", ".")) or not os.path.isdir(area_dir):
            continue
        for filename in sorted(os.listdir(area_dir)):
            if not filename.endswith(".py") or filename.startswith("_"):
                continue
            module_name = filename[:-3]
            module = importlib.import_module(f"data_access_logic.{area_name}.{module_name}")
            for name, cls in inspect.getmembers(module, inspect.isclass):
                if cls.__module__ != module.__name__ or not issubclass(cls, Entrypoint):
                    continue
                found.append(Entrance(
                    id=f"{area_name}.{module_name}.{name}", area=area_name, name=name,
                    doc=_doc(cls) or _doc(module), params=_params(cls.__init__),
                    claude=_uses_claude(cls), writes=issubclass(cls, CommitEntrypoint) or _uses_claude(cls),
                    target=cls))
    return found


ENTRANCES: dict[str, Entrance] = {
    entrance.id: entrance for entrance in sorted(_collect_interface(), key=lambda e: e.id)}


def entrance_of(entrance_id: str) -> Entrance:
    entrance = ENTRANCES.get(entrance_id)
    if entrance is None:
        raise KeyError(f"入口が無い: {entrance_id}")
    return entrance


def _style_defaults(args: dict[str, Any], params: tuple[Param, ...]) -> dict[str, Any]:
    """世界リポジトリの `instructions/style.py` があれば、渡されていない文体の引数をそこから埋める。
    `core` は汎用の仕組みなので値は持たない(無ければ空のまま)。"""
    names = {param.name for param in params}
    wanted = {"shared_style_extra": "SHARED_EXTRA", "style_extra": "EPISODE_STYLE_EXTRA"}
    if not any(name in names and name not in args for name in wanted):
        return args
    try:
        style = importlib.import_module("instructions.style")
    except ImportError:
        return args
    filled = dict(args)
    for name, constant in wanted.items():
        if name in names and name not in filled and hasattr(style, constant):
            filled[name] = getattr(style, constant)
    return filled


def _has_model(annotation: Any) -> bool:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return True
    return any(_has_model(argument) for argument in typing.get_args(annotation))


def prepare(entrance: Entrance, args: dict[str, Any]) -> dict[str, Any]:
    """JSON で来た引数を入口の signature に当て、型が pydantic のモデルの引数はモデルに読み込む。
    食い違いは ValueError にして 400 へ(裏の job にする前に確かめる)。"""
    args = _style_defaults(args, entrance.params)
    target = entrance.target
    try:
        inspect.signature(target).bind(**args)
    except TypeError as error:
        raise ValueError(f"{entrance.id} の引数が合わない: {error}") from error
    hints = typing.get_type_hints(target.__init__)
    return {name: TypeAdapter(hints[name]).validate_python(value) if name in hints and _has_model(hints[name]) else value
            for name, value in args.items()}


def call(entrance: Entrance, arguments: dict[str, Any]) -> Any:
    """`prepare` した引数で入口を組み立てて `run()` を呼ぶ(dump 済みの結果)。"""
    return entrance.target(**arguments).run()
