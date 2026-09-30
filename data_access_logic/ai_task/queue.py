#!/usr/bin/env python3
"""claude を叩く入口の呼び出しの待ち行列(`ai_task`)と、それを回すルーチンの生存確認(`ai_worker`)。

claude の無い環境(Lambda の API)では入口を回せないので、呼び出しを行に積んで返す。Claude Code のルーチンが
`tool/routine/run_ai_tasks.py` で古い順に拾って回し、結果を行に書き戻す。画面は `/api/jobs/task-<id>` で行を引く。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from db.schema import AiTask, AiTaskStatus, AiWorker, utc_now

# 画面・API が job として見せる id の頭。プロセスの中の job(uuid の 12 桁)と見分ける
JOB_PREFIX = "task-"
# これより新しい鼓動があるルーチンは生きているとみなし、起こし直さない
WORKER_ALIVE = timedelta(minutes=2)
# 一度起こしたら、ルーチンのセッションが立ち上がって鼓動を打つまでは起こし直さない
FIRE_DEBOUNCE = timedelta(minutes=5)
# 拾ったルーチンが途中で止まった行を、何回まで拾い直すか(入口そのものがセッションを落とす行で回り続けない)
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


def claim_next(s: Session, worker_id: int | None) -> AiTask | None:
    """一番古い queued の行を running にして返す。PostgreSQL では他のルーチンが掴んだ行を飛ばす
    (SQLite は FOR UPDATE を持たないが、書き込みを一つずつしか通さないので同じ行を二度は掴まない)。"""
    task = s.scalars(select(AiTask).where(AiTask.status == AiTaskStatus.QUEUED).order_by(AiTask.id)
                     .limit(1).with_for_update(skip_locked=True)).first()
    if task is None:
        return None
    task.status, task.started_at, task.worker_id = AiTaskStatus.RUNNING, utc_now(), worker_id
    task.attempts += 1
    s.flush()
    return task


def finish(s: Session, task: AiTask, result: Any = None, error: str | None = None) -> None:
    task.status = AiTaskStatus.FAILED if error is not None else AiTaskStatus.DONE
    task.result, task.error, task.finished_at = result, error, utc_now()
    s.flush()


def _dead_workers() -> Select:
    return select(AiWorker.id).where(or_(AiWorker.stopped_at.is_not(None),
                                         AiWorker.heartbeat_at <= utc_now() - WORKER_ALIVE))


def requeue_stale(s: Session) -> int:
    """running のまま、拾ったルーチンの鼓動が絶えた行(セッションが途中で終わった)を queued へ戻す。
    拾った回数が上限に達した行は failed にする。戻した・落とした行の数を返す。"""
    stale = s.scalars(select(AiTask).where(
        AiTask.status == AiTaskStatus.RUNNING,
        or_(AiTask.worker_id.is_(None), AiTask.worker_id.in_(_dead_workers())))).all()
    for task in stale:
        if task.attempts >= MAX_ATTEMPTS:
            task.status, task.finished_at = AiTaskStatus.FAILED, utc_now()
            task.error = f"{task.attempts} 回拾ったが、どれもルーチンが途中で止まって終わらなかった"
        else:
            task.status, task.started_at, task.worker_id = AiTaskStatus.QUEUED, None, None
    s.flush()
    return len(stale)


def start_worker(s: Session, session: str | None) -> AiWorker:
    worker = AiWorker(session=session)
    s.add(worker)
    s.flush()
    return worker


def beat(s: Session, worker: AiWorker) -> None:
    worker.heartbeat_at = utc_now()
    s.flush()


def stop_worker(s: Session, worker: AiWorker) -> None:
    worker.stopped_at = utc_now()
    s.flush()


def should_fire(s: Session) -> bool:
    """ルーチンを起こすべきか。鼓動のあるルーチンがいるか、起こした直後(まだ鼓動が無い)なら起こさない。"""
    now = utc_now()
    alive = s.scalars(select(AiWorker.id).where(AiWorker.stopped_at.is_(None),
                                                AiWorker.heartbeat_at > now - WORKER_ALIVE).limit(1)).first()
    if alive is not None:
        return False
    fired = s.scalars(select(AiTask.id).where(AiTask.fired_at > now - FIRE_DEBOUNCE,
                                              or_(AiTask.status == AiTaskStatus.QUEUED,
                                                  AiTask.status == AiTaskStatus.RUNNING)).limit(1)).first()
    return fired is None


def mark_fired(s: Session, task: AiTask, fired: bool = True) -> None:
    task.fired_at = utc_now() if fired else None
    s.flush()
