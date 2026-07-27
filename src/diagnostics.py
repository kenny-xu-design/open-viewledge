from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .config import AppConfig, resolve_output_root
from .providers.llm import ProviderRegistry
from .runtime_tools import runtime_tool_statuses


DIAGNOSTIC_SCHEMA_VERSION = "1.0"


def run_doctor(config: AppConfig, *, project_root: Path) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    checks.append(_check("python", True, sys.version.split()[0], required=True))
    checks.append(_check("package_version", True, __version__, required=True))
    checks.append(_check("schema", True, DIAGNOSTIC_SCHEMA_VERSION, required=True))

    for module_name, label in (("yt_dlp", "yt-dlp"), ("faster_whisper", "faster-whisper")):
        available = importlib.util.find_spec(module_name) is not None
        checks.append(_check(label, available, "available" if available else "missing", required=module_name == "yt_dlp"))

    for status in runtime_tool_statuses(
        ffmpeg_path=config.ffmpeg_path,
        ffprobe_path=config.ffprobe_path,
        project_root=project_root,
    ):
        checks.append(_check(status.name, status.available, status.path or status.error, required=True))

    model_root = _whisper_model_path(config, project_root)
    required_model_files = ("model.bin", "config.json", "tokenizer.json", "vocabulary.txt")
    model_ready = all((model_root / name).is_file() for name in required_model_files)
    checks.append(_check("whisper_model", model_ready, str(model_root), required=False))

    providers = ProviderRegistry().statuses()
    for provider in providers:
        checks.append(
            _check(
                f"provider:{provider['name']}",
                bool(provider["configured"]),
                f"model={provider['model']}; capabilities={','.join(provider['capabilities'])}",
                required=False,
            )
        )

    output_root = resolve_output_root(config, project_root)
    checks.append(_writable_check("output_dir", output_root, required=True))
    checks.append(_writable_check("web_data_store", project_root / ".local", required=True))

    if config.obsidian_vault_path:
        checks.append(_writable_check("obsidian_vault", Path(config.obsidian_vault_path).expanduser(), required=False))
    else:
        checks.append(_check("obsidian_vault", False, "not configured", required=False))

    errors = [item for item in checks if item["required"] and item["status"] == "error"]
    warnings = [item for item in checks if not item["required"] and item["status"] != "ok"]
    return {
        "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
        "healthy": not errors,
        "checks": checks,
        "summary": {"ok": len(checks) - len(errors) - len(warnings), "errors": len(errors), "warnings": len(warnings)},
    }


def _check(name: str, available: bool, detail: str, *, required: bool) -> dict[str, Any]:
    return {
        "name": name,
        "status": "ok" if available else "error" if required else "warning",
        "required": required,
        "detail": detail,
    }


def _writable_check(name: str, path: Path, *, required: bool) -> dict[str, Any]:
    target = path.expanduser().resolve()
    temporary_path = target / f".viewledge-doctor-{os.getpid()}.tmp"
    try:
        target.mkdir(parents=True, exist_ok=True)
        handle = os.open(
            temporary_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        )
        os.close(handle)
        temporary_path.unlink()
        return _check(name, True, str(target), required=required)
    except OSError as exc:
        return _check(name, False, f"{target}: {exc}", required=required)
    finally:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass


def _whisper_model_path(config: AppConfig, project_root: Path) -> Path:
    value = Path(config.whisper_model).expanduser()
    if value.is_absolute() or any(separator in config.whisper_model for separator in ("/", "\\")):
        return value if value.is_absolute() else project_root / value
    return project_root / "models" / f"faster-whisper-{config.whisper_model}"
