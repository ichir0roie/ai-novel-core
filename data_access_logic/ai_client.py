#!/usr/bin/env python3
from __future__ import annotations

from typing import Protocol


class AIClient(Protocol):
    def try_generate_json(
        self,
        prompt: str,
        schema: dict,
        *,
        system: str | None = None,
        timeout: float = 120.0,
        options: dict | None = None,
    ) -> dict: ...
