from __future__ import annotations

import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Mapping

from .utils import UserFacingError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOL_ENV_VARS = {
    "ffmpeg": "FFMPEG_PATH",
    "ffprobe": "FFPROBE_PATH",
}
TOOL_CONFIG_FIELDS = {
    "ffmpeg": "ffmpeg_path",
    "ffprobe": "ffprobe_path",
}


@dataclass(frozen=True)
class ExecutableStatus:
    name: str
    available: bool
    path: str = ""
    source: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def resolve_executable(
    name: str,
    explicit_path: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
    project_root: Path = PROJECT_ROOT,
) -> str:
    normalized = name.strip().lower()
    if normalized not in TOOL_ENV_VARS:
        raise ValueError(f"不支持的运行工具：{name}")

    bundled = _bundled_candidate(normalized, project_root)
    if bundled.is_file():
        return str(bundled.resolve())

    if explicit_path:
        return _resolve_configured_candidate(
            normalized,
            explicit_path,
            source=f"配置项 {TOOL_CONFIG_FIELDS[normalized]}",
        )

    env = os.environ if environ is None else environ
    env_var = TOOL_ENV_VARS[normalized]
    env_value = str(env.get(env_var) or "").strip()
    if env_value:
        return _resolve_configured_candidate(normalized, env_value, source=f"环境变量 {env_var}")

    discovered = which(normalized)
    if discovered:
        return str(Path(discovered).expanduser().resolve())

    for candidate in _legacy_project_candidates(normalized, project_root):
        if candidate.is_file():
            return str(candidate.resolve())

    raise UserFacingError(_missing_message(normalized))


def executable_status(
    name: str,
    explicit_path: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
    project_root: Path = PROJECT_ROOT,
) -> ExecutableStatus:
    try:
        path = resolve_executable(
            name,
            explicit_path,
            environ=environ,
            which=which,
            project_root=project_root,
        )
    except UserFacingError as exc:
        return ExecutableStatus(name=name, available=False, error=str(exc))
    return ExecutableStatus(
        name=name,
        available=True,
        path=path,
        source=_resolution_source(name, explicit_path, environ=environ, which=which, project_root=project_root),
    )


def runtime_tool_statuses(
    *,
    ffmpeg_path: str | Path | None = None,
    ffprobe_path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
    project_root: Path = PROJECT_ROOT,
) -> list[ExecutableStatus]:
    return [
        executable_status(
            "ffmpeg",
            ffmpeg_path,
            environ=environ,
            which=which,
            project_root=project_root,
        ),
        executable_status(
            "ffprobe",
            ffprobe_path,
            environ=environ,
            which=which,
            project_root=project_root,
        ),
    ]


def _resolve_configured_candidate(name: str, value: str | Path, *, source: str) -> str:
    raw = Path(value).expanduser()
    candidates = _configured_candidates(raw, name)
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())
    checked = "、".join(str(candidate) for candidate in candidates)
    raise UserFacingError(f"{source} 指向的 {name} 不可用。已检查：{checked}")


def _configured_candidates(path: Path, name: str) -> list[Path]:
    if path.is_dir():
        return [path / executable_name for executable_name in _executable_names(name)]
    return [path]


def _project_candidates(name: str, project_root: Path) -> list[Path]:
    return [_bundled_candidate(name, project_root), *_legacy_project_candidates(name, project_root)]


def _bundled_candidate(name: str, project_root: Path) -> Path:
    executable_name = f"{name}.exe" if os.name == "nt" else name
    windows_name = f"{name}.exe"
    preferred = project_root / "tools" / "ffmpeg" / "bin" / executable_name
    if preferred.is_file() or executable_name == windows_name:
        return preferred
    return project_root / "tools" / "ffmpeg" / "bin" / windows_name


def _legacy_project_candidates(name: str, project_root: Path) -> list[Path]:
    result: list[Path] = []
    for executable_name in _executable_names(name):
        result.extend(
            [
                project_root / "tools" / executable_name,
                project_root / "bin" / executable_name,
                project_root / "vendor" / "ffmpeg" / "bin" / executable_name,
                project_root / "ffmpeg" / "bin" / executable_name,
                project_root / ".tools" / "ffmpeg" / "bin" / executable_name,
            ]
        )
    return result


def _executable_names(name: str) -> tuple[str, ...]:
    return (f"{name}.exe", name) if os.name == "nt" else (name, f"{name}.exe")


def _resolution_source(
    name: str,
    explicit_path: str | Path | None,
    *,
    environ: Mapping[str, str] | None,
    which: Callable[[str], str | None],
    project_root: Path,
) -> str:
    if _bundled_candidate(name, project_root).is_file():
        return "bundled"
    if explicit_path:
        return f"config:{TOOL_CONFIG_FIELDS[name]}"
    env = os.environ if environ is None else environ
    if str(env.get(TOOL_ENV_VARS[name]) or "").strip():
        return f"env:{TOOL_ENV_VARS[name]}"
    if which(name):
        return "PATH"
    if any(candidate.is_file() for candidate in _legacy_project_candidates(name, project_root)):
        return "project"
    return ""


def _missing_message(name: str) -> str:
    label = "FFmpeg" if name == "ffmpeg" else "FFprobe"
    return (
        f"未找到 {label} 可执行文件（{name}）。"
        f"请设置配置项 {TOOL_CONFIG_FIELDS[name]}、环境变量 {TOOL_ENV_VARS[name]}，"
        f"或将 {name} 加入当前 PATH。也可以放入项目 tools/ffmpeg/bin/。"
        "项目不会自动下载二进制文件。"
    )
