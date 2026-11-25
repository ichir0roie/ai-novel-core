#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import uuid
from functools import cache
from pathlib import Path

from pydantic import BaseModel, ValidationError

from ai.instructions.materials import SAFETY_NOTE, calendar_note
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


def _build_args(system: str, schema: dict, tools: tuple[str, ...], model: str, effort: str,
                persist: bool = False) -> list[str]:
    """`persist` は会話を残すか(`ClaudeSession` が続きから呼ぶときだけ残す)。"""
    # `--tools` は組み込みの道具だけを絞る。MCP の道具(`mcp__…`)は MCP サーバーから来るので、許可だけ渡す。
    builtin = [tool for tool in tools if not tool.startswith("mcp__")]
    args = [
        _command(), "-p",
        "--output-format", "json",
        "--tools", ",".join(builtin),
        *([] if persist else ["--no-session-persistence"]),
        # 使う人の設定(グローバルの CLAUDE.md・接続した MCP・スキル)を読ませない。読むと、MCP の道具の定義だけで毎回 10 万トークン
        # ほど載り、CLAUDE.md の口調(一人称など)が生成した文に移る。MCP の道具は下の `--mcp-config` で渡すものだけにする
        "--strict-mcp-config",
        "--setting-sources", "",
    ]
    if tools:
        # -p では許可を尋ねられないので、渡した道具は先に許しておく(許さないと拒まれて使えない)。
        args += ["--allowedTools", ",".join(tools)]
    mcp_config = os.environ.get("DEM_CLAUDE_AI_MCP_CONFIG")
    if mcp_config and len(builtin) < len(tools):
        args += ["--mcp-config", mcp_config]
    return args + ["--system-prompt", system, "--json-schema", json.dumps(schema, ensure_ascii=False),
                   "--model", model, "--effort", effort]


def _reply(prompt: str, args: list[str], timeout: float | None) -> _Reply:
    # CLI の起動と思考のぶん、短い待ち時間では足りない。既定は `DEM_CLAUDE_AI_TIMEOUT`(600 秒)で、
    # 道具で調べさせる呼び出しなど、それより長く待つものだけが `timeout` を渡す。
    timeout = max(timeout or 0.0, float(os.environ.get("DEM_CLAUDE_AI_TIMEOUT", 600)))
    try:
        # cwd を一時ディレクトリにして、プロジェクトの CLAUDE.md・設定を拾わせない(生成の指示は system だけにする)
        completed = subprocess.run(
            args, input=prompt, capture_output=True, cwd=tempfile.gettempdir(),
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


def _parsed[Output: BaseModel](reply: _Reply, output: type[Output]) -> Output:
    if reply.structured_output is not None:
        return output.model_validate(reply.structured_output)
    if reply.result is None:
        raise ClaudeAIError("Claude Code の応答に 'result' が無い")
    return output.model_validate_json(reply.result)


def styled_system(system: str | None, writing_style: str, with_calendar: bool = True) -> str:
    """`with_calendar` は暦の数え方(年を含む表記の決まり)を足すか。人物の目の生成には年を渡さないので足さない。"""
    return "\n\n".join(part for part in (system, SAFETY_NOTE, calendar_note() if with_calendar else "",
                                          writing_style and f"書く文の書き方:\n{writing_style}") if part)


def generate[Output: BaseModel](
    prompt: str,
    output: type[Output],
    system: str | None = None,
    timeout: float | None = None,
    tools: tuple[str, ...] = (),
    model: str = MODEL,
    effort: str = EFFORT,
    style_scope: StyleScope | None = StyleScope.ALL,
) -> Output | None:
    """応答が得られない・`output` の形に合わないときは None。
    `system` は仕事ごとの指示(コードの定数)。そのあとに、どの生成にも効く禁止事項と、書く文の書き方(全体の行 → その範囲の行)を足す。
    `style_scope` は書く文の範囲(プロット・人物など)で、文を書かない仕事(id・番号だけを返す)は None にして書き方を足さない。
    作品・話の指示は本文だけに効き、本文は AI の生成では書かないので、ここでは足さない。"""
    load_env()
    args = _build_args(_system_text(system, style_scope), output.model_json_schema(), tools, model, effort)
    try:
        return _parsed(_reply(prompt, args, timeout), output)
    except (ClaudeAIError, ValidationError) as error:
        logger.warning(f"Claude Code の応答が使えなかった: {error}")
        return None


def _system_text(system: str | None, style_scope: StyleScope | None) -> str:
    # 世界ごとの書き方なので、そのつど db の段で読む
    writing_style = "" if style_scope is None else call(style_steps.writing_style, WritingStyleForm(scope=style_scope))
    return styled_system(system, writing_style, with_calendar=style_scope is not StyleScope.ACTING)


class ClaudeSession:
    """一つの会話を `claude -p` の続き(`--resume`)で回す。二度目からは前の問いと答えをキャッシュから読むので、毎回の材料は差分だけでよい。
    一度目の呼び出しが失敗したら、会話を作り直す(id を使い直すと、作りかけの会話とぶつかる)。"""

    def __init__(self, system: str, style_scope: StyleScope | None, model: str, effort: str):
        load_env()
        self.system = _system_text(system, style_scope)
        self.model = model
        self.effort = effort
        self.id = str(uuid.uuid4())
        self.started = False

    def ask[Output: BaseModel](self, prompt: str, output: type[Output], model: str | None = None) -> Output | None:
        args = _build_args(self.system, output.model_json_schema(), (), model or self.model, self.effort, persist=True)
        args += ["--resume", self.id] if self.started else ["--session-id", self.id]
        try:
            reply = _reply(prompt, args, None)
        except ClaudeAIError as error:
            logger.warning(f"Claude Code の会話({self.id})の応答が使えなかった: {error}")
            if not self.started:
                self.id = str(uuid.uuid4())
            return None
        self.started = True
        try:
            return _parsed(reply, output)
        except (ClaudeAIError, ValidationError) as error:
            logger.warning(f"Claude Code の会話({self.id})の応答が使えなかった: {error}")
            return None


def session(system: str, style_scope: StyleScope | None, model: str = MODEL, effort: str = EFFORT) -> ClaudeSession:
    return ClaudeSession(system, style_scope, model, effort)
