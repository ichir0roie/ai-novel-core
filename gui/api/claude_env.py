#!/usr/bin/env python3
"""`claude` コマンド(`claude -p`)を叩く入口を、Claude Code の環境でだけ通すための判定。

Claude Code はシェルに `CLAUDECODE=1` を渡し、`gui.dev` も API に渡す。それ以外(uvicorn を素のターミナルや
常駐サーバーで直に起こしたとき)は、`claude` を叩く入口を 403 で止める。
"""
from __future__ import annotations

import os


def in_claude_code() -> bool:
    return os.environ.get("CLAUDECODE") == "1"


class ClaudeCommandForbidden(PermissionError):
    pass


def require_claude_code(entrance: str) -> None:
    if not in_claude_code():
        raise ClaudeCommandForbidden(
            f"{entrance} は claude コマンドを叩くので、Claude Code の環境(CLAUDECODE=1)で起こした API でだけ実行できる")
