#!/usr/bin/env python3
"""待ち行列(`ai_task`)に積んだとき、Claude Code のルーチンを API トリガー(`/fire`)で起こす。

ルーチンのスケジュールは一時間より細かくできないので、積んだその場で起こして分単位で拾わせる。
`NOVEL_ROUTINE_FIRE_URL`(ルーチンの API トリガーの URL)と `NOVEL_ROUTINE_FIRE_TOKEN`(その token)が
無ければ起こさない(毎時のスケジュールだけで拾う)。起こし過ぎないよう、鼓動のあるルーチンがいるとき・
起こした直後は起こさない(`data_access_logic/ai_task/queue.py` の `should_fire`)。
"""
from __future__ import annotations

import logging
import os

import httpx

from data_access_logic.ai_task import queue
from db.schema import AiTask, get_env_session

logger = logging.getLogger(__name__)

# ルーチンの `/fire` は研究プレビューで、日付つきの beta ヘッダーで版を選ぶ(変わったら環境変数で差し替える)
_DEFAULT_BETA = "experimental-cc-routine-2026-04-01"


def _settings() -> tuple[str, str] | None:
    url = os.environ.get("NOVEL_ROUTINE_FIRE_URL", "").strip()
    token = os.environ.get("NOVEL_ROUTINE_FIRE_TOKEN", "").strip()
    return (url, token) if url and token else None


def fire_if_idle(task_id: int) -> bool:
    """起こしたら true。起こせなくても積んだ行は残るので、毎時のスケジュールが拾う。"""
    settings = _settings()
    if settings is None:
        return False
    with get_env_session() as s, s.begin():
        if not queue.should_fire(s):
            return False
        queue.mark_fired(s, s.get_one(AiTask, task_id))
    url, token = settings
    headers = {
        "Authorization": f"Bearer {token}",
        "anthropic-beta": os.environ.get("NOVEL_ROUTINE_FIRE_BETA", _DEFAULT_BETA),
        "anthropic-version": "2023-06-01",
    }
    try:
        # ルーチンは `text` を信用しない参考として受け取る。回す中身は db の行から読む
        response = httpx.post(url, timeout=10, headers=headers, json={"text": f"ai_task {task_id} を積んだ"})
        response.raise_for_status()
    except httpx.HTTPError:
        logger.exception(f"ルーチンを起こせなかった(ai_task {task_id})。毎時のスケジュールで拾う")
        with get_env_session() as s, s.begin():
            queue.mark_fired(s, s.get_one(AiTask, task_id), fired=False)
        return False
    logger.info(f"ルーチンを起こした(ai_task {task_id}): {response.json().get('claude_code_session_url')}")
    return True
