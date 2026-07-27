from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .processing_profiles import ProcessingProfile, normalize_processing_profile
from .schema_compat import UnsupportedSchemaVersion, require_supported_schema
from .utils import UserFacingError


SCHEMA_VERSION = "1.0"
MAX_JOBS = 200
MAX_LOG_LINES = 400


@dataclass
class Job:
    id: str
    command: list[str]
    schema_version: str = SCHEMA_VERSION
    analysis_profile: str = "summary"
    processing_profile: ProcessingProfile = "complete"
    analysis_requested: bool = True
    analysis_status: str = "pending"
    analysis_skip_reason: str = ""
    analysis_provider: str = ""
    analysis_model: str = ""
    transcript_only: bool = False
    transcript_status: str = "pending"
    transcript_provider: str = ""
    transcript_model: str = ""
    transcript_route_requested: str = "cloud"
    transcript_fallback_used: bool = False
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    status: str = "queued"
    returncode: int | None = None
    logs: list[str] = field(default_factory=list)
    cli_task_id: str = ""
    knowledge_id: str = ""
    output_dir: str = ""
    error: str = ""

    def to_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["logs"] = self.logs[-MAX_LOG_LINES:]
        return record

    @classmethod
    def from_record(cls, value: dict[str, Any]) -> "Job":
        try:
            schema_version = require_supported_schema(
                value.get("schema_version"), supported_major=1, object_name="Web 任务记录"
            )
        except UnsupportedSchemaVersion as exc:
            raise UserFacingError(str(exc)) from exc
        try:
            processing_profile = normalize_processing_profile(value.get("processing_profile"))
        except ValueError as exc:
            raise UserFacingError(f"Web 任务记录损坏：{exc}") from exc
        command = [
            str(item)
            for item in value.get("command", [])
            if isinstance(item, (str, int, float))
        ]
        legacy_transcript_only = "--no-summary" in command
        analysis_requested = bool(
            value.get("analysis_requested", not legacy_transcript_only)
        )
        transcript_only = bool(
            value.get("transcript_only", legacy_transcript_only)
        )
        return cls(
            id=str(value.get("id") or ""),
            command=command,
            schema_version=schema_version,
            analysis_profile=str(value.get("analysis_profile") or "summary"),
            processing_profile=processing_profile,
            analysis_requested=analysis_requested,
            analysis_status=str(
                value.get("analysis_status")
                or ("skipped" if transcript_only else "pending")
            ),
            analysis_skip_reason=str(
                value.get("analysis_skip_reason")
                or ("user_requested_transcript_only" if transcript_only else "")
            ),
            analysis_provider=str(value.get("analysis_provider") or ""),
            analysis_model=str(value.get("analysis_model") or ""),
            transcript_only=transcript_only,
            transcript_status=str(value.get("transcript_status") or "pending"),
            transcript_provider=str(value.get("transcript_provider") or ""),
            transcript_model=str(value.get("transcript_model") or ""),
            transcript_route_requested=str(value.get("transcript_route_requested") or "cloud"),
            transcript_fallback_used=bool(value.get("transcript_fallback_used", False)),
            created_at=float(value.get("created_at") or time.time()),
            updated_at=float(value.get("updated_at") or value.get("created_at") or time.time()),
            started_at=_optional_float(value.get("started_at")),
            finished_at=_optional_float(value.get("finished_at")),
            status=str(value.get("status") or "failed"),
            returncode=_optional_int(value.get("returncode")),
            logs=[str(item) for item in value.get("logs", []) if isinstance(item, str)][-MAX_LOG_LINES:],
            cli_task_id=str(value.get("cli_task_id") or ""),
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
            if isinstance(payload, dict) and payload:
                try:
                    require_supported_schema(
                        payload.get("schema_version"), supported_major=1, object_name="Web 任务存储"
                    )
                except UnsupportedSchemaVersion as exc:
                    raise UserFacingError(str(exc)) from exc
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
        temporary_path = self.path.with_name(
            f"{self.path.name}.{os.getpid()}.{threading.get_ident()}.{time.time_ns()}.tmp"
        )
        try:
            with temporary_path.open("x", encoding="utf-8") as temporary:
                json.dump(payload, temporary, ensure_ascii=False, indent=2)
                temporary.write("\n")
                temporary.flush()
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()


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
