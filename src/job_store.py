from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
MAX_JOBS = 200
MAX_LOG_LINES = 400


@dataclass
class Job:
    id: str
    command: list[str]
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    status: str = "queued"
    returncode: int | None = None
    logs: list[str] = field(default_factory=list)
    knowledge_id: str = ""
    output_dir: str = ""
    error: str = ""

    def to_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["logs"] = self.logs[-MAX_LOG_LINES:]
        return record

    @classmethod
    def from_record(cls, value: dict[str, Any]) -> "Job":
        return cls(
            id=str(value.get("id") or ""),
            command=[str(item) for item in value.get("command", []) if isinstance(item, (str, int, float))],
            created_at=float(value.get("created_at") or time.time()),
            updated_at=float(value.get("updated_at") or value.get("created_at") or time.time()),
            started_at=_optional_float(value.get("started_at")),
            finished_at=_optional_float(value.get("finished_at")),
            status=str(value.get("status") or "failed"),
            returncode=_optional_int(value.get("returncode")),
            logs=[str(item) for item in value.get("logs", []) if isinstance(item, str)][-MAX_LOG_LINES:],
            knowledge_id=str(value.get("knowledge_id") or ""),
            output_dir=str(value.get("output_dir") or ""),
            error=str(value.get("error") or ""),
        )


class JobStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._jobs: dict[str, Job] | None = None

    def load_jobs(self) -> list[Job]:
        with self._lock:
            self._ensure_loaded()
            assert self._jobs is not None
            return sorted(self._jobs.values(), key=lambda item: item.created_at, reverse=True)

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            self._ensure_loaded()
            assert self._jobs is not None
            return self._jobs.get(job_id)

    def upsert(self, job: Job) -> None:
        with self._lock:
            self._ensure_loaded()
            assert self._jobs is not None
            job.updated_at = time.time()
            self._jobs[job.id] = job
            ordered = sorted(self._jobs.values(), key=lambda item: item.created_at, reverse=True)[:MAX_JOBS]
            self._jobs = {item.id: item for item in ordered}
            self._write()

    def _ensure_loaded(self) -> None:
        if self._jobs is not None:
            return
        jobs: dict[str, Job] = {}
        if self.path.exists():
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
            values = payload.get("jobs", []) if isinstance(payload, dict) else []
            for value in values if isinstance(values, list) else []:
                if not isinstance(value, dict):
                    continue
                job = Job.from_record(value)
                if job.id:
                    jobs[job.id] = job
        self._jobs = jobs
        changed = False
        now = time.time()
        for job in self._jobs.values():
            if job.status in {"queued", "running"}:
                job.status = "interrupted"
                job.finished_at = now
                job.updated_at = now
                job.error = job.error or "Web 服务重启，任务运行状态已中断。"
                changed = True
        if changed:
            self._write()

    def _write(self) -> None:
        assert self._jobs is not None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "jobs": [
                item.to_record()
                for item in sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)
            ],
        }
        handle, temporary_name = tempfile.mkstemp(prefix="web-jobs-", suffix=".json", dir=self.path.parent)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as temporary:
                json.dump(payload, temporary, ensure_ascii=False, indent=2)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, self.path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
