from __future__ import annotations

from typing import Any


class UnsupportedSchemaVersion(ValueError):
    """Raised when persisted data requires a newer incompatible schema."""


def schema_major(value: Any, *, default: int = 1) -> int:
    text = str(value or "").strip()
    if not text:
        return default
    head = text.split(".", 1)[0]
    try:
        major = int(head)
    except ValueError as exc:
        raise UnsupportedSchemaVersion(f"Schema 版本格式无效：{value}") from exc
    if major < 1:
        raise UnsupportedSchemaVersion(f"Schema 版本必须大于 0：{value}")
    return major


def require_supported_schema(
    value: Any,
    *,
    supported_major: int,
    object_name: str,
    legacy_default: int = 1,
) -> str:
    major = schema_major(value, default=legacy_default)
    if major > supported_major:
        raise UnsupportedSchemaVersion(
            f"不支持的{object_name} Schema 版本 {value}；当前最高支持主版本 {supported_major}。"
        )
    return str(value or legacy_default)
