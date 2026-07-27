from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from rich.console import Console
except ImportError:
    class Console:  # type: ignore[no-redef]
        def print(self, *values: object, **_: object) -> None:
            print(*values)


console = Console()

INVALID_FILENAME_CHARS = r'<>:"/\|?*'


class UserFacingError(Exception):
    """Error with a clear message intended for CLI users."""


class ConfigRequiredError(UserFacingError):
    """A required local dependency or user configuration is missing."""


def is_timeout_error(exc: BaseException | str) -> bool:
    text = str(exc).lower()
    return isinstance(exc, TimeoutError) or any(
        marker in text
        for marker in ("timeout", "timed out", "超时", "请求时间过长")
    )


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def sanitize_filename(value: str, fallback: str = "video") -> str:
    cleaned = "".join("_" if ch in INVALID_FILENAME_CHARS else ch for ch in value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().strip(".")
    return cleaned[:120] or fallback


def save_json(path: Path, data: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def format_seconds(seconds: float | int | None) -> str:
    if seconds is None:
        return "未知"
    total = int(float(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def run_command(
    args: list[str],
    cwd: Path | None = None,
    *,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise UserFacingError(f"命令不存在：{args[0]}。请确认已安装并加入 PATH。") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise UserFacingError(f"外部命令执行失败：{' '.join(args)}\n{detail}") from exc
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(
            f"外部命令执行超时（{timeout:.0f} 秒）：{args[0]}"
        ) from exc


def write_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def safe_unlink(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError:
        console.print(f"[yellow]临时文件删除失败，可手动清理：{path}[/yellow]")
