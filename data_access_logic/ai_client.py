#!/usr/bin/env python3
from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel


class AIClient(Protocol):
    def generate[Output: BaseModel](
        self,
        prompt: str,
        output: type[Output],
        system: str | None = None,
        timeout: float = 120.0,
        model: str = ...,
        effort: str = ...,
    ) -> Output | None: ...
