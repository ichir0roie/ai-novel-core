#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


class ClaudeAIError(RuntimeError):
    pass


# 呼んだ回数とトークン・費用の積算。`usage_summary` でループの終わりに出す。
_tally = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}


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


def _command() -> str:
    name = os.environ.get("DEM_CLAUDE_AI_COMMAND", "claude")
    # Windows の npm shim は `claude.cmd` なので、PATHEXT を見て実体のパスに解決する。
    return shutil.which(name) or name


def _build_args(system: str | None, schema: dict | None, tools: tuple[str, ...] = (),
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
    if schema is not None:
        args += ["--json-schema", json.dumps(schema, ensure_ascii=False)]
    args += ["--model", model, "--effort", effort]
    return args


def _record_usage(result: dict) -> None:
    usage = result.get("usage") or {}
    _tally["calls"] += 1
    # input_tokens はキャッシュ命中分を含まないので、実際に読ませた量として足し合わせる。
    _tally["input_tokens"] += sum(
        int(usage.get(key) or 0)
        for key in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
    _tally["output_tokens"] += int(usage.get("output_tokens") or 0)
    _tally["cost_usd"] += float(result.get("total_cost_usd") or 0.0)


def usage_summary() -> str:
    return (f"claude 呼び出し {_tally['calls']}回 / 入力 {_tally['input_tokens']} tok"
            f" / 出力 {_tally['output_tokens']} tok / ${_tally['cost_usd']:.4f}")


def generate(
    prompt: str,
    *,
    system: str | None = None,
    format: dict | str | None = None,
    timeout: float = 120.0,
    options: dict | None = None,
    tools: tuple[str, ...] = (),
    model: str = _MODEL,
    effort: str = _EFFORT,
) -> str:
    """`options`(Ollama の temperature 等)は Claude Code に相当する設定が無いので受け取るだけで使わない。"""
    schema = format if isinstance(format, dict) else None
    args = _build_args(system, schema, tools, model, effort)
    # CLI の起動と思考のぶん、Ollama 向けの timeout(既定 120 秒)では足りないことがある。
    timeout = max(float(timeout), float(os.environ.get("DEM_CLAUDE_AI_TIMEOUT", 600)))
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
        raise ClaudeAIError(
            f"Claude Code が終了コード {completed.returncode} で失敗: {detail}")
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ClaudeAIError(
            f"Claude Code の出力が JSON として読めない: {completed.stdout[-2000:]!r}") from error
    if not isinstance(result, dict):
        raise ClaudeAIError(f"Claude Code の出力が想定の形でない: {result!r}")

    _record_usage(result)
    if result.get("is_error") or result.get("subtype") != "success":
        raise ClaudeAIError(
            f"Claude Code がエラーを返した({result.get('subtype')}): {result.get('result')!r}")

    if schema is not None and result.get("structured_output") is not None:
        return json.dumps(result["structured_output"], ensure_ascii=False)
    text = result.get("result")
    if text is None:
        raise ClaudeAIError(f"Claude Code の応答に 'result' が無い: {result!r}")
    return text


def generate_json(
    prompt: str,
    schema: dict,
    *,
    system: str | None = None,
    timeout: float = 120.0,
    options: dict | None = None,
    tools: tuple[str, ...] = (),
    model: str = _MODEL,
    effort: str = _EFFORT,
) -> dict:
    text = generate(
        prompt, system=system, format=schema, timeout=timeout, options=options, tools=tools,
        model=model, effort=effort)
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise ClaudeAIError(
            f"Claude Code の応答がJSONとしてパースできない: {text!r}") from error


def try_generate_json(
    prompt: str,
    schema: dict,
    *,
    system: str | None = None,
    timeout: float = 120.0,
    options: dict | None = None,
    tools: tuple[str, ...] = (),
    model: str = _MODEL,
    effort: str = _EFFORT,
) -> dict:
    try:
        return generate_json(prompt, schema, system=system, timeout=timeout, options=options, tools=tools,
                             model=model, effort=effort)
    except ClaudeAIError as error:
        print(f"[claude_ai] Claude Code の応答が使えなかったため既定値で進める: {error}")
        return {}
