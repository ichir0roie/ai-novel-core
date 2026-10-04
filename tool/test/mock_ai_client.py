#!/usr/bin/env python3
"""生成器の流れ(db への確定・時刻の進み・busy の除外など)を、AI 無し・費用無しで
最後まで通すためのもの。
"""
from __future__ import annotations

import random
import re

from pydantic import BaseModel, ValidationError

# 材料は日本語の見出しの JSON(`"人物id": 1`)で渡る
_CHARACTER_ID_IN_PROMPT = re.compile(r"\"人物id\": (\d+)")

# 空だと後段が何もしない配列だけ、件数を持たせる。それ以外の配列は空で返す。
_ARRAY_SIZES = {"candidates": 3, "seeds": 2}


class MockAIClient:
    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)
        self.calls: list[dict] = []

    def generate[Output: BaseModel](
        self, prompt: str, output: type[Output], system: str | None = None, timeout: float | None = None,
        tools: tuple[str, ...] = (), model: str = "", effort: str = "",
    ) -> Output | None:
        schema = output.model_json_schema()
        self.calls.append({"prompt": prompt, "system": system, "schema": schema, "tools": tools})
        try:
            return output.model_validate(self._fill(schema, prompt, key=None, defs=schema.get("$defs", {})))
        except ValidationError:
            return None

    def _fill(self, schema: dict, prompt: str, key: str | None, defs: dict):
        # pydantic の model_json_schema は入れ子のモデルを $defs に置いて $ref で指し、省ける値を anyOf で書く
        if "$ref" in schema:
            return self._fill(defs[schema["$ref"].rsplit("/", 1)[-1]], prompt, key, defs)
        if "anyOf" in schema:
            options = schema["anyOf"]
            if any(option.get("type") == "null" for option in options):
                return None
            return self._fill(options[0], prompt, key, defs)
        types = schema.get("type")
        if isinstance(types, list):
            if "null" in types:
                return None
            types = types[0]
        if "enum" in schema:
            return self.rng.choice(schema["enum"])
        if types == "object":
            return {name: self._fill(sub, prompt, name, defs)
                    for name, sub in schema.get("properties", {}).items()}
        if types == "array":
            if key == "character_ids":
                ids = sorted({int(m) for m in _CHARACTER_ID_IN_PROMPT.findall(prompt)})
                return self.rng.sample(ids, min(len(ids), self.rng.randint(1, 2))) if ids else []
            item = schema.get("items", {"type": "string"})
            return [self._fill(item, prompt, key, defs) for _ in range(_ARRAY_SIZES.get(key or "", 0))]
        if types == "integer":
            low = schema.get("minimum", 1)
            high = schema.get("maximum", max(low, 1))
            return self.rng.randint(low, high)
        if types == "number":
            return float(schema.get("minimum", 0))
        if types == "boolean":
            return False
        return f"モック{key or ''}{len(self.calls)}"
