#!/usr/bin/env python3
"""web のセッションから API 越しに db に届くかを確かめる。リポジトリのルートで:

    .venv/bin/python -m web_session.check_api

繋ぐ先の API・db の種類・alembic のバージョン(db の側と、このセッションのコードの head)・PostGIS のバージョン・
`claude` コマンドの有無を JSON で print し、届かないかバージョンが食い違えば終了コード 1 で終わる。
web の環境の設定(ネットワーク・環境変数)を変えたら、まずこれを回す(`.docs/web-session.md`)。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory

from data_access_logic.system import steps
from web_session.api import call

_ALEMBIC_INI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db", "alembic", "alembic.ini")


def main() -> None:
    report: dict[str, Any] = {
        "api_url_set": bool(os.environ.get("NOVEL_API_URL", "").strip()),
        "api_key_set": bool(os.environ.get("NOVEL_API_KEY", "").strip()),
        "claude_command": shutil.which(os.environ.get("DEM_CLAUDE_AI_COMMAND", "claude")),
        "claudecode_env": os.environ.get("CLAUDECODE") == "1",
        "alembic_head": ScriptDirectory.from_config(Config(_ALEMBIC_INI)).get_current_head(),
    }
    ok = False
    try:
        status = call(steps.db_status)
        report.update(connected=True, **status.model_dump())
        ok = status.alembic_current == report["alembic_head"]
    except Exception as exc:  # 届かない理由をそのまま見せる
        report.update(connected=False, error=f"{type(exc).__name__}: {exc}")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
