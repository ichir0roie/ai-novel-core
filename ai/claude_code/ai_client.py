#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from functools import cache
from pathlib import Path

from pydantic import BaseModel, ValidationError

from data_access_logic.caller import call
from data_access_logic.style_preference import steps as style_steps
from data_access_logic.style_preference.form import WritingStyleForm
from db.schema import StyleScope

logger = logging.getLogger(__name__)


@cache
def load_env() -> None:
    """`.env` の `DEM_CLAUDE_AI_*` を環境変数に読む。claude を叩く前に一度だけ。import のときには読まない
    (API の Lambda は claude を叩かず、dotenv の import がコールドスタートを延ばすため)"""
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")


class ClaudeAIError(RuntimeError):
    pass


MODEL = "claude-opus-5-5"
EFFORT = "low"


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
                model: str = MODEL, effort: str = EFFORT) -> list[str]:
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


def _reply(prompt: str, args: list[str], timeout: float | None) -> _Reply:
    # CLI の起動と思考のぶん、短い待ち時間では足りない。既定は `DEM_CLAUDE_AI_TIMEOUT`(600 秒)で、
    # 道具で調べさせる呼び出しなど、それより長く待つものだけが `timeout` を渡す。
    timeout = max(timeout or 0.0, float(os.environ.get("DEM_CLAUDE_AI_TIMEOUT", 600)))
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


def styled_system(system: str | None, writing_style: str) -> str:
    return "\n\n".join(part for part in (system, f"書く文の書き方:\n{writing_style}") if part)


def generate[Output: BaseModel](
    prompt: str,
    output: type[Output],
    system: str | None = None,
    timeout: float | None = None,
    tools: tuple[str, ...] = (),
    model: str = MODEL,
    effort: str = EFFORT,
    style_scope: StyleScope = StyleScope.ALL,
    story_id: int | None = None,
) -> Output | None:
    """応答が得られない・`output` の形に合わないときは None。
    `style_scope` は書く文の範囲(プロット・人物など)、`story_id` は書く文の作品。全体 → ストーリー → その範囲の書き方を足す。"""
    load_env()
    # プロット・来歴・アイデア・ミームなど、AI が書くどの文にも書き方を効かせる。世界・作品ごとの指示を含むので、そのつど db の段で読む
    system = styled_system(system, call(style_steps.writing_style, WritingStyleForm(scope=style_scope, story_id=story_id)))
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
