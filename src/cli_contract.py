from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, TextIO


CLI_SCHEMA_VERSION = "1.0"
EVENT_SCHEMA_VERSION = "1.0"
TASK_SCHEMA_VERSION = "1.0"


class ExitCode(IntEnum):
    SUCCESS = 0
    EXECUTION_FAILED = 1
    USAGE_OR_CONFIG = 2
    INPUT_INACCESSIBLE = 3
    PROVIDER_NOT_CONFIGURED = 4
    EXTERNAL_TOOL_MISSING = 5
    KNOWLEDGE_PACKAGE_DAMAGED = 6
    CANCELLED = 7
    RETRYABLE_FAILURE = 8


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def result_envelope(
    command: str,
    data: dict[str, Any] | None = None,
    *,
    success: bool = True,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": CLI_SCHEMA_VERSION,
        "command": command,
        "success": success,
        "timestamp": utc_timestamp(),
        "data": data or {},
    }
    if error:
        payload["error"] = error
    return payload


def error_object(code: ExitCode, message: str, *, retryable: bool = False) -> dict[str, Any]:
    return {
        "code": code.name.lower(),
        "exit_code": int(code),
        "message": sanitize_message(message),
        "retryable": retryable,
    }


def sanitize_message(message: str) -> str:
    sanitized = str(message)
    for name, value in os.environ.items():
        if not value or not any(marker in name.upper() for marker in ("API_KEY", "TOKEN", "SECRET", "PASSWORD")):
            continue
        sanitized = sanitized.replace(value, "[REDACTED]")
    sanitized = re.sub(
        r"(?i)(api[_-]?key|authorization|access[_-]?token|secret|password)(\s*[:=]\s*)([^\s,;]+)",
        r"\1\2[REDACTED]",
        sanitized,
    )
    return sanitized


@dataclass
class CliEmitter:
    command: str
    json_output: bool = False
    jsonl_output: bool = False
    stdout: TextIO = field(default_factory=lambda: sys.stdout)
    stderr: TextIO = field(default_factory=lambda: sys.stderr)

    def __post_init__(self) -> None:
        if self.json_output and self.jsonl_output:
            raise ValueError("--json 和 --jsonl 不能同时使用。")

    def diagnostic(self, message: str) -> None:
        print(sanitize_message(message), file=self.stderr, flush=True)

    def event(self, event: str, *, task_id: str = "", **fields: Any) -> None:
        if not self.jsonl_output:
            return
        payload = {
            "schema_version": EVENT_SCHEMA_VERSION,
            "event": event,
            "task_id": task_id,
            "timestamp": utc_timestamp(),
            **fields,
        }
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), file=self.stdout, flush=True)

    def result(
        self,
        data: dict[str, Any],
        *,
        success: bool = True,
        error: dict[str, Any] | None = None,
    ) -> None:
        if self.jsonl_output:
            return
        if self.json_output:
            print(
                json.dumps(
                    result_envelope(self.command, data, success=success, error=error),
                    ensure_ascii=False,
                    indent=2,
                ),
                file=self.stdout,
            )
            return
        for key, value in data.items():
            if value not in (None, "", [], {}):
                print(f"{key}: {value}", file=self.stdout)

    def failure(self, code: ExitCode, message: str, *, task_id: str = "") -> None:
        message = sanitize_message(message)
        error = error_object(code, message, retryable=code == ExitCode.RETRYABLE_FAILURE)
        if self.jsonl_output:
            self.event("task_failed", task_id=task_id, error=error)
        elif self.json_output:
            print(
                json.dumps(
                    result_envelope(
                        self.command,
                        {"task_id": task_id} if task_id else {},
                        success=False,
                        error=error,
                    ),
                    ensure_ascii=False,
                    indent=2,
                ),
                file=self.stdout,
            )
        else:
            self.diagnostic(message)


def classify_error(message: str) -> ExitCode:
    normalized = message.lower()
    if any(value in normalized for value in ("api_key", "未配置", "provider")):
        return ExitCode.PROVIDER_NOT_CONFIGURED
    if any(value in normalized for value in ("ffmpeg", "ffprobe", "yt-dlp", "faster-whisper", "模型不可用", "命令不存在")):
        return ExitCode.EXTERNAL_TOOL_MISSING
    if any(value in normalized for value in ("不存在", "不可访问", "找不到文件", "输入格式", "不支持的媒体")):
        return ExitCode.INPUT_INACCESSIBLE
    if any(value in normalized for value in ("schema", "知识包完整性", "知识包损坏")):
        return ExitCode.KNOWLEDGE_PACKAGE_DAMAGED
    if any(value in normalized for value in ("429", "timeout", "timed out", "暂时", "临时失败")):
        return ExitCode.RETRYABLE_FAILURE
    return ExitCode.EXECUTION_FAILED
