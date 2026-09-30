#!/usr/bin/env python3
"""claude を叩く入口の呼び出しの待ち行列(`ai_task`)。

claude の無い環境(Lambda の API)では入口を回せないので、呼び出しを行に積んで返す。Claude Code on the web のセッションが
`web_session/run_ai_tasks.py` で古い順に拾って回し、結果を行に書き戻す(拾う・書き戻すは `ai_task/steps.py` の段で API 越しに)。
画面は `/api/jobs/task-<id>` で行を引く。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.schema import AiTask, AiTaskStatus, utc_now

# 画面・API が job として見せる id の頭。プロセスの中の job(uuid の 12 桁)と見分ける
JOB_PREFIX = "task-"
# 拾ったセッションが途中で止まった行を、何回まで拾い直すか(入口そのものがセッションを落とす行で回り続けない)
MAX_ATTEMPTS = 3


def enqueue(s: Session, entrance: str, args: dict[str, Any]) -> AiTask:
    task = AiTask(entrance=entrance, args=args, status=AiTaskStatus.QUEUED)
    s.add(task)
    s.flush()
    return task


def task_id_of(job_id: str) -> int | None:
    if not job_id.startswith(JOB_PREFIX):
        return None
    number = job_id.removeprefix(JOB_PREFIX)
    return int(number) if number.isdigit() else None


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat(timespec="seconds") + "+00:00"


def job_view(task: AiTask) -> dict[str, Any]:
    """`gui/api/models.py` の `JobInfo` の形。プロセスの中の job と同じ形で画面に見せる。"""
    return {
        "id": f"{JOB_PREFIX}{task.id}", "entrance": task.entrance, "args": task.args or {},
        "status": task.status, "result": task.result, "error": task.error,
        "created_at": _iso(task.created_at), "started_at": _iso(task.started_at), "finished_at": _iso(task.finished_at),
    }


def recent(s: Session, limit: int = 50) -> list[AiTask]:
    return list(s.scalars(select(AiTask).order_by(AiTask.id.desc()).limit(limit)).all())


def pending_count(s: Session) -> int:
    return s.scalar(select(func.count()).select_from(AiTask).where(AiTask.status == AiTaskStatus.QUEUED)) or 0


def claim_next(s: Session) -> AiTask | None:
    """一番古い queued の行を running にして返す。"""
    task = s.scalars(select(AiTask).where(AiTask.status == AiTaskStatus.QUEUED).order_by(AiTask.id).limit(1)).first()
    if task is None:
        return None
    task.status, task.started_at = AiTaskStatus.RUNNING, utc_now()
    task.attempts += 1
    s.flush()
    return task


def finish(s: Session, task: AiTask, result: Any = None, error: str | None = None) -> None:
    task.status = AiTaskStatus.FAILED if error is not None else AiTaskStatus.DONE
    task.result, task.error, task.finished_at = result, error, utc_now()
    s.flush()


def requeue_running(s: Session) -> int:
    """running のまま残った行(前に回したセッションが途中で終わった)を queued へ戻す。
    回すのは一度に一つのセッションだけなので、回し始める前に呼べば running の行はどれも止まったものになる。
    拾った回数が上限に達した行は failed にする。戻した・落とした行の数を返す。"""
    stale = s.scalars(select(AiTask).where(AiTask.status == AiTaskStatus.RUNNING)).all()
    for task in stale:
        if task.attempts >= MAX_ATTEMPTS:
            task.status, task.finished_at = AiTaskStatus.FAILED, utc_now()
            task.error = f"{task.attempts} 回拾ったが、どれもセッションが途中で止まって終わらなかった"
        else:
            task.status, task.started_at = AiTaskStatus.QUEUED, None
    s.flush()
    return len(stale)
