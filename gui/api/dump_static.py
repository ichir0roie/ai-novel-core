#!/usr/bin/env python3
"""画面(`gui/web`)が固定で持つものを書き出す。表・入口・API の形を変えたら回し、続けて `gui/web` で `npm run types` を回す。

- `gui/api/openapi.json`: API の形。フロントの型(`lib/openapi.d.ts`)の元。画面が JSON で持つ表・入口の情報の型も足す
- `gui/web/lib/tables.json`: 表の列・子の一覧(`gui/api/meta.py`)。フォーム・一覧を組み立てるのに使う
- `gui/web/lib/entrances.json`: API から呼べる入口と引数(`gui/api/catalog.py`)。入口の画面(`/interface`)が並べる

API はこれらを要求のたびに組み立てない。書き出したものがコードとずれていないかは `tests/api/test_static.py` が見る。

    .venv/bin/python -m gui.api.dump_static
"""
from __future__ import annotations

import json
import os
from typing import Any

from pydantic.json_schema import models_json_schema

from gui.api import catalog, interface, meta
from gui.api.app import app
from gui.api.models import EntranceList, TablesResponse

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OPENAPI_PATH = os.path.join(_ROOT, "gui", "api", "openapi.json")
TABLES_PATH = os.path.join(_ROOT, "gui", "web", "lib", "tables.json")
ENTRANCES_PATH = os.path.join(_ROOT, "gui", "web", "lib", "entrances.json")


def openapi() -> dict[str, Any]:
    document = app.openapi()
    _, schema = models_json_schema([(TablesResponse, "serialization"), (EntranceList, "serialization")],
                                   ref_template="#/components/schemas/{model}")
    document["components"]["schemas"].update(schema["$defs"])
    return document


def tables() -> dict[str, Any]:
    return TablesResponse(tables=meta.all_tables()).model_dump(mode="json")


def entrances() -> dict[str, Any]:
    classes = catalog.entrance_classes()
    return EntranceList(entrances=[catalog.entrance_meta(entrance_id, classes[entrance_id])
                                   for entrance_id in sorted(interface.DB_ENTRANCES)]).model_dump(mode="json")


def dumped(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def main() -> list[str]:
    written = []
    for path, value in ((OPENAPI_PATH, openapi()), (TABLES_PATH, tables()), (ENTRANCES_PATH, entrances())):
        with open(path, "w", encoding="utf-8") as f:
            f.write(dumped(value))
        written.append(path)
    return written


if __name__ == "__main__":
    print("\n".join(main()))
