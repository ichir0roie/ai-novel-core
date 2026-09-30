#!/usr/bin/env python3
"""`claude` コマンド(`claude -p`)を叩く入口を、この API でどう扱うか(`NOVEL_CLAUDE_MODE`)。

- `direct`: その場で裏の job として回す。Claude Code の環境(`CLAUDECODE=1`)でだけ選べる。
  Claude Code はシェルに `CLAUDECODE=1` を渡し、`gui.dev` も API に渡す
- `queue`: 呼び出しを db の待ち行列(`ai_task`)に積むだけで返し、Claude Code のルーチンが後で回す。
  claude の無い常駐サーバー(Lambda など)で AI のボタンを使うとき(`.docs/claude-tasks.md`)
- `off`: 403 で止める。画面の AI のボタンは押せなくなる

`NOVEL_CLAUDE_MODE` を省けば、Claude Code の環境なら `direct`、外なら `off`。
"""
from __future__ import annotations

import logging
import os
from typing import Literal, cast

logger = logging.getLogger(__name__)

ClaudeMode = Literal["direct", "queue", "off"]
_MODES = ("direct", "queue", "off")


def in_claude_code() -> bool:
    return os.environ.get("CLAUDECODE") == "1"


def claude_mode() -> ClaudeMode:
    mode = os.environ.get("NOVEL_CLAUDE_MODE", "").strip()
    if not mode:
        return "direct" if in_claude_code() else "off"
    if mode not in _MODES:
        raise ValueError(f"NOVEL_CLAUDE_MODE は {'/'.join(_MODES)} のいずれか: {mode!r}")
    if mode == "direct" and not in_claude_code():
        logger.warning("NOVEL_CLAUDE_MODE=direct だが Claude Code の環境(CLAUDECODE=1)ではないので off として扱う")
        return "off"
    return cast(ClaudeMode, mode)


def claude_available() -> bool:
    """画面の AI のボタンを押せるか(その場で回すか、待ち行列に積めるか)。"""
    return claude_mode() != "off"


class ClaudeCommandForbidden(PermissionError):
    pass


def require_claude_code(entrance: str) -> None:
    if not claude_available():
        raise ClaudeCommandForbidden(
            f"{entrance} は claude コマンドを叩くので、Claude Code の環境(CLAUDECODE=1)で起こした API か、"
            "待ち行列に積む API(NOVEL_CLAUDE_MODE=queue)でだけ実行できる")
