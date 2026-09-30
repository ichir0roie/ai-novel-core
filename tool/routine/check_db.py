#!/usr/bin/env python3
"""ルーチンの環境から db に届くかを確かめる。世界リポジトリのルートで:

    .venv/bin/python -m tool.routine.check_db

繋ぐ先(パスワードは伏せる)・接続できたか・alembic の版が head か・PostGIS の版・待ち行列の件数・
`claude` コマンドの有無を JSON で print し、繋がらないか版が食い違えば終了コード 1 で終わる。
クラウドの環境の設定(ネットワーク・環境変数)を変えたら、まずこれを回す(`.docs/routine-db-connection.md`)。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from typing import Any


def main() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from sqlalchemy import text

    from db.schema import engine

    report: dict[str, Any] = {
        "url": engine.url.render_as_string(hide_password=True),
        "claude_command": shutil.which(os.environ.get("DEM_CLAUDE_AI_COMMAND", "claude")),
        "claudecode_env": os.environ.get("CLAUDECODE") == "1",
    }
    alembic_ini = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                               "db", "alembic", "alembic.ini")
    report["alembic_head"] = ScriptDirectory.from_config(Config(alembic_ini)).get_current_head()
    ok = False
    try:
        with engine.connect() as conn:
            report["connected"] = True
            report["alembic_current"] = conn.scalar(text("SELECT version_num FROM alembic_version"))
            if engine.dialect.name == "postgresql":
                report["postgis"] = conn.scalar(text(
                    "SELECT extversion FROM pg_extension WHERE extname = 'postgis'"))
            report["ai_task_queued"] = conn.scalar(text("SELECT count(*) FROM ai_task WHERE status = 'queued'"))
        ok = report["alembic_current"] == report["alembic_head"]
    except Exception as exc:  # 繋がらない理由をそのまま見せる
        report["connected"] = report.get("connected", False)
        report["error"] = f"{type(exc).__name__}: {exc}"
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
