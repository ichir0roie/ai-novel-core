#!/usr/bin/env python3
from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from db.schema import StyleScope


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
        style_scope: StyleScope = ...,
        story_id: int | None = ...,
        episode_id: int | None = ...,
        instruction: StyleScope | None = ...,
    ) -> Output | None: ...
