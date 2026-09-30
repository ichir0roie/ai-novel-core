#!/usr/bin/env python3
"""待ち行列(`ai_task`)を、Claude Code on the web のセッションで回す。リポジトリのルートで:

    .venv/bin/python -m web_session.run_ai_tasks

1. running のまま残った行(前に回したセッションが途中で終わった)を queued へ戻す
2. queued の行を古い順に一つずつ拾い、入口に当たる web の流れ(`web_session/flows.py`)を回して結果を行に書き戻す
3. 行が尽きたら、フラグで印の付いた後回しの AI の段(`RefreshGeneratedContent` に当たる流れ)を一度回して終わる
   (`--no-refresh` で外す)

終わるときに、回した行(`done` は id、`failed` は id と落ちた理由)と残りの件数を JSON で print する。
db には API(`web_session/api.py`)越しにだけ触る。
"""
from __future__ import annotations

import argparse
import logging
import sys
import traceback
from typing import Any

from pydantic import BaseModel

from data_access_logic.ai_task import steps
from data_access_logic.logs import configure_logging
from gui.api.claude_env import in_claude_code
from web_session import flows
from web_session.api import call

logger = logging.getLogger(__name__)


class FailedTask(BaseModel):
    id: int
    error: str


class RunSummary(BaseModel):
    requeued: int
    done: list[int] = []
    failed: list[FailedTask] = []
    # 後回しの AI の段の結果(`--no-refresh` なら None)
    refreshed: Any = None
    pending: int = 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--no-refresh", action="store_true", help="行が尽きたときの後回しの AI の段を回さない")
    return p.parse_args(argv)


def _run_one() -> steps.TaskOutcome | None:
    """一件拾って回す。行が無ければ None。"""
    task = call(steps.claim_next_task)
    if task is None:
        return None
    logger.info(f"ai_task {task.id}: {task.entrance} を回す")
    outcome = steps.TaskOutcome(id=task.id)
    try:
        outcome.result = flows.run(task.entrance, task.args)
    except Exception as exc:  # 落ちた理由は行に残し、次の行へ進む
        outcome.error = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        logger.exception(f"ai_task {task.id} が落ちた")
    call(steps.finish_task, outcome)
    return outcome


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    configure_logging()
    if not in_claude_code():
        sys.exit("claude を叩くので、Claude Code の環境(CLAUDECODE=1)で動かす")

    summary = RunSummary(requeued=call(steps.requeue_running_tasks))
    while (outcome := _run_one()) is not None:
        if outcome.error is None:
            summary.done.append(outcome.id)
        else:
            summary.failed.append(FailedTask(id=outcome.id, error=outcome.error))
    if not args.no_refresh:
        logger.info("フラグの付いた後回しの AI の段を回す")
        summary.refreshed = flows.run(flows.REFRESH, {})
    summary.pending = call(steps.db_status).ai_task_queued
    print(summary.model_dump_json())

if __name__ == "__main__":
    main()
