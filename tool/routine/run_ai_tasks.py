#!/usr/bin/env python3
"""待ち行列(`ai_task`)を回すルーチンの本体。Claude Code のルーチン(クラウド)から、世界リポジトリのルートで:

    .venv/bin/python -m tool.routine.run_ai_tasks

1. 拾ったまま鼓動の絶えた行(前のルーチンが途中で終わった)を queued へ戻す
2. queued の行を古い順に一つずつ拾い、入口を回して結果を行に書き戻す(一件ずつコミット)
3. 行が尽きたら、フラグで印の付いた後回しの AI の段を回す(`RefreshGeneratedContent`。
   `meme_seeded=false` の行からのミームの抜き出しと、本文と食い違った要約の作り直し。GUI の追加・修正は `execute(s)` で
   確定だけしてこの段を回さないので、ここで拾う)
4. 新しい行を `--poll` 秒おきに見に行き、`--idle` 秒来なければ終わる。全体で `--max-minutes` を超えたら、
   回している一件を終えてから終わる

回しているあいだは鼓動(`ai_worker`)を打つので、API はルーチンを起こし直さない。
終わるときに、回した件数を JSON で print する。claude を叩くので Claude Code の環境(`CLAUDECODE=1`)でだけ動く。
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
import time
import traceback
from typing import Any

from data_access_logic.ai_task import queue
from data_access_logic.logs import configure_logging
from db.schema import AiTask, AiWorker, get_env_session
from gui.api import interface
from gui.api.claude_env import in_claude_code

logger = logging.getLogger(__name__)

_HEARTBEAT_SECONDS = 30


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--idle", type=int, default=600, help="新しい行を待つ秒数。来なければ終わる(既定 600)")
    p.add_argument("--poll", type=int, default=20, help="新しい行を見に行く間隔の秒数(既定 20)")
    p.add_argument("--max-minutes", type=int, default=50, help="全体の上限の分数(既定 50)")
    p.add_argument("--no-refresh", action="store_true", help="行が尽きたときの RefreshGeneratedContent を回さない")
    return p.parse_args(argv)


class _Heartbeat:
    """入口が数分〜十数分 claude を待つあいだも鼓動を打つよう、別のスレッドで打つ。"""

    def __init__(self, worker_id: int):
        self._worker_id = worker_id
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="ai-worker-heartbeat", daemon=True)

    def __enter__(self) -> _Heartbeat:
        self._thread.start()
        return self

    def __exit__(self, *_exc) -> None:
        self._stop.set()
        self._thread.join()

    def _loop(self) -> None:
        while not self._stop.wait(_HEARTBEAT_SECONDS):
            try:
                with get_env_session() as s, s.begin():
                    queue.beat(s, s.get_one(AiWorker, self._worker_id))
            except Exception:  # 鼓動が一度打てなくても、回している入口は止めない
                logger.exception("鼓動を打てなかった")


def _run_one(worker_id: int) -> tuple[int, str] | None:
    """一件拾って回す。行が無ければ None、あれば (id, 状態)。"""
    with get_env_session() as s, s.begin():
        task = queue.claim_next(s, worker_id)
        if task is None:
            return None
        task_id, entrance_id, args = task.id, task.entrance, dict(task.args or {})
    logger.info(f"ai_task {task_id}: {entrance_id} を回す")
    result: Any = None
    error: str | None = None
    try:
        entrance = interface.entrance_of(entrance_id)
        result = interface.call(entrance, interface.prepare(entrance, args))
    except Exception as exc:  # 落ちた理由は行に残し、次の行へ進む
        error = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        logger.exception(f"ai_task {task_id} が落ちた")
    with get_env_session() as s, s.begin():
        task = s.get_one(AiTask, task_id)
        queue.finish(s, task, result=result, error=error)
        return task_id, task.status


def _refresh() -> dict | list:
    from data_access_logic.meme.refresh_generated_content import RefreshGeneratedContent

    logger.info("フラグの付いた後回しの AI の段(RefreshGeneratedContent)を回す")
    return RefreshGeneratedContent().run()


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    configure_logging()
    if not in_claude_code():
        sys.exit("claude を叩くので、Claude Code の環境(CLAUDECODE=1)で動かす")

    deadline = time.monotonic() + args.max_minutes * 60
    summary: dict[str, Any] = {"done": [], "failed": [], "requeued": 0, "refreshed": None}
    with get_env_session() as s, s.begin():
        summary["requeued"] = queue.requeue_stale(s)
        worker_id = queue.start_worker(s, os.environ.get("CLAUDE_CODE_REMOTE_SESSION_ID")).id

    try:
        with _Heartbeat(worker_id):
            idle_since, refreshed = time.monotonic(), False
            while time.monotonic() < deadline:
                ran = _run_one(worker_id)
                if ran is not None:
                    task_id, status = ran
                    summary["done" if status == "done" else "failed"].append(task_id)
                    idle_since, refreshed = time.monotonic(), False
                    continue
                if not refreshed and not args.no_refresh:
                    summary["refreshed"] = _refresh()
                    idle_since, refreshed = time.monotonic(), True
                    continue
                if time.monotonic() - idle_since >= args.idle:
                    break
                time.sleep(args.poll)
    finally:
        with get_env_session() as s, s.begin():
            queue.stop_worker(s, s.get_one(AiWorker, worker_id))
            summary["pending"] = queue.pending_count(s)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
