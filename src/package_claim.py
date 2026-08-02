from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .utils import UserFacingError, ensure_dir


PACKAGE_CLAIM_SCHEMA_VERSION = "1.0"
DEFAULT_STALE_AFTER_SECONDS = 6 * 60 * 60
_SAFE_CLAIM_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


class PackageClaimLocked(UserFacingError):
    def __init__(
        self,
        *,
        knowledge_id: str,
        task_id: str = "",
        updated_at_epoch: float = 0.0,
    ) -> None:
        self.knowledge_id = knowledge_id
        self.task_id = task_id
        self.updated_at_epoch = updated_at_epoch
        suffix = f"; current task: {task_id}" if task_id else ""
        super().__init__(f"Knowledge package is locked by another task. Try again later{suffix}.")


@dataclass(frozen=True, slots=True)
class PackageClaim:
    root: Path
    path: Path
    knowledge_id: str
    request_fingerprint: str
    task_id: str
    output_dir: Path
    recovered_from_task_id: str = ""

    def refresh(self, *, now: float | None = None) -> None:
        existing = _read_claim(self.path)
        existing_task_id = str(existing.get("task_id") or "")
        if existing_task_id and existing_task_id != self.task_id:
            raise PackageClaimLocked(
                knowledge_id=self.knowledge_id,
                task_id=existing_task_id,
                updated_at_epoch=_updated_at_epoch(existing, self.path),
            )
        payload = _record_payload(
            root=self.root,
            knowledge_id=self.knowledge_id,
            request_fingerprint=self.request_fingerprint,
            task_id=self.task_id,
            output_dir=self.output_dir,
            created_at_epoch=_existing_created_at(self.path, now or time.time()),
            updated_at_epoch=now or time.time(),
            recovered_from_task_id=self.recovered_from_task_id,
        )
        _write_claim_atomic(self.path, payload)

    def release(self) -> None:
        payload = _read_claim(self.path)
        if str(payload.get("task_id") or "") != self.task_id:
            return
        try:
            self.path.unlink()
        except FileNotFoundError:
            return


def package_claim_path(root: Path, knowledge_id: str) -> Path:
    safe_name = _SAFE_CLAIM_NAME_RE.sub("-", knowledge_id.strip()).strip(".-")
    if not safe_name:
        raise ValueError("knowledge_id cannot be empty.")
    return root / ".viewledge_claims" / f"{safe_name}.json"


def acquire_package_claim(
    root: Path,
    *,
    knowledge_id: str,
    request_fingerprint: str,
    task_id: str,
    output_dir: Path,
    stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
    now: float | None = None,
) -> PackageClaim:
    if stale_after_seconds <= 0:
        raise ValueError("stale_after_seconds must be greater than zero.")
    timestamp = time.time() if now is None else now
    root = root.resolve()
    path = package_claim_path(root, knowledge_id)
    ensure_dir(path.parent)
    recovered_from_task_id = ""
    for _attempt in range(3):
        payload = _record_payload(
            root=root,
            knowledge_id=knowledge_id,
            request_fingerprint=request_fingerprint,
            task_id=task_id,
            output_dir=output_dir,
            created_at_epoch=timestamp,
            updated_at_epoch=timestamp,
            recovered_from_task_id=recovered_from_task_id,
        )
        try:
            with path.open("x", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            existing = _read_claim(path)
            existing_task_id = str(existing.get("task_id") or "")
            if existing_task_id == task_id:
                claim = PackageClaim(
                    root=root,
                    path=path,
                    knowledge_id=knowledge_id,
                    request_fingerprint=request_fingerprint,
                    task_id=task_id,
                    output_dir=output_dir,
                    recovered_from_task_id=str(existing.get("recovered_from_task_id") or ""),
                )
                claim.refresh(now=timestamp)
                return claim
            existing_updated_at = _updated_at_epoch(existing, path)
            if timestamp - existing_updated_at <= stale_after_seconds:
                raise PackageClaimLocked(
                    knowledge_id=knowledge_id,
                    task_id=existing_task_id,
                    updated_at_epoch=existing_updated_at,
                )
            recovered_from_task_id = existing_task_id
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            continue
        return PackageClaim(
            root=root,
            path=path,
            knowledge_id=knowledge_id,
            request_fingerprint=request_fingerprint,
            task_id=task_id,
            output_dir=output_dir,
            recovered_from_task_id=recovered_from_task_id,
        )
    raise PackageClaimLocked(knowledge_id=knowledge_id)


def _record_payload(
    *,
    root: Path,
    knowledge_id: str,
    request_fingerprint: str,
    task_id: str,
    output_dir: Path,
    created_at_epoch: float,
    updated_at_epoch: float,
    recovered_from_task_id: str = "",
) -> dict[str, Any]:
    return {
        "schema_version": PACKAGE_CLAIM_SCHEMA_VERSION,
        "knowledge_id": knowledge_id,
        "request_fingerprint": request_fingerprint,
        "task_id": task_id,
        "output_dir": _relative_output_dir(root, output_dir),
        "created_at_epoch": created_at_epoch,
        "updated_at_epoch": updated_at_epoch,
        "recovered_from_task_id": recovered_from_task_id,
    }


def _write_claim_atomic(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _read_claim(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _existing_created_at(path: Path, fallback: float) -> float:
    existing = _read_claim(path)
    try:
        return float(existing.get("created_at_epoch") or fallback)
    except (TypeError, ValueError):
        return fallback


def _updated_at_epoch(payload: dict[str, Any], path: Path) -> float:
    try:
        return float(payload.get("updated_at_epoch") or 0)
    except (TypeError, ValueError):
        pass
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _relative_output_dir(root: Path, output_dir: Path) -> str:
    try:
        return output_dir.resolve().relative_to(root).as_posix()
    except (OSError, ValueError):
        return output_dir.name
