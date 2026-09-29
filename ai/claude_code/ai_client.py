#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


class ClaudeAIError(RuntimeError):
    pass


_MODEL = "claude-sonnet-5"
_EFFORT = "medium"

# 話の本文(Episode)だけは質を優先する。要約・ミーム・出来事などはすべて上の既定のまま。
EPISODE_MODEL = "claude-fable-5-1"
EPISODE_EFFORT = "high"

# GUI の「本文のモデル」プルダウンに出す一覧(claude CLI の --model にそのまま渡せる名前)。
# 一覧の更新は本ファイルの値だけを直せばよい(GUI 側は choices としてこの値をそのまま受け取る)。
AVAILABLE_MODELS = (EPISODE_MODEL, "claude-opus-5", "claude-opus-5-5", _MODEL, "claude-haiku-4-5")

# GUI の「本文の effort」プルダウンに出す一覧。claude CLI の --effort に渡せる値(--help の一覧)そのまま。
AVAILABLE_EFFORTS = ("low", "medium", "high", "xhigh", "max")


class _Reply(BaseModel):
    """`claude -p --output-format json` の出力のうち、使う欄。"""

    is_error: bool = False
    subtype: str | None = None
    result: str | None = None
    # `--json-schema` を渡したとき、応答はここに入る
    structured_output: dict | None = None


def _command() -> str:
    name = os.environ.get("DEM_CLAUDE_AI_COMMAND", "claude")
    # Windows の npm shim は `claude.cmd` なので、PATHEXT を見て実体のパスに解決する。
    return shutil.which(name) or name


def _build_args(system: str | None, schema: dict, tools: tuple[str, ...] = (),
                model: str = _MODEL, effort: str = _EFFORT) -> list[str]:
    # `--tools` は組み込みの道具だけを絞る。MCP の道具(`mcp__…`)は MCP サーバーから来るので、許可だけ渡す。
    builtin = [tool for tool in tools if not tool.startswith("mcp__")]
    args = [
        _command(), "-p",
        "--output-format", "json",
        "--tools", ",".join(builtin),
        "--no-session-persistence",
    ]
    if tools:
        # -p では許可を尋ねられないので、渡した道具は先に許しておく(許さないと拒まれて使えない)。
        args += ["--allowedTools", ",".join(tools)]
    mcp_config = os.environ.get("DEM_CLAUDE_AI_MCP_CONFIG")
    if mcp_config and len(builtin) < len(tools):
        args += ["--mcp-config", mcp_config]
    if system is not None:
        args += ["--system-prompt", system]
    args += ["--json-schema", json.dumps(schema, ensure_ascii=False)]
    args += ["--model", model, "--effort", effort]
    return args


def _reply(prompt: str, args: list[str], timeout: float) -> _Reply:
    # CLI の起動と思考のぶん、呼び出し側の timeout では足りないことがある。
    timeout = max(timeout, float(os.environ.get("DEM_CLAUDE_AI_TIMEOUT", 600)))
    # プロジェクトの CLAUDE.md・設定を拾わせない(生成の指示は system だけにする)。
    cwd = tempfile.gettempdir()
    try:
        completed = subprocess.run(
            args, input=prompt, capture_output=True, cwd=cwd,
            encoding="utf-8", errors="replace", timeout=timeout)
    except OSError as error:
        raise ClaudeAIError(f"Claude Code({args[0]})を起動できない: {error}") from error
    except subprocess.TimeoutExpired as error:
        raise ClaudeAIError(f"Claude Code が {timeout} 秒以内に応答しない") from error

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()[-2000:]
        raise ClaudeAIError(f"Claude Code が終了コード {completed.returncode} で失敗: {detail}")
    try:
        reply = _Reply.model_validate_json(completed.stdout)
    except ValidationError as error:
        raise ClaudeAIError(f"Claude Code の出力が想定の形でない: {completed.stdout[-2000:]!r}") from error
    if reply.is_error or reply.subtype != "success":
        raise ClaudeAIError(f"Claude Code がエラーを返した({reply.subtype}): {reply.result!r}")
    return reply


def generate[Output: BaseModel](
    prompt: str,
    output: type[Output],
    system: str | None = None,
    timeout: float = 120.0,
    tools: tuple[str, ...] = (),
    model: str = _MODEL,
    effort: str = _EFFORT,
) -> Output | None:
    """応答が得られない・`output` の形に合わないときは None。"""
    args = _build_args(system, output.model_json_schema(), tools, model, effort)
    try:
        reply = _reply(prompt, args, timeout)
        if reply.structured_output is not None:
            return output.model_validate(reply.structured_output)
        if reply.result is None:
            raise ClaudeAIError("Claude Code の応答に 'result' が無い")
        return output.model_validate_json(reply.result)
    except (ClaudeAIError, ValidationError) as error:
        logger.warning(f"Claude Code の応答が使えなかった: {error}")
        return None
