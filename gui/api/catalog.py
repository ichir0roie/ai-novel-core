#!/usr/bin/env python3
"""入口(`data_access_logic/<領域>/*.py`)を歩いて、引数・説明・claude を叩くかを読む。

API と web のセッションはこれを使わず、`gui/api/interface.py` の固定の一覧で入口を引く。ここを使うのは、画面の入口の一覧
(`gui/web/lib/entrances.json`)を書き出す `gui/api/dump_static.py` と、固定の一覧がコードとずれていないかを見るテストだけ。
"""
from __future__ import annotations

import importlib
import inspect
import os
from typing import Any, Callable

import data_access_logic
from data_access_logic.entrypoint import CommitEntrypoint, Entrypoint, RandomDraft, SessionEntrypoint
from gui.api.models import EntranceMeta, EntranceParam

# `result()` を上書きしていない(= 確定のあとに AI を回さない)基底
_PLAIN_RESULTS = {SessionEntrypoint.result, CommitEntrypoint.result, RandomDraft.result}


def _jsonable_default(value: Any) -> Any:
    if value is inspect.Parameter.empty:
        return None
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _params(callable_: Callable) -> list[EntranceParam]:
    params = []
    for parameter in inspect.signature(callable_).parameters.values():
        if parameter.name in ("self", "ai"):
            continue
        if parameter.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        annotation = parameter.annotation
        params.append(EntranceParam(
            name=parameter.name, required=parameter.default is inspect.Parameter.empty,
            default=_jsonable_default(parameter.default),
            annotation="" if annotation is inspect.Parameter.empty else str(annotation).replace("typing.", "")))
    return params


def _doc(obj: object) -> str:
    doc = inspect.getdoc(obj) or ""
    return doc.strip().splitlines()[0] if doc.strip() else ""


def uses_claude(cls: type) -> bool:
    """確定のあとに AI を回す `result()` を持つか、AI を受け取る入口か。"""
    if cls.result not in _PLAIN_RESULTS:
        return True
    return "ai" in inspect.signature(cls.__init__).parameters


def entrance_classes() -> dict[str, type[Entrypoint]]:
    """`data_access_logic/<領域>/*.py` で定義した入口のクラスを、id(`<領域>.<ファイル>.<クラス>`)で。領域のディレクトリは
    `__init__.py` を持たない(名前空間パッケージ)ので、pkgutil ではなくファイルを直接見る。"""
    found: dict[str, type[Entrypoint]] = {}
    root = next(iter(data_access_logic.__path__))
    for area_name in sorted(os.listdir(root)):
        area_dir = os.path.join(root, area_name)
        if area_name.startswith(("_", ".")) or not os.path.isdir(area_dir):
            continue
        for filename in sorted(os.listdir(area_dir)):
            if not filename.endswith(".py") or filename.startswith("_"):
                continue
            module = importlib.import_module(f"data_access_logic.{area_name}.{filename[:-3]}")
            for name, cls in inspect.getmembers(module, inspect.isclass):
                if cls.__module__ == module.__name__ and issubclass(cls, Entrypoint):
                    found[f"{area_name}.{filename[:-3]}.{name}"] = cls
    return dict(sorted(found.items()))


def entrance_meta(entrance_id: str, cls: type[Entrypoint]) -> EntranceMeta:
    module = inspect.getmodule(cls)
    return EntranceMeta(
        id=entrance_id, area=entrance_id.split(".")[0], name=cls.__name__, doc=_doc(cls) or _doc(module),
        params=_params(cls.__init__), writes=issubclass(cls, CommitEntrypoint) or uses_claude(cls))
