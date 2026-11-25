#!/usr/bin/env python3
from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from db.schema import StyleScope


class AISession(Protocol):
    """一つの会話を続ける AI。前の問いと答えを覚えているので、二度目からは前に渡した材料を送り直さなくてよい。"""

    def ask[Output: BaseModel](self, prompt: str, output: type[Output], model: str | None = None) -> Output | None: ...


class AIClient(Protocol):
    def generate[Output: BaseModel](
        self,
        prompt: str,
        output: type[Output],
        system: str | None = None,
        timeout: float | None = None,
        tools: tuple[str, ...] = (),
        model: str = ...,
        effort: str = ...,
        style_scope: StyleScope | None = ...,
    ) -> Output | None: ...

    def session(self, system: str, style_scope: StyleScope | None, model: str, effort: str) -> AISession: ...
