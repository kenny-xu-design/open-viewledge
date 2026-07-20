from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .cli_contract import TASK_SCHEMA_VERSION, utc_timestamp
from .schema_compat import require_supported_schema
from .utils import UserFacingError


class CliTaskRecord(BaseModel):
    schema_version: str = TASK_SCHEMA_VERSION
    task_id: str
    status: Literal["created", "running", "completed", "failed", "cancelled"] = "created"
    source_type: Literal["url", "file"]
    source: str
    options: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_timestamp)
    updated_at: str = Field(default_factory=utc_timestamp)
    output_dir: str = ""
    knowledge_id: str = ""
    exit_code: int | None = None
    error_code: str = ""
    error_message: str = ""

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        return require_supported_schema(value, supported_major=1, object_name="任务记录")


class CliTaskStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path_for(self, task_id: str) -> Path:
        normalized = task_id.strip()
        if not normalized or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in normalized):
            raise UserFacingError("task_id 格式无效。")
        return self.root / f"{normalized}.json"

    def save(self, record: CliTaskRecord) -> None:
        record.updated_at = utc_timestamp()
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.path_for(record.task_id)
        handle, temporary_name = tempfile.mkstemp(prefix="cli-task-", suffix=".json", dir=self.root)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as temporary:
                json.dump(record.model_dump(mode="json"), temporary, ensure_ascii=False, indent=2)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, target)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    def load(self, task_id: str) -> CliTaskRecord:
        path = self.path_for(task_id)
        if not path.is_file():
            raise UserFacingError(f"任务记录不存在：{task_id}")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("顶层不是对象")
            return CliTaskRecord.model_validate(value)
        except (OSError, ValueError) as exc:
            raise UserFacingError(f"任务记录损坏：{task_id}：{exc}") from exc
