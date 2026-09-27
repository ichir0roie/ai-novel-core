#!/usr/bin/env python3
"""長く掛かる入口(`claude -p` を回すもの)を裏で走らせ、id で状態を引く。

プロセスの中のメモリにだけ持つ(API を起こし直すと消える)。`claude` を同時に何本も回さないよう、一度に一つずつ走らせる。
"""
from __future__ import annotations

import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Job:
    id: str
    entrance: str
    args: dict[str, Any]
    status: str = "queued"  # queued / running / done / failed
    result: Any = None
    error: str | None = None
    created_at: str = field(default_factory=_now)
    started_at: str | None = None
    finished_at: str | None = None

    def to_dict(self) -> dict:
        return {"id": self.id, "entrance": self.entrance, "args": self.args, "status": self.status,
                "result": self.result, "error": self.error, "created_at": self.created_at,
                "started_at": self.started_at, "finished_at": self.finished_at}


class JobRunner:
    def __init__(self, workers: int = 1):
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="gui-job")
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def submit(self, entrance: str, args: dict[str, Any], work: Callable[[], Any]) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], entrance=entrance, args=args)
        with self._lock:
            self._jobs[job.id] = job
        self._executor.submit(self._run, job, work)
        return job

    def _run(self, job: Job, work: Callable[[], Any]) -> None:
        job.status, job.started_at = "running", _now()
        try:
            job.result = work()
            job.status = "done"
        except Exception as error:  # 裏で走るので、落ちた理由は job に残す
            job.error = "".join(traceback.format_exception_only(type(error), error)).strip()
            job.status = "failed"
            traceback.print_exc()
        finally:
            job.finished_at = _now()

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)


runner = JobRunner()
