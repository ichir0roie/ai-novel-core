#!/usr/bin/env python3
"""OpenAPI を `gui/api/openapi.json` に書き出す。フロントの型はここから生成する(`gui/web` の `npm run types`)。

    .venv/bin/python -m gui.api.dump_openapi
"""
from __future__ import annotations

import json
import os

from gui.api.app import app


def main() -> str:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "openapi.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(app.openapi(), f, ensure_ascii=False, indent=2)
        f.write("\n")
    return path


if __name__ == "__main__":
    print(main())
