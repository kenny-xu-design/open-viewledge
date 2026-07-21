from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import os
import re
import shutil
import stat
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse

from . import __version__
from .cli_contract import sanitize_message
from .analysis.retry import reanalyze_knowledge_package
from .chat import answer_question
from .chat_store import ChatStore
from .config import load_config
from .exporters import export_directory_to_vault, refresh_compatible_export, render_directory_export, selection_for_request
from .job_store import Job, JobStore
from .knowledge_validation import inspect_knowledge_package
from .note_store import NoteConflictError, NoteStore
from .providers.llm import ProviderRegistry
from .runtime_tools import runtime_tool_statuses
from .utils import UserFacingError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = PROJECT_ROOT / "output"
WEB_UI_ROOT = Path(__file__).resolve().parent / "web_ui"
LOCAL_STATE_ROOT = PROJECT_ROOT / ".local"
SUPPORTED_MODES = {"summary", "tutorial", "viral", "close-reading"}
SUPPORTED_BACKENDS = {"deepseek"}
SUPPORTED_EXPORTS = {"none", "obsidian"}
LIBRARY_FILES = {
    "index.md",
    "metadata.json",
    "manifest.json",
    "analysis.json",
    "timeline.json",
    "transcript.grouped.md",
    "transcript.raw.jsonl",
    "transcript.md",
    "source.md",
    "export_note.md",
    "user_notes.md",
}
MEDIA_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm", ".m4v", ".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus"}

JOB_STORE = JobStore(LOCAL_STATE_ROOT / "web_jobs.json")
JOBS: dict[str, Job] = {job.id: job for job in JOB_STORE.load_jobs()}
JOBS_LOCK = threading.RLock()
LOGGER = logging.getLogger(__name__)


class KnowledgeDeletionError(RuntimeError):
    def __init__(self, code: str, message: str, target: Path, cause: OSError, deleted: list[str] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.target = target
        self.cause = cause
        self.deleted = list(deleted or [])


def build_cli_command(payload: dict[str, Any], python_executable: str | None = None) -> list[str]:
    python_executable = python_executable or sys.executable
    source_type = str(payload.get("sourceType") or "url")
    source = _clean_source_value(str(payload.get("source") or ""))
    if source_type not in {"url", "file"}:
        raise ValueError("sourceType 只能是 url 或 file。")
    if not source:
        raise ValueError("请填写视频链接或本地文件路径。")

    backend = str(payload.get("backend") or "deepseek")
    mode = str(payload.get("mode") or "summary")
    export = str(payload.get("export") or "none")
    lang = str(payload.get("lang") or "").strip()

    if backend not in SUPPORTED_BACKENDS:
        raise ValueError("旧 AI 后端已停用，backend 只能是 deepseek。")
    if mode not in SUPPORTED_MODES:
        raise ValueError("mode 参数不合法。")
    if export not in SUPPORTED_EXPORTS:
        raise ValueError("export 参数不合法。")

    command = [python_executable, "-m", "src.main", "analyze"]
    command.extend(["--url" if source_type == "url" else "--file", source])
    if lang:
        command.extend(["--lang", lang])
    command.extend(["--backend", backend, "--mode", mode])
    if payload.get("noFrames"):
        command.append("--no-frames")
    if export != "none":
        command.extend(["--export", export])
    if payload.get("noSummary"):
        command.append("--no-summary")
    sample_seconds = payload.get("sampleSeconds")
    if sample_seconds not in (None, ""):
        try:
            sample_value = int(sample_seconds)
        except (TypeError, ValueError) as exc:
            raise ValueError("sampleSeconds 必须是正整数。") from exc
        if sample_value <= 0:
            raise ValueError("sampleSeconds 必须是正整数。")
        command.extend(["--sample-seconds", str(sample_value)])
    command.append("--jsonl")
    return command


def _clean_source_value(value: str) -> str:
    cleaned = value.strip()
    quote_pairs = {('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’")}
    for left, right in quote_pairs:
        if cleaned.startswith(left) and cleaned.endswith(right):
            return cleaned[1:-1].strip()
    return cleaned


def start_job(payload: dict[str, Any]) -> Job:
    command = build_cli_command(payload)
    job = Job(id=uuid.uuid4().hex[:12], command=command)
    with JOBS_LOCK:
        JOBS[job.id] = job
        try:
            _persist_job(job, strict=True)
        except OSError:
            JOBS.pop(job.id, None)
            raise
    thread = threading.Thread(target=_run_job, args=(job,), daemon=True)
    thread.start()
    return job


def _run_job(job: Job) -> None:
    before = _snapshot_output_dirs()
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    job.status = "running"
    job.started_at = time.time()
    _persist_job(job)
    try:
        _append_runtime_logs(job)
        _persist_job(job)
        process = subprocess.Popen(
            job.command,
            cwd=PROJECT_ROOT,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        assert process.stdout is not None
        for line in process.stdout:
            _handle_cli_output_line(job, line.rstrip())
        job.returncode = process.wait()
        if not job.output_dir:
            job.output_dir = _find_new_output_dir(before)
        job.knowledge_id = Path(job.output_dir).name if job.output_dir else ""
        job.status = "success" if job.returncode == 0 else "failed"
        if job.returncode != 0 and not job.error:
            job.error = f"CLI 退出码：{job.returncode}"
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)
        _append_log(job, f"处理失败：{exc}")
    finally:
        job.finished_at = time.time()
        _persist_job(job)


def _handle_cli_output_line(job: Job, line: str) -> None:
    if not line:
        return
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        _append_log(job, line)
        return
    if not isinstance(payload, dict) or not payload.get("event"):
        _append_log(job, line)
        return
    event = str(payload.get("event"))
    if event == "task_created":
        job.cli_task_id = str(payload.get("task_id") or "")
    elif event == "task_completed" and isinstance(payload.get("result"), dict):
        result = payload["result"]
        job.output_dir = str(result.get("output_dir") or "")
        job.knowledge_id = str(result.get("knowledge_id") or "")
    elif event == "task_failed" and isinstance(payload.get("error"), dict):
        job.error = str(payload["error"].get("message") or "")
    stage = str(payload.get("stage") or "")
    progress = payload.get("progress")
    detail = f"{event}{' ' + stage if stage else ''}"
    if isinstance(progress, (int, float)):
        detail += f" {float(progress):.0%}"
    _append_log(job, detail)


def _append_runtime_logs(job: Job) -> None:
    _append_log(job, f"当前 Python 路径：{sys.executable}")
    _append_log(job, f"当前工作目录：{PROJECT_ROOT}")
    warning = _runtime_python_warning()
    if warning:
        _append_log(job, warning)


def _runtime_python_warning(python_executable: str | None = None) -> str:
    if _is_project_venv_python(python_executable):
        return ""
    return "当前 Web UI 未运行在项目虚拟环境中，可能缺少 yt-dlp / faster-whisper 等依赖。"


def runtime_status_payload() -> dict[str, Any]:
    config = load_config(PROJECT_ROOT / "config.example.json")
    tools = [
        item.to_dict()
        for item in runtime_tool_statuses(
            ffmpeg_path=config.ffmpeg_path,
            ffprobe_path=config.ffprobe_path,
            project_root=PROJECT_ROOT,
        )
    ]
    return {
        "version": __version__,
        "pythonExecutable": sys.executable,
        "projectRoot": str(PROJECT_ROOT),
        "inProjectVenv": _is_project_venv_python(),
        "warning": _runtime_python_warning(),
        "tools": tools,
        "providers": ProviderRegistry().statuses(),
    }


def _is_project_venv_python(python_executable: str | None = None) -> bool:
    python_path = Path(python_executable or sys.executable).resolve()
    venv_root = (PROJECT_ROOT / ".venv").resolve()
    try:
        python_path.relative_to(venv_root)
        return True
    except ValueError:
        return str(python_path).lower().startswith(str(venv_root).lower())


def _append_log(job: Job, line: str) -> None:
    if not line:
        return
    line = sanitize_message(line)
    with JOBS_LOCK:
        job.logs.append(line)
        if len(job.logs) > 400:
            job.logs = job.logs[-400:]
        should_persist = len(job.logs) % 10 == 0
    if should_persist:
        _persist_job(job)


def _persist_job(job: Job, strict: bool = False) -> None:
    try:
        JOB_STORE.upsert(job)
    except OSError as exc:
        if strict:
            raise
        print(f"[web] 任务状态持久化失败：{exc}")


def _snapshot_output_dirs() -> dict[Path, float]:
    if not OUTPUT_ROOT.exists():
        return {}
    return {path: path.stat().st_mtime for path in OUTPUT_ROOT.iterdir() if path.is_dir()}


def _find_new_output_dir(before: dict[Path, float]) -> str:
    if not OUTPUT_ROOT.exists():
        return ""
    candidates = [
        path
        for path in OUTPUT_ROOT.iterdir()
        if path.is_dir() and (path not in before or path.stat().st_mtime > before[path])
    ]
    if not candidates:
        return ""
    newest = max(candidates, key=lambda path: path.stat().st_mtime)
    return str(newest.relative_to(PROJECT_ROOT)).replace("\\", "/")


def job_to_dict(job: Job) -> dict[str, Any]:
    output_files: list[dict[str, str]] = []
    output_available = False
    if job.output_dir:
        output_path = (PROJECT_ROOT / job.output_dir).resolve()
        if output_path.exists():
            output_available = True
            output_files = [
                {
                    "name": path.name,
                    "url": "/" + str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                }
                for path in sorted(output_path.iterdir())
                if path.is_file()
            ]
    return {
        "id": job.id,
        "command": job.command,
        "createdAt": job.created_at,
        "updatedAt": job.updated_at,
        "startedAt": job.started_at,
        "finishedAt": job.finished_at,
        "status": job.status,
        "returncode": job.returncode,
        "cliTaskId": job.cli_task_id,
        "logs": job.logs,
        "knowledgeId": job.knowledge_id if output_available else "",
        "outputDir": job.output_dir if output_available else "",
        "outputFiles": output_files,
        "error": job.error,
    }


def list_library_items() -> list[dict[str, Any]]:
    if not OUTPUT_ROOT.exists():
        return []
    items = []
    for directory in OUTPUT_ROOT.iterdir():
        if not _is_knowledge_package(directory):
            continue
        metadata = _load_json_file(directory / "metadata.json")
        manifest = _load_json_file(directory / "manifest.json")
        source = manifest.get("source") if isinstance(manifest.get("source"), dict) else metadata
        analysis = _load_json_file(directory / "analysis.json")
        inspection = inspect_knowledge_package(directory)
        display_status = manifest.get("status") or ("completed" if (directory / "transcript.md").exists() else "unknown")
        if inspection.level == "invalid" and str(display_status).startswith("completed"):
            display_status = "invalid"
        items.append(
            {
                "id": directory.name,
                "title": source.get("title") or metadata.get("title") or directory.name,
                "platform": source.get("platform") or metadata.get("source") or "unknown",
                "sourceType": source.get("source_type") or "unknown",
                "author": source.get("author") or metadata.get("author") or "",
                "thumbnail": source.get("thumbnail") or "",
                "status": display_status,
                "currentStage": manifest.get("current_stage") or "",
                "updatedAt": directory.stat().st_mtime,
                "hasAnalysis": bool(analysis.get("summary") or analysis.get("highlights") or analysis.get("chapters")),
                "analysisStatus": inspection.analysis_status,
                "integrity": inspection.level,
                "integrityIssues": [issue.message for issue in inspection.issues[:5]],
                "chapterCount": _timeline_count(directory),
            }
        )
    return sorted(items, key=lambda item: item["updatedAt"], reverse=True)


def load_knowledge_package(knowledge_id: str) -> dict[str, Any]:
    directory = resolve_library_dir(knowledge_id)
    metadata = _load_json_file(directory / "metadata.json")
    manifest = _load_json_file(directory / "manifest.json")
    source = manifest.get("source") if isinstance(manifest.get("source"), dict) else dict(metadata)
    source = dict(source)
    local_path = str(source.pop("local_path", "") or source.pop("source_path", "") or metadata.get("source_path") or "")
    analysis = _load_json_file(directory / "analysis.json")
    analysis.pop("raw_response", None)
    inspection = inspect_knowledge_package(directory)
    if inspection.analysis_status == "invalid":
        analysis = {
            "status": "failed",
            "error": "知识包中的 analysis.json 无效，请运行 CLI inspect 查看详情。",
        }
    manifest_view = dict(manifest)
    if inspection.level == "invalid" and str(manifest_view.get("status") or "").startswith("completed"):
        manifest_view["status"] = "invalid"
        manifest_view["errors"] = [
            *list(manifest_view.get("errors") or []),
            *[issue.message for issue in inspection.issues if issue.severity == "error"][:5],
        ]
    timeline_payload = _load_json_file(directory / "timeline.json")
    timeline = timeline_payload.get("items", []) if isinstance(timeline_payload, dict) else []
    if not isinstance(timeline, list):
        timeline = []
    encoded_id = quote(knowledge_id, safe="")
    files = {
        name: f"/api/library/{encoded_id}/file/{quote(name, safe='')}"
        for name in sorted(LIBRARY_FILES)
        if (directory / name).is_file()
    }
    frames = []
    frames_dir = directory / "frames"
    if frames_dir.is_dir():
        frames = [
            {"name": path.name, "url": f"/api/library/{encoded_id}/file/frames/{quote(path.name, safe='')}"}
            for path in sorted(frames_dir.iterdir())
            if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
        ]
    media_path = Path(local_path) if local_path else None
    media_available = bool(media_path and media_path.is_file() and media_path.suffix.lower() in MEDIA_EXTENSIONS)
    media_kind = "external"
    if media_available:
        media_kind = "audio" if media_path.suffix.lower() in {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus"} else "video"
    external_url = source.get("canonical_url") or source.get("source_url") or metadata.get("source_url") or ""
    embed = _external_player_descriptor(str(external_url))
    platform = str(source.get("platform") or metadata.get("platform") or "local").lower()
    normalized_platform = "bilibili" if platform in {"bili", "bilibili"} else platform
    if normalized_platform not in {"local", "youtube", "bilibili"}:
        normalized_platform = "generic" if external_url else "local"
    video_id = str((embed or {}).get("videoId") or source.get("video_id") or metadata.get("video_id") or "")
    return {
        "id": knowledge_id,
        "knowledge_id": knowledge_id,
        "source_type": "online_video" if external_url and not media_available else "local",
        "platform": normalized_platform,
        "source_url": external_url,
        "source_id": video_id,
        "video_id": video_id,
        "thumbnail": source.get("thumbnail") or metadata.get("thumbnail") or "",
        "duration": float(source.get("duration") or metadata.get("duration") or 0),
        "status": manifest_view.get("status") or "unknown",
        "currentStage": manifest_view.get("current_stage") or "",
        "source": source,
        "manifest": manifest_view,
        "analysis": analysis,
        "inspection": inspection.to_dict(),
        "timeline": timeline,
        "files": files,
        "frames": frames,
        "media": {
            "kind": media_kind,
            "available": media_available,
            "url": f"/api/library/{encoded_id}/media" if media_available else "",
            "externalUrl": external_url,
            "thumbnail": source.get("thumbnail") or metadata.get("thumbnail") or "",
            "embed": embed,
        },
    }


def _external_player_descriptor(source_url: str) -> dict[str, str] | None:
    """Return an allow-listed official player descriptor for supported platforms."""
    if not source_url:
        return None
    parsed = urlparse(source_url)
    host = parsed.netloc.lower().split(":", 1)[0]
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}:
        video_id = ""
        if host == "youtu.be":
            video_id = parsed.path.strip("/").split("/", 1)[0]
        else:
            from urllib.parse import parse_qs

            video_id = parse_qs(parsed.query).get("v", [""])[0]
        if re.fullmatch(r"[A-Za-z0-9_-]{6,20}", video_id):
            return {"provider": "youtube", "videoId": video_id}
    if host in {"bilibili.com", "www.bilibili.com", "m.bilibili.com", "b23.tv"}:
        match = re.search(r"(?i)(BV[0-9A-Za-z]{10})", source_url)
        if match:
            from urllib.parse import parse_qs

            page = parse_qs(parsed.query).get("p", ["1"])[0]
            page = page if page.isdigit() and int(page) > 0 else "1"
            return {
                "provider": "bilibili",
                "videoId": match.group(1),
                "url": f"https://player.bilibili.com/player.html?bvid={match.group(1)}&p={page}&danmaku=0",
            }
    return None


def load_transcript_groups(knowledge_id: str) -> list[dict[str, Any]]:
    directory = resolve_library_dir(knowledge_id)
    grouped_path = directory / "transcript.grouped.md"
    if grouped_path.exists():
        groups = _parse_grouped_markdown(grouped_path.read_text(encoding="utf-8"))
        if groups:
            return groups
    timeline = _load_json_file(directory / "timeline.json").get("items", [])
    if isinstance(timeline, list) and timeline:
        return [
            {
                "index": item.get("index", index),
                "start": item.get("start", 0),
                "end": item.get("end", 0),
                "title": item.get("title") or f"片段 {index + 1}",
                "text": item.get("summary") or "",
                "keywords": item.get("keywords") or [],
                "sourceLink": item.get("source_link") or "",
            }
            for index, item in enumerate(timeline)
            if isinstance(item, dict)
        ]
    raw_path = directory / "transcript.raw.jsonl"
    if raw_path.exists():
        segments = []
        for line in raw_path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict) and str(item.get("text") or "").strip():
                segments.append(item)
        groups = []
        for offset in range(0, len(segments), 12):
            chunk = segments[offset : offset + 12]
            groups.append(
                {
                    "index": len(groups),
                    "start": float(chunk[0].get("start") or 0),
                    "end": float(chunk[-1].get("end") or chunk[-1].get("start") or 0),
                    "title": f"字幕片段 {len(groups) + 1}",
                    "text": " ".join(str(item.get("text") or "").strip() for item in chunk),
                    "keywords": [],
                    "sourceLink": "",
                }
            )
        return groups
    return []


def chat_with_knowledge(payload: dict[str, Any]) -> dict[str, Any]:
    knowledge_id = str(payload.get("knowledge_id") or "").strip()
    if not knowledge_id:
        raise ValueError("knowledge_id 不能为空。")
    knowledge = load_knowledge_package(knowledge_id)
    groups = load_transcript_groups(knowledge_id)
    client_history = payload.get("history") or []
    if not isinstance(client_history, list):
        raise ValueError("history 必须是数组。")
    question = str(payload.get("question") or "")
    requested_provider = str(payload.get("provider") or "auto")
    registry = ProviderRegistry()
    visual_terms = ("画面", "截图", "界面", "按钮", "图表", "图像", "视觉")
    visual_question = any(term in question for term in visual_terms)
    provider = registry.resolve(
        requested_provider,
        question,
        str(payload.get("model") or "") or None,
    )
    store = ChatStore(resolve_library_dir)
    stored_history = store.load(knowledge_id).get("messages", [])
    result = answer_question(
        question=question,
        groups=groups,
        analysis=knowledge.get("analysis") if isinstance(knowledge.get("analysis"), dict) else {},
        source=knowledge.get("source") if isinstance(knowledge.get("source"), dict) else {},
        history=stored_history if stored_history else client_history,
        provider=provider,
        knowledge_id=knowledge_id,
    )
    if visual_question:
        result["warning"] = "当前聊天请求未附带关键帧，本次仅基于字幕和已有文本分析回答。"
    new_messages = [] if stored_history and stored_history[-1].get("role") == "user" and stored_history[-1].get("content") == question else [{"role": "user", "content": question}]
    new_messages.append(
        {
            "role": "assistant",
            "content": result["answer"],
            "citations": result["citations"],
            "provider": result["provider"],
            "model": result["model"],
            "warning": result.get("warning", ""),
        }
    )
    store.append(knowledge_id, new_messages)
    return result


def resolve_library_dir(knowledge_id: str) -> Path:
    decoded = unquote(knowledge_id).strip()
    if not decoded or decoded in {".", ".."} or "/" in decoded or "\\" in decoded:
        raise ValueError("知识包 ID 不合法。")
    candidate = (OUTPUT_ROOT / decoded).resolve()
    if candidate.parent != OUTPUT_ROOT.resolve() or not _is_knowledge_package(candidate):
        raise FileNotFoundError(decoded)
    return candidate


def delete_knowledge_packages(knowledge_ids: list[str]) -> list[str]:
    if not isinstance(knowledge_ids, list) or not knowledge_ids:
        raise ValueError("请至少选择一条知识记录。")
    if len(knowledge_ids) > 100:
        raise ValueError("单次最多删除 100 条知识记录。")

    normalized_ids: list[str] = []
    targets: list[Path] = []
    seen: set[str] = set()
    for value in knowledge_ids:
        if not isinstance(value, str):
            raise ValueError("知识包 ID 必须是字符串。")
        knowledge_id = unquote(value).strip()
        if knowledge_id in seen:
            continue
        directory = resolve_library_dir(knowledge_id)
        manifest = _load_json_file(directory / "manifest.json")
        if str(manifest.get("status") or "") in {"created", "queued", "running", "processing"}:
            raise ValueError(f"知识记录“{knowledge_id}”仍在处理中，不能删除。")
        seen.add(knowledge_id)
        normalized_ids.append(knowledge_id)
        targets.append(directory)

    # Resolve and validate every target before removing the first directory so
    # malformed IDs cannot cause a partially applied batch deletion.
    deleted: list[str] = []
    for knowledge_id, directory in zip(normalized_ids, targets, strict=True):
        try:
            _remove_knowledge_directory(directory)
        except OSError as exc:
            error = _classify_delete_error(directory, exc, deleted)
            LOGGER.error(
                "knowledge_delete_failed code=%s exception=%s winerror=%s target=%s",
                error.code,
                type(exc).__name__,
                getattr(exc, "winerror", None),
                directory,
            )
            raise error from exc
        deleted.append(knowledge_id)
    return normalized_ids


def _remove_knowledge_directory(directory: Path) -> None:
    output_root = OUTPUT_ROOT.resolve()
    target = directory.resolve()
    try:
        relative = target.relative_to(output_root)
    except ValueError as exc:
        raise ValueError("知识包路径超出允许的输出目录。") from exc
    if len(relative.parts) != 1 or target == output_root:
        raise ValueError("知识包路径不符合安全删除规则。")
    if not target.exists():
        raise FileNotFoundError(target)
    if not target.is_dir():
        raise ValueError("知识包目标不是目录。")
    shutil.rmtree(target, onexc=_retry_readonly_delete)


def _retry_readonly_delete(function: Any, path: str, exc: BaseException) -> None:
    if not isinstance(exc, PermissionError):
        raise exc
    target = Path(path)
    try:
        target.chmod(target.stat().st_mode | stat.S_IWRITE | stat.S_IREAD)
        function(path)
    except OSError:
        raise exc


def _classify_delete_error(target: Path, exc: OSError, deleted: list[str]) -> KnowledgeDeletionError:
    winerror = getattr(exc, "winerror", None)
    if winerror in {32, 33}:
        return KnowledgeDeletionError(
            "knowledge_package_locked",
            "知识包文件正在被播放器、编辑器、同步软件或其他进程占用。请关闭相关程序后重试。",
            target,
            exc,
            deleted,
        )
    if isinstance(exc, PermissionError) or winerror == 5:
        return KnowledgeDeletionError(
            "knowledge_package_access_denied",
            "无法删除知识包。请检查输出目录 ACL、只读属性、同步软件保护，以及 Web 服务的运行权限。",
            target,
            exc,
            deleted,
        )
    return KnowledgeDeletionError(
        "knowledge_package_delete_io_error",
        "删除知识包时发生文件系统错误，请检查磁盘和同步软件状态后重试。",
        target,
        exc,
        deleted,
    )


def resolve_library_file(knowledge_id: str, relative_name: str) -> Path:
    directory = resolve_library_dir(knowledge_id)
    decoded = unquote(relative_name).replace("\\", "/").strip("/")
    parts = Path(decoded).parts
    if not decoded or ".." in parts:
        raise ValueError("文件路径不合法。")
    if len(parts) == 1 and parts[0] not in LIBRARY_FILES:
        raise ValueError("不允许访问该文件。")
    if len(parts) == 2 and parts[0] == "frames":
        if Path(parts[1]).suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise ValueError("不允许访问该关键帧文件。")
    elif len(parts) != 1:
        raise ValueError("不允许访问该文件。")
    candidate = (directory / Path(*parts)).resolve()
    try:
        candidate.relative_to(directory)
    except ValueError as exc:
        raise ValueError("文件路径越界。") from exc
    if not candidate.is_file():
        raise FileNotFoundError(decoded)
    return candidate


def _is_knowledge_package(path: Path) -> bool:
    return path.is_dir() and (path / "metadata.json").is_file() and any((path / name).exists() for name in ("manifest.json", "index.md", "transcript.md"))


def _load_json_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _timeline_count(directory: Path) -> int:
    items = _load_json_file(directory / "timeline.json").get("items", [])
    return len(items) if isinstance(items, list) else 0


def _parse_grouped_markdown(text: str) -> list[dict[str, Any]]:
    groups = []
    pattern = re.compile(r"^##\s+(?:\d+\.\s*)?(?P<title>.+?)\n+\*\*时间：(?P<start>[\d:]+)\s+-\s+(?P<end>[\d:]+)\*\*\n+(?P<text>.*?)(?=\n##\s+|\Z)", re.M | re.S)
    for index, match in enumerate(pattern.finditer(text)):
        groups.append({
            "index": index,
            "start": _timestamp_seconds(match.group("start")),
            "end": _timestamp_seconds(match.group("end")),
            "title": match.group("title").strip(),
            "text": match.group("text").strip(),
            "keywords": [],
            "sourceLink": "",
        })
    return groups


def _timestamp_seconds(value: str) -> int:
    parts = [int(part) for part in value.split(":")]
    return sum(part * (60 ** index) for index, part in enumerate(reversed(parts)))


def resolve_media_path(knowledge_id: str) -> Path:
    directory = resolve_library_dir(knowledge_id)
    metadata = _load_json_file(directory / "metadata.json")
    manifest = _load_json_file(directory / "manifest.json")
    source = manifest.get("source") if isinstance(manifest.get("source"), dict) else metadata
    raw_path = str(source.get("local_path") or metadata.get("source_path") or "")
    path = Path(raw_path).resolve() if raw_path else Path()
    if not raw_path or not path.is_file() or path.suffix.lower() not in MEDIA_EXTENSIONS:
        raise FileNotFoundError("media")
    return path


class VideoSummaryHandler(BaseHTTPRequestHandler):
    server_version = f"VideoSummaryWeb/{__version__}"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/knowledge/") and parsed.path.endswith("/export/preview"):
            knowledge_id = unquote(parsed.path[len("/api/knowledge/") : -len("/export/preview")].strip("/"))
            try:
                selection = selection_for_request(knowledge_id, {"preset": "full", "destination": "preview"})
                markdown, filename = render_directory_export(resolve_library_dir(knowledge_id), selection)
                self._send_json({"knowledge_id": knowledge_id, "filename": filename, "markdown": markdown, "included_sections": selection.normalized_sections()})
            except (ValueError, UserFacingError) as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except FileNotFoundError:
                self._send_json({"error": "知识包不存在。"}, HTTPStatus.NOT_FOUND)
        elif parsed.path == "/":
            self._send_path(WEB_UI_ROOT / "index.html")
        elif parsed.path.startswith("/static/"):
            self._send_static(parsed.path[len("/static/") :])
        elif parsed.path == "/api/library":
            self._send_json({"items": list_library_items()})
        elif parsed.path == "/api/runtime":
            self._send_json(runtime_status_payload())
        elif parsed.path == "/api/providers":
            self._send_json({"providers": ProviderRegistry().statuses()})
        elif parsed.path.startswith("/api/library/"):
            self._handle_library_get(parsed.path)
        elif parsed.path == "/api/jobs":
            with JOBS_LOCK:
                jobs = [job_to_dict(job) for job in sorted(JOBS.values(), key=lambda item: item.created_at, reverse=True)]
            self._send_json({"jobs": jobs})
        elif parsed.path.startswith("/api/jobs/") or parsed.path.startswith("/api/tasks/"):
            job_id = parsed.path.rsplit("/", 1)[-1]
            with JOBS_LOCK:
                job = JOBS.get(job_id)
            if not job:
                self._send_json({"error": "任务不存在。"}, HTTPStatus.NOT_FOUND)
                return
            self._send_json({"job": job_to_dict(job)})
        elif parsed.path.startswith("/output/"):
            self._send_output_file(parsed.path)
        else:
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/knowledge/") and parsed.path.endswith("/export"):
            knowledge_id = unquote(parsed.path[len("/api/knowledge/") : -len("/export")].strip("/"))
            try:
                payload = self._read_json_body()
                selection = selection_for_request(knowledge_id, payload)
                directory = resolve_library_dir(knowledge_id)
                if selection.destination in {"vault", "obsidian-open"}:
                    config = load_config(PROJECT_ROOT / "config.example.json")
                    result = export_directory_to_vault(directory, selection, vault_path=config.obsidian_vault_path, vault_name=config.obsidian_vault_name, subdir=config.obsidian_export_subdir)
                    self._send_json(result)
                else:
                    markdown, filename = render_directory_export(directory, selection)
                    if selection.destination == "download":
                        self._send_markdown(markdown, filename)
                    else:
                        self._send_json({"knowledge_id": knowledge_id, "filename": filename, "markdown": markdown, "included_sections": selection.normalized_sections()})
            except (ValueError, UserFacingError) as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except FileNotFoundError:
                self._send_json({"error": "知识包不存在。"}, HTTPStatus.NOT_FOUND)
            except OSError:
                self._send_json({"error": "导出写入失败，请检查本地配置和目录权限。"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if parsed.path.startswith("/api/library/") and parsed.path.endswith("/analysis/retry"):
            knowledge_id = unquote(
                parsed.path[len("/api/library/") : -len("/analysis/retry")].strip("/")
            )
            try:
                directory = resolve_library_dir(knowledge_id)
                config = load_config(PROJECT_ROOT / "config.example.json")
                reanalyze_knowledge_package(directory, config)
                self._send_json({"knowledge": load_knowledge_package(knowledge_id)})
            except ValueError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except FileNotFoundError:
                self._send_json({"error": "知识包不存在。"}, HTTPStatus.NOT_FOUND)
            except UserFacingError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
            except OSError:
                self._send_json({"error": "重新分析结果写入失败，请检查输出目录。"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if parsed.path.startswith("/api/library/") and parsed.path.endswith("/chat"):
            try:
                knowledge_id = unquote(parsed.path[len("/api/library/") : -len("/chat")].strip("/"))
                payload = self._read_json_body()
                messages = payload.get("messages") or []
                if not isinstance(messages, list):
                    raise ValueError("messages 必须是数组。")
                self._send_json({"chat": ChatStore(resolve_library_dir).replace(knowledge_id, messages)})
            except ValueError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except FileNotFoundError:
                self._send_json({"error": "知识包不存在。"}, HTTPStatus.NOT_FOUND)
            return
        if parsed.path == "/api/chat":
            try:
                self._send_json(chat_with_knowledge(self._read_json_body()))
            except ValueError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except FileNotFoundError:
                self._send_json({"error": "知识包不存在。"}, HTTPStatus.NOT_FOUND)
            except UserFacingError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
            except Exception:
                self._send_json({"error": "上下文对话请求失败。"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if parsed.path.endswith("/capture-frame") and parsed.path.startswith("/api/library/"):
            self._send_json({"error": "服务端关键帧保存接口尚未接入"}, HTTPStatus.NOT_IMPLEMENTED)
            return
        if parsed.path not in {"/api/jobs", "/api/process"}:
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            job = start_job(payload)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        except Exception as exc:
            self._send_json({"error": f"创建任务失败：{exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        self._send_json({"job": job_to_dict(job)}, HTTPStatus.CREATED)

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        if not (parsed.path.startswith("/api/library/") and parsed.path.endswith("/notes")):
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        knowledge_id = unquote(parsed.path[len("/api/library/") : -len("/notes")].strip("/"))
        try:
            payload = self._read_json_body()
            if "content" not in payload:
                raise ValueError("content 不能为空。")
            expected_revision = payload.get("revision") if "revision" in payload else None
            note = NoteStore(resolve_library_dir).save(
                knowledge_id,
                payload["content"],
                str(expected_revision) if expected_revision is not None else None,
            )
            directory = resolve_library_dir(knowledge_id)
            export: dict[str, str] = {}
            warning = ""
            try:
                export_path = refresh_compatible_export(directory)
                encoded_id = quote(knowledge_id, safe="")
                export = {
                    "name": export_path.name,
                    "url": f"/api/library/{encoded_id}/file/{quote(export_path.name, safe='')}",
                }
            except FileNotFoundError:
                warning = "笔记已保存，但知识包缺少 index.md，未刷新兼容导出。"
            self._send_json({"note": note, "export": export, "warning": warning})
        except NoteConflictError as exc:
            self._send_json({"error": str(exc), "note": exc.current}, HTTPStatus.CONFLICT)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except FileNotFoundError:
            self._send_json({"error": "知识包不存在。"}, HTTPStatus.NOT_FOUND)
        except OSError:
            self._send_json({"error": "笔记保存失败，请检查输出目录是否可写。"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/library":
            try:
                payload = self._read_json_body()
                knowledge_ids = payload.get("knowledge_ids")
                if not isinstance(knowledge_ids, list):
                    raise ValueError("knowledge_ids 必须是数组。")
                deleted = delete_knowledge_packages(knowledge_ids)
                self._send_json({"deleted": deleted, "count": len(deleted)})
            except ValueError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except FileNotFoundError:
                self._send_json({"error": "选择的知识记录不存在或已被删除。"}, HTTPStatus.NOT_FOUND)
            except KnowledgeDeletionError as exc:
                status = HTTPStatus.LOCKED if exc.code == "knowledge_package_locked" else HTTPStatus.FORBIDDEN if exc.code == "knowledge_package_access_denied" else HTTPStatus.INTERNAL_SERVER_ERROR
                self._send_json(
                    {
                        "error": str(exc),
                        "code": exc.code,
                        "deleted": exc.deleted,
                        "retryable": exc.code in {"knowledge_package_locked", "knowledge_package_access_denied"},
                    },
                    status,
                )
            return
        if parsed.path.startswith("/api/library/") and parsed.path.endswith("/chat"):
            try:
                knowledge_id = unquote(parsed.path[len("/api/library/") : -len("/chat")].strip("/"))
                ChatStore(resolve_library_dir).clear(knowledge_id)
                self._send_json({"knowledge_id": knowledge_id, "cleared": True})
            except ValueError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except FileNotFoundError:
                self._send_json({"error": "知识包不存在。"}, HTTPStatus.NOT_FOUND)
            return
        self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[web] {self.address_string()} - {fmt % args}")

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        if not isinstance(payload, dict):
            raise ValueError("请求体必须是 JSON 对象。")
        return payload

    def _send_html(self, html: str) -> None:
        data = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _handle_library_get(self, request_path: str) -> None:
        relative = request_path[len("/api/library/") :]
        parts = relative.split("/")
        knowledge_id = unquote(parts[0]) if parts else ""
        try:
            if len(parts) == 1:
                self._send_json({"knowledge": load_knowledge_package(knowledge_id)})
                return
            action = parts[1]
            if action == "transcript" and len(parts) == 2:
                self._send_json({"groups": load_transcript_groups(knowledge_id)})
                return
            if action == "inspect" and len(parts) == 2:
                self._send_json({"inspection": inspect_knowledge_package(resolve_library_dir(knowledge_id)).to_dict()})
                return
            if action == "chat" and len(parts) == 2:
                self._send_json({"chat": ChatStore(resolve_library_dir).load(knowledge_id)})
                return
            if action == "notes" and len(parts) == 2:
                self._send_json({"note": NoteStore(resolve_library_dir).load(knowledge_id)})
                return
            if action == "media" and len(parts) == 2:
                self._send_path(resolve_media_path(knowledge_id), allow_range=True)
                return
            if action == "file" and len(parts) >= 3:
                self._send_path(resolve_library_file(knowledge_id, "/".join(parts[2:])))
                return
        except ValueError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        except FileNotFoundError:
            self._send_json({"error": "知识包或文件不存在。"}, HTTPStatus.NOT_FOUND)
            return
        self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def _send_static(self, relative_name: str) -> None:
        decoded = unquote(relative_name).replace("\\", "/").strip("/")
        fingerprinted = re.fullmatch(r"app\.workspace-\d+\.(js|css)", decoded)
        if fingerprinted:
            decoded = f"app.{fingerprinted.group(1)}"
        if not decoded or ".." in Path(decoded).parts or "/" in decoded:
            self._send_json({"error": "静态资源路径不合法。"}, HTTPStatus.BAD_REQUEST)
            return
        path = (WEB_UI_ROOT / decoded).resolve()
        if path.parent != WEB_UI_ROOT.resolve() or not path.is_file():
            self._send_json({"error": "静态资源不存在。"}, HTTPStatus.NOT_FOUND)
            return
        self._send_path(path)

    def _send_path(self, path: Path, allow_range: bool = False) -> None:
        try:
            size = path.stat().st_size
        except OSError:
            self._send_json({"error": "文件不存在。"}, HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if path.suffix.lower() in {".md", ".jsonl"}:
            content_type = "text/plain; charset=utf-8"
        elif path.suffix.lower() == ".json":
            content_type = "application/json; charset=utf-8"
        start, end = 0, max(0, size - 1)
        status = HTTPStatus.OK
        range_header = self.headers.get("Range", "") if allow_range else ""
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header)
        if match and size:
            start = int(match.group(1) or 0)
            end = min(int(match.group(2) or end), end)
            if start > end:
                self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                return
            status = HTTPStatus.PARTIAL_CONTENT
        length = end - start + 1 if size else 0
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("X-Content-Type-Options", "nosniff")
        if path.parent == WEB_UI_ROOT.resolve():
            self.send_header("Cache-Control", "no-cache")
        if allow_range:
            self.send_header("Accept-Ranges", "bytes")
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if not length:
            return
        with path.open("rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining:
                chunk = handle.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_markdown(self, markdown: str, filename: str) -> None:
        data = markdown.encode("utf-8")
        ascii_name = re.sub(r"[^A-Za-z0-9._-]", "_", filename) or "video-note.md"
        disposition = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename, safe='')}"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/markdown; charset=utf-8")
        self.send_header("Content-Disposition", disposition)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_output_file(self, request_path: str) -> None:
        relative = unquote(request_path.lstrip("/"))
        path = (PROJECT_ROOT / relative).resolve()
        output_root = OUTPUT_ROOT.resolve()
        try:
            path.relative_to(output_root)
        except ValueError:
            self._send_json({"error": "文件不存在。"}, HTTPStatus.NOT_FOUND)
            return
        if not path.is_file():
            self._send_json({"error": "文件不存在。"}, HTTPStatus.NOT_FOUND)
            return
        self._send_path(path)


INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Video Summary Skill</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f8;
      --panel: #ffffff;
      --line: #d9dee3;
      --text: #18212b;
      --muted: #647181;
      --accent: #0f766e;
      --accent-dark: #0b5f59;
      --danger: #b42318;
      --warn: #9a5b00;
      --ok: #1f7a3a;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    header {
      height: 64px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 24px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    h1 { font-size: 19px; margin: 0; font-weight: 650; }
    main {
      display: grid;
      grid-template-columns: minmax(320px, 420px) minmax(0, 1fr);
      gap: 18px;
      padding: 18px;
      max-width: 1320px;
      margin: 0 auto;
    }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    .panel-title {
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      font-weight: 650;
    }
    form, .jobs, .detail { padding: 16px; }
    label { display: block; margin: 0 0 6px; font-size: 13px; color: var(--muted); }
    input[type="text"], select {
      width: 100%;
      height: 38px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0 10px;
      background: #fff;
      color: var(--text);
      font: inherit;
    }
    .field { margin-bottom: 14px; }
    .segmented {
      display: grid;
      grid-template-columns: 1fr 1fr;
      border: 1px solid var(--line);
      border-radius: 6px;
      overflow: hidden;
    }
    .segmented button {
      border: 0;
      height: 36px;
      background: #fff;
      cursor: pointer;
      font: inherit;
    }
    .segmented button.active { background: #dff4ef; color: var(--accent-dark); font-weight: 650; }
    .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .checks { display: grid; gap: 9px; margin: 12px 0 16px; }
    .checks label { display: flex; align-items: center; gap: 8px; color: var(--text); margin: 0; }
    .primary {
      width: 100%;
      height: 42px;
      border: 0;
      border-radius: 6px;
      background: var(--accent);
      color: white;
      font: inherit;
      font-weight: 650;
      cursor: pointer;
    }
    .primary:hover { background: var(--accent-dark); }
    .hint { color: var(--muted); font-size: 12px; line-height: 1.6; margin-top: 10px; }
    .job {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      margin-bottom: 10px;
      cursor: pointer;
      background: #fff;
    }
    .job.active { outline: 2px solid #99d6cc; }
    .job-top { display: flex; justify-content: space-between; gap: 10px; align-items: center; }
    .job-id { font-family: Consolas, monospace; font-size: 13px; }
    .status { font-size: 12px; padding: 3px 8px; border-radius: 999px; background: #eef1f4; color: var(--muted); }
    .status.running { background: #fff1cf; color: var(--warn); }
    .status.success { background: #def7e7; color: var(--ok); }
    .status.failed { background: #fde2df; color: var(--danger); }
    .command, pre {
      white-space: pre-wrap;
      word-break: break-word;
      font-family: Consolas, "Courier New", monospace;
      font-size: 12px;
      line-height: 1.5;
    }
    .command { color: var(--muted); margin-top: 8px; }
    pre {
      min-height: 220px;
      max-height: 430px;
      overflow: auto;
      padding: 12px;
      border-radius: 6px;
      border: 1px solid var(--line);
      background: #111820;
      color: #e7eef5;
    }
    .files { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0; }
    .files a {
      display: inline-flex;
      align-items: center;
      min-height: 30px;
      padding: 0 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      color: var(--accent-dark);
      text-decoration: none;
      background: #fff;
    }
    .empty { color: var(--muted); padding: 20px; text-align: center; }
    @media (max-width: 860px) {
      header { padding: 0 14px; }
      main { grid-template-columns: 1fr; padding: 12px; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Video Summary Skill</h1>
    <span id="serverState" class="status">5188</span>
  </header>
  <main>
    <section>
      <div class="panel-title">创建解析任务</div>
      <form id="jobForm">
        <div class="field">
          <label>输入类型</label>
          <div class="segmented">
            <button type="button" data-source-type="url" class="active">公开视频链接</button>
            <button type="button" data-source-type="file">本地文件路径</button>
          </div>
        </div>
        <div class="field">
          <label id="sourceLabel">视频链接</label>
          <input id="source" type="text" placeholder="https://www.bilibili.com/video/BV..." autocomplete="off">
        </div>
        <div class="grid-2">
          <div class="field">
            <label>AI 分析</label>
            <select id="backend" disabled>
              <option value="deepseek">DeepSeek</option>
            </select>
          </div>
          <div class="field">
            <label>分析模式</label>
            <select id="mode">
              <option value="summary">summary</option>
              <option value="tutorial">tutorial</option>
              <option value="viral">viral</option>
              <option value="close-reading">close-reading</option>
            </select>
          </div>
        </div>
        <div class="grid-2">
          <div class="field">
            <label>字幕语言</label>
            <select id="lang">
              <option value="">默认 zh</option>
              <option value="zh">zh</option>
              <option value="en">en</option>
            </select>
          </div>
          <div class="field">
            <label>导出</label>
            <select id="exportMode">
              <option value="none">none</option>
              <option value="obsidian">obsidian</option>
            </select>
          </div>
        </div>
        <div class="checks">
          <label><input id="noFrames" type="checkbox"> 跳过关键帧</label>
          <label><input id="noSummary" type="checkbox"> 只生成 transcript，不调用 LLM</label>
        </div>
        <button class="primary" type="submit">启动任务</button>
        <div class="hint">任务会在后台调用现有 CLI。输出文件保存在项目的 output 目录。</div>
      </form>
    </section>
    <section>
      <div class="panel-title">任务状态</div>
      <div class="jobs" id="jobs"></div>
    </section>
    <section style="grid-column: 1 / -1;">
      <div class="panel-title">当前任务详情</div>
      <div class="detail" id="detail"><div class="empty">还没有任务。</div></div>
    </section>
  </main>
  <script>
    let sourceType = "url";
    let selectedJobId = "";

    const $ = (id) => document.getElementById(id);
    const statusClass = (status) => "status " + status;

    document.querySelectorAll("[data-source-type]").forEach((button) => {
      button.addEventListener("click", () => {
        sourceType = button.dataset.sourceType;
        document.querySelectorAll("[data-source-type]").forEach((item) => item.classList.remove("active"));
        button.classList.add("active");
        $("sourceLabel").textContent = sourceType === "url" ? "视频链接" : "本地文件路径";
        $("source").placeholder = sourceType === "url"
          ? "https://www.bilibili.com/video/BV..."
          : "E:\\Downloads_E\\video.mp4";
      });
    });

    $("jobForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const payload = {
        sourceType,
        source: $("source").value.trim(),
        backend: $("backend").value,
        mode: $("mode").value,
        lang: $("lang").value,
        export: $("exportMode").value,
        noFrames: $("noFrames").checked,
        noSummary: $("noSummary").checked
      };
      const response = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (!response.ok) {
        alert(data.error || "创建任务失败");
        return;
      }
      selectedJobId = data.job.id;
      await refresh();
    });

    async function refresh() {
      const response = await fetch("/api/jobs");
      const data = await response.json();
      renderJobs(data.jobs || []);
      const selected = (data.jobs || []).find((job) => job.id === selectedJobId) || (data.jobs || [])[0];
      if (selected) {
        selectedJobId = selected.id;
        renderDetail(selected);
      }
    }

    function renderJobs(jobs) {
      const root = $("jobs");
      if (!jobs.length) {
        root.innerHTML = '<div class="empty">暂无任务。</div>';
        return;
      }
      root.innerHTML = jobs.map((job) => `
        <div class="job ${job.id === selectedJobId ? "active" : ""}" data-job-id="${job.id}">
          <div class="job-top">
            <span class="job-id">${job.id}</span>
            <span class="${statusClass(job.status)}">${job.status}</span>
          </div>
          <div class="command">${escapeHtml(job.command.join(" "))}</div>
        </div>
      `).join("");
      root.querySelectorAll("[data-job-id]").forEach((item) => {
        item.addEventListener("click", () => {
          selectedJobId = item.dataset.jobId;
          refresh();
        });
      });
    }

    function renderDetail(job) {
      const files = job.outputFiles.length
        ? `<div class="files">${job.outputFiles.map((file) => `<a href="${file.url}" target="_blank">${file.name}</a>`).join("")}</div>`
        : '<div class="hint">任务完成后会显示输出文件。</div>';
      $("detail").innerHTML = `
        <div class="job-top">
          <div>
            <div class="job-id">${job.id}</div>
            <div class="command">${escapeHtml(job.command.join(" "))}</div>
          </div>
          <span class="${statusClass(job.status)}">${job.status}</span>
        </div>
        <p class="hint">输出目录：${job.outputDir ? escapeHtml(job.outputDir) : "尚未生成"}</p>
        ${files}
        <pre>${escapeHtml((job.logs || []).join("\n") || "等待日志...")}</pre>
      `;
    }

    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, (ch) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;"
      }[ch]));
    }

    refresh();
    setInterval(refresh, 1500);
  </script>
</body>
</html>
"""


class VideoSummaryServer(ThreadingHTTPServer):
    # HTTPServer enables SO_REUSEADDR by default. On Windows that can let
    # several long-running UI processes share port 5188 and receive requests
    # unpredictably, including processes that still have older code loaded.
    allow_reuse_address = False
    allow_reuse_port = False


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the video-summary-skill web UI.")
    parser.add_argument("--version", action="version", version=f"video-summary-skill {__version__}")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5188)
    parser.add_argument("--open", action="store_true", help="Open the browser after starting.")
    args = parser.parse_args()

    server = VideoSummaryServer((args.host, args.port), VideoSummaryHandler)
    url = f"http://{args.host}:{args.port}"
    print(f"Video Summary Web UI: {url}")
    print(f"Python executable: {sys.executable}")
    print(f"Working directory: {PROJECT_ROOT}")
    print("Subprocess runner: uses this Web UI process sys.executable")
    runtime = runtime_status_payload()
    for tool in runtime["tools"]:
        detail = f"{tool['path']} ({tool['source']})" if tool["available"] else "未配置或未发现"
        print(f"{tool['name']}: {detail}")
    for provider in runtime["providers"]:
        configured = "configured" if provider["configured"] else "not configured"
        print(f"Provider: {provider['name']} / {provider['model']} ({configured})")
    warning = _runtime_python_warning()
    if warning:
        print(warning)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping web server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
