#!/usr/bin/env python3
"""世界ごとの文体の好み。core は値を持たず、世界リポジトリの `instructions/style.py` にあればそこから読む。

入口の `shared_style_extra` / `style_extra` を省いたとき(None)に使う。明示して渡した値(空文字を含む)はそのまま使う。
"""
from __future__ import annotations

import functools
import importlib.util
import os
from types import ModuleType

from db.schema import WORLD_DIR


@functools.cache
def _world_style() -> ModuleType | None:
    # cwd や import の探し先に世界リポジトリのルートが入っていなくても読めるよう、`DEM_WORLD_DIR` の下のファイルを直に読む
    path = os.path.join(WORLD_DIR, "instructions", "style.py")
    spec = importlib.util.spec_from_file_location("instructions.style", path)
    if spec is None or spec.loader is None or not os.path.isfile(path):
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _constant(name: str) -> str:
    style = _world_style()
    return "" if style is None else getattr(style, name, "")


def shared_style_extra(given: str | None) -> str:
    return _constant("SHARED_EXTRA") if given is None else given


def style_extra(given: str | None) -> str:
    return _constant("EPISODE_STYLE_EXTRA") if given is None else given
