from __future__ import annotations

import argparse
import hashlib
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
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

from . import __version__
from .cli_contract import sanitize_message
from .analysis.retry import reanalyze_knowledge_package
from .chat import answer_question, prepare_grounded_request
from .chat_store import ChatStore
from .capabilities import CapabilityRegistry
from .config import load_config, resolve_output_root
from .domain.models import AnalysisResult
from .exporters import export_directory_to_vault, refresh_compatible_export, render_directory_export, selection_for_request
from .job_store import Job, JobStore
from .knowledge_identity import (
    DuplicateDecision,
    DuplicateKind,
    KnowledgeRequestDimensions,
    TaskIdentityRecord,
    build_input_knowledge_identity,
    detect_duplicate,
    normalize_source_url,
    source_urls_equivalent,
)
from .intake_store import IntakeStore
from .page_ingestion import ingest_page_capture
from .bilibili_series import inspect_bilibili_input
from .knowledge_sets import KnowledgeSetStore, knowledge_set_registry_path
from .folder_sets import FolderSetStore, inspect_folder, normalize_local_path, VIDEO_EXTENSIONS as FOLDER_VIDEO_EXTENSIONS
from .clip_store import ClipStore
from .project_groups import ProjectGroupStore, project_registry_path
from .sources.ytdlp_source import is_bilibili_input
from .knowledge_validation import inspect_knowledge_package, meaningful_analysis
from .network import apply_network_proxy_env
from .note_store import NoteConflictError, NoteStore
from .processing_profiles import normalize_processing_profile
from .provider_config import (
    ProviderConfigResolver,
    WebProviderConfigStore,
    sanitize_provider_error,
    test_groq_connection,
    test_provider_connection,
)
from .providers.llm import GeminiProvider, ProviderRegistry
from .runtime_tools import resolve_executable, runtime_tool_statuses
from .utils import UserFacingError, ensure_dir, is_timeout_error, run_command
from .video_chat import GeminiVideoChatRouter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NETWORK_PROXY_STATUS = apply_network_proxy_env()
WEB_CONFIG = load_config(PROJECT_ROOT / "config.example.json")
OUTPUT_ROOT = resolve_output_root(WEB_CONFIG, PROJECT_ROOT)
WEB_UI_ROOT = Path(__file__).resolve().parent / "web_ui"
_configured_state_root = str(os.environ.get("VIEWLEDGE_STATE_ROOT") or "").strip()
LOCAL_STATE_ROOT = (
    Path(_configured_state_root).expanduser().resolve()
    if _configured_state_root
    else PROJECT_ROOT / ".local"
)
LOCAL_STATE_ROOT.mkdir(parents=True, exist_ok=True)
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
    "page.md",
    "page_content.json",
    "export_note.md",
    "user_notes.md",
    "visual_insights.json",
    "visual_insights.md",
    "comments.json",
    "comments.md",
    "comment_insights.json",
    "comment_insights.md",
}
MEDIA_EXTENSIONS = set(FOLDER_VIDEO_EXTENSIONS) | {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus"}
TS_MEDIA_EXTENSIONS = {".ts", ".mts", ".m2ts"}

JOB_STORE = JobStore(LOCAL_STATE_ROOT / "web_jobs.json")
JOBS: dict[str, Job] = {job.id: job for job in JOB_STORE.load_jobs()}
JOBS_LOCK = threading.RLock()
JOB_ENV_OVERRIDES: dict[str, dict[str, str]] = {}
JOB_ASR_PERSIST_STATE: dict[str, dict[str, Any]] = {}
JOB_SCHEDULER_CONDITION = threading.Condition(JOBS_LOCK)
ACTIVE_PIPELINES = 0
MAX_ACTIVE_PIPELINES = 2
INTAKE_STORE = IntakeStore(LOCAL_STATE_ROOT / "intakes.json")
KNOWLEDGE_SET_STORE = KnowledgeSetStore(
    knowledge_set_registry_path(OUTPUT_ROOT),
    legacy_paths=(
        PROJECT_ROOT / ".local" / "knowledge_sets.json",
        LOCAL_STATE_ROOT / "knowledge_sets.json",
    ),
)
FOLDER_SET_STORE = FolderSetStore(LOCAL_STATE_ROOT / "folder_sets.json")
CLIP_STORE = ClipStore(LOCAL_STATE_ROOT / "clips.json")
PROJECT_GROUP_STORE = ProjectGroupStore(project_registry_path(OUTPUT_ROOT))
LOGGER = logging.getLogger(__name__)
WEB_PROVIDER_CONFIG = WebProviderConfigStore()
CAPABILITY_CACHE: dict[str, Any] = {}
CAPABILITY_LOCK = threading.RLock()
SEARCH_DOCUMENT_CACHE: dict[str, dict[str, Any]] = {}
SEARCH_DOCUMENT_CACHE_LOCK = threading.RLock()
MEDIA_PREVIEW_ROOT = LOCAL_STATE_ROOT / "media_previews"
MEDIA_PREVIEW_LOCK = threading.RLock()
SEARCH_FILE_LIMIT = 2_000_000
PRODUCT_SENSITIVE_KEYS = {
    "analysis_model",
    "analysis_provider",
    "asr_model",
    "asr_provider",
    "compute_type",
    "device",
    "ffmpeg_path",
    "ffprobe_path",
    "llm_model",
    "llm_provider",
    "local_path",
    "model",
    "model_name",
    "models",
    "output_dir",
    "package_path",
    "provider",
    "source_path",
    "transcript_model",
    "transcript_provider",
}
PRODUCT_PROVIDER_SERVICES = {
    "deepseek": "analysis_text",
    "gemini": "visual_understanding",
    "groq": "cloud_transcription",
}


def _diagnostic_ui_mode() -> bool:
    return os.getenv("VIEWLEDGE_UI_MODE", "").strip().lower() == "diagnostic"


def _diagnostic_flag(name: str) -> bool:
    return _diagnostic_ui_mode() and os.getenv(name, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _safe_process_log(line: str) -> str:
    value = re.sub(
        r"(?i)\b(authorization|cookie|set-cookie|proxy-authorization)"
        r"(\s*[:=]\s*)([^\r\n]+)",
        r"\1\2[REDACTED]",
        str(line),
    )
    value = sanitize_message(value)
    value = re.sub(
        r"(?i)\b(cookie|set-cookie|proxy-authorization)(\s*[:=]\s*)([^\r\n]+)",
        r"\1\2[REDACTED]",
        value,
    )
    return value


def _product_log(line: str) -> str:
    value = _safe_process_log(line)
    for path in (sys.executable, str(PROJECT_ROOT), str(OUTPUT_ROOT)):
        if path:
            value = value.replace(path, "[LOCAL_PATH]")
    return value


def _product_message(value: str) -> str:
    text = _product_log(value)
    replacements = {
        "DeepSeek": "文字分析服务",
        "Gemini": "视觉理解服务",
        "Groq": "云端转写服务",
        "faster-whisper": "本地转写组件",
        "CTranslate2": "本地计算组件",
        "CUDA": "本地 GPU",
        "cuDNN": "GPU 运行组件",
        "cuBLAS": "GPU 运行组件",
        "FFmpeg": "媒体处理组件",
        "ffmpeg": "媒体处理组件",
        "ffprobe": "媒体检测组件",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = re.sub(r"(?i)\b(?:small|turbo|large-v3|whisper-large-v3-turbo)\b", "本地模型", text)
    return text


def _product_capabilities(payload: dict[str, Any]) -> dict[str, Any]:
    raw = payload.get("capabilities") if isinstance(payload.get("capabilities"), dict) else {}

    def aggregate(*names: str) -> tuple[str, bool]:
        items = [raw.get(name) for name in names if isinstance(raw.get(name), dict)]
        available = bool(items) and all(item.get("status") == "available" for item in items)
        if available:
            return "available", True
        config_required = any(item.get("status") == "config_required" for item in items)
        return ("config_required" if config_required else "unavailable"), False

    definitions = {
        "analysis_text": (("deepseek",), "已配置", "未配置"),
        "cloud_transcription": (("groq",), "已配置", "未配置"),
        "visual_understanding": (("gemini",), "已配置", "未配置"),
        "media_processing": (("ffmpeg", "ffprobe"), "可用", "不可用"),
        "local_model": (("local_model",), "可用", "未安装"),
        "local_cpu": (("local_cpu",), "可用", "不可用"),
        "local_gpu": (("local_gpu",), "可用", "不可用"),
    }
    capabilities: dict[str, Any] = {}
    for name, (sources, available_label, unavailable_label) in definitions.items():
        status, available = aggregate(*sources)
        capabilities[name] = {
            "status": status,
            "displayMessage": available_label if available else unavailable_label,
        }
    return {
        "status": payload.get("status") or "available",
        "updatedAt": payload.get("updatedAt"),
        "capabilities": capabilities,
    }


def capability_payload(*, refresh: bool = False) -> dict[str, Any]:
    global CAPABILITY_CACHE
    with CAPABILITY_LOCK:
        if CAPABILITY_CACHE and not refresh:
            cached = dict(CAPABILITY_CACHE)
            return cached if _diagnostic_ui_mode() else _product_capabilities(cached)
    payload = CapabilityRegistry(
        load_config(PROJECT_ROOT / "config.example.json"),
        project_root=PROJECT_ROOT,
        provider_resolver=ProviderConfigResolver(WEB_PROVIDER_CONFIG),
    ).inspect()
    with CAPABILITY_LOCK:
        CAPABILITY_CACHE = payload
    return dict(payload) if _diagnostic_ui_mode() else _product_capabilities(payload)


def data_directory_status(*, create: bool = True) -> dict[str, Any]:
    try:
        if create:
            OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        if not OUTPUT_ROOT.is_dir():
            raise OSError("not_a_directory")
        probe = OUTPUT_ROOT / f".viewledge-write-test-{uuid.uuid4().hex}.tmp"
        try:
            probe.write_text("ok", encoding="utf-8")
        finally:
            probe.unlink(missing_ok=True)
    except OSError:
        result: dict[str, Any] = {"available": False, "status": "unwritable", "displayMessage": "不可写"}
    else:
        result = {"available": True, "status": "available", "displayMessage": "可用"}
    if _diagnostic_flag("SHOW_TECH_DETAILS"):
        result["path"] = str(OUTPUT_ROOT)
    return result


def ensure_data_directory_writable() -> None:
    if not data_directory_status()["available"]:
        raise UserFacingError("数据目录不可写，请在设置中选择当前用户可写的目录。")


class KnowledgeDeletionError(RuntimeError):
    def __init__(self, code: str, message: str, target: Path, cause: OSError, deleted: list[str] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.target = target
        self.cause = cause
        self.deleted = list(deleted or [])


class DuplicateTaskError(ValueError):
    def __init__(self, decision: DuplicateDecision, message: str = "duplicate active task") -> None:
        super().__init__(message)
        self.decision = decision


def _payload_source(payload: dict[str, Any]) -> tuple[str, str]:
    source_type = str(payload.get("sourceType") or "url")
    source = _clean_source_value(str(payload.get("source") or ""))
    if source_type not in {"url", "file"}:
        raise ValueError("sourceType must be url or file.")
    if not source:
        raise ValueError("source is required.")
    return source_type, source


def _sample_seconds_from_payload(payload: dict[str, Any]) -> int | None:
    sample_seconds = payload.get("sampleSeconds")
    if sample_seconds in (None, ""):
        return None
    try:
        sample_value = int(sample_seconds)
    except (TypeError, ValueError) as exc:
        raise ValueError("sampleSeconds must be a positive integer.") from exc
    if sample_value <= 0:
        raise ValueError("sampleSeconds must be a positive integer.")
    return sample_value


def _transcript_group_seconds_from_payload(
    payload: dict[str, Any],
    *,
    default: int,
) -> int:
    raw = payload.get("transcriptGroupSeconds", payload.get("transcript_group_seconds"))
    if raw in (None, ""):
        return int(default)
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("transcriptGroupSeconds 必须是整数。") from exc
    if value < 15:
        raise ValueError("transcriptGroupSeconds 不能小于 15。")
    if value > 300:
        raise ValueError("transcriptGroupSeconds 不能大于 300。")
    return value


def _request_dimensions_from_payload(
    payload: dict[str, Any],
    *,
    analysis_requested: bool,
    processing_profile: str,
    asr_route: str,
) -> KnowledgeRequestDimensions:
    return KnowledgeRequestDimensions(
        language=str(payload.get("lang") or WEB_CONFIG.language or ""),
        analysis_profile=str(payload.get("mode") or "summary"),
        processing_profile=processing_profile,
        transcript_only=not analysis_requested,
        comments_enabled=bool(payload.get("comments")),
        sample_seconds=_sample_seconds_from_payload(payload),
        transcript_group_seconds=_transcript_group_seconds_from_payload(
            payload,
            default=WEB_CONFIG.transcript_group_seconds,
        ),
        asr_route=asr_route,
        asr_fallback_enabled=_explicit_true(
            payload.get("asr_fallback_enabled", payload.get("asrFallbackEnabled", True))
        ),
        generate_frames=not bool(payload.get("noFrames")),
    )


def _duplicate_payload(decision: DuplicateDecision) -> dict[str, Any]:
    return {
        "kind": decision.kind.value,
        "matchedTaskId": decision.matched_task_id,
        "matchedKnowledgeId": decision.matched_knowledge_id,
        "allowedActions": list(decision.allowed_actions),
    }


def _duplicate_action_from_payload(payload: dict[str, Any]) -> str:
    return str(payload.get("duplicateAction") or payload.get("duplicate_action") or "").strip().lower()


def _matched_duplicate_job(decision: DuplicateDecision) -> Job | None:
    if not decision.matched_task_id:
        return None
    return JOBS.get(decision.matched_task_id)


def _build_resume_command(cli_task_id: str, python_executable: str | None = None) -> list[str]:
    python_executable = python_executable or sys.executable
    if not cli_task_id:
        raise ValueError("可恢复任务缺少 CLI task_id。")
    return [python_executable, "-m", "src.main", "resume", cli_task_id, "--jsonl"]


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
    processing_profile = normalize_processing_profile(str(payload.get("processingProfile") or "complete"))
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
    command.extend(
        [
            "--backend",
            backend,
            "--mode",
            mode,
            "--processing-profile",
            processing_profile,
        ]
    )
    asr_route = str(payload.get("asr_route") or payload.get("asrRoute") or "cloud")
    if asr_route not in {"cloud", "local_gpu", "local_cpu"}:
        raise ValueError("asr_route 只能是 cloud、local_gpu 或 local_cpu。")
    if "asr_route" in payload or "asrRoute" in payload:
        command.extend(["--asr-route", asr_route])
    fallback_value = payload.get("asr_fallback_enabled", payload.get("asrFallbackEnabled", True))
    if not _explicit_true(fallback_value):
        command.append("--no-asr-fallback")
    if payload.get("noFrames"):
        command.append("--no-frames")
    if payload.get("comments"):
        command.append("--comments")
    if export != "none":
        command.extend(["--export", export])
    analysis_requested, _skip_reason = _analysis_request_from_payload(payload)
    if not analysis_requested:
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
    group_seconds = _transcript_group_seconds_from_payload(
        payload,
        default=WEB_CONFIG.transcript_group_seconds,
    )
    if group_seconds != WEB_CONFIG.transcript_group_seconds or "transcriptGroupSeconds" in payload or "transcript_group_seconds" in payload:
        command.extend(["--transcript-group-seconds", str(group_seconds)])
    command.append("--jsonl")
    return command


def _analysis_request_from_payload(payload: dict[str, Any]) -> tuple[bool, str]:
    transcript_only = any(
        _explicit_true(payload.get(key))
        for key in ("noSummary", "skip_analysis", "transcribe_only", "transcriptOnly")
    )
    if payload.get("analysis_enabled") is not None:
        transcript_only = transcript_only or not _explicit_true(payload.get("analysis_enabled"))
    if payload.get("analysis_requested") is not None:
        transcript_only = transcript_only or not _explicit_true(payload.get("analysis_requested"))
    return (not transcript_only, "user_requested_transcript_only" if transcript_only else "")


def _explicit_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _clean_source_value(value: str) -> str:
    cleaned = value.strip()
    quote_pairs = {('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’")}
    for left, right in quote_pairs:
        if cleaned.startswith(left) and cleaned.endswith(right):
            return cleaned[1:-1].strip()
    return cleaned


def _task_identity_records() -> list[TaskIdentityRecord]:
    return [
        TaskIdentityRecord(
            task_id=job.id,
            knowledge_id=job.knowledge_id,
            request_fingerprint=job.request_fingerprint,
            status=job.status,
        )
        for job in JOBS.values()
        if job.knowledge_id and job.request_fingerprint
    ]


def _job_from_request(
    *,
    command: list[str],
    payload: dict[str, Any],
    analysis_requested: bool,
    analysis_skip_reason: str,
    processing_profile: str,
    asr_route: str,
    identity_schema_version: str,
    knowledge_id: str,
    request_fingerprint: str,
    duplicate: DuplicateDecision,
) -> Job:
    return Job(
        id=uuid.uuid4().hex[:12],
        command=command,
        analysis_profile=str(payload.get("mode") or "summary"),
        processing_profile=processing_profile,
        analysis_requested=analysis_requested,
        analysis_status="pending" if analysis_requested else "skipped",
        analysis_skip_reason=analysis_skip_reason,
        transcript_only=not analysis_requested,
        transcript_route_requested=asr_route,
        identity_schema_version=identity_schema_version,
        knowledge_id=knowledge_id,
        request_fingerprint=request_fingerprint,
        duplicate_kind=duplicate.kind.value,
        duplicate_matched_task_id=duplicate.matched_task_id,
        duplicate_matched_knowledge_id=duplicate.matched_knowledge_id,
        duplicate_allowed_actions=list(duplicate.allowed_actions),
    )


def _reuse_completed_duplicate(
    *,
    payload: dict[str, Any],
    matched_job: Job,
    duplicate: DuplicateDecision,
    analysis_requested: bool,
    analysis_skip_reason: str,
    processing_profile: str,
    asr_route: str,
    identity_schema_version: str,
    knowledge_id: str,
    request_fingerprint: str,
) -> Job:
    if not matched_job.output_dir:
        raise ValueError("已完成任务缺少可复用的知识包路径。")
    now = time.time()
    job = _job_from_request(
        command=[],
        payload=payload,
        analysis_requested=analysis_requested,
        analysis_skip_reason=analysis_skip_reason,
        processing_profile=processing_profile,
        asr_route=asr_route,
        identity_schema_version=identity_schema_version,
        knowledge_id=knowledge_id,
        request_fingerprint=request_fingerprint,
        duplicate=duplicate,
    )
    job.compute_profile = str(
        payload.get("computeProfile")
        or payload.get("compute_profile")
        or WEB_CONFIG.compute_profile
    )
    if job.compute_profile not in {"responsive", "balanced", "performance"}:
        raise ValueError("computeProfile 只能是 responsive、balanced 或 performance。")
    job.status = "success"
    job.returncode = 0
    job.started_at = now
    job.finished_at = now
    job.output_dir = matched_job.output_dir
    job.cli_task_id = matched_job.cli_task_id
    job.analysis_status = matched_job.analysis_status
    job.analysis_provider = matched_job.analysis_provider
    job.analysis_model = matched_job.analysis_model
    job.transcript_status = matched_job.transcript_status
    job.transcript_provider = matched_job.transcript_provider
    job.transcript_model = matched_job.transcript_model
    job.transcript_actual_provider = matched_job.transcript_actual_provider
    job.transcript_actual_device = matched_job.transcript_actual_device
    job.logs.append(f"Reused completed task {matched_job.id}.")
    with JOBS_LOCK:
        JOBS[job.id] = job
        try:
            _persist_job(job, strict=True)
        except OSError:
            JOBS.pop(job.id, None)
            raise
    return job


def start_job(payload: dict[str, Any]) -> Job:
    ensure_data_directory_writable()
    analysis_requested, analysis_skip_reason = _analysis_request_from_payload(payload)
    command = build_cli_command(payload)
    source_type, source = _payload_source(payload)
    processing_profile = normalize_processing_profile(str(payload.get("processingProfile") or "complete"))
    asr_route = str(payload.get("asr_route") or payload.get("asrRoute") or "cloud")
    identity = build_input_knowledge_identity(
        source,
        is_url=source_type == "url",
        dimensions=_request_dimensions_from_payload(
            payload,
            analysis_requested=analysis_requested,
            processing_profile=processing_profile,
            asr_route=asr_route,
        ),
    )
    with JOBS_LOCK:
        duplicate = detect_duplicate(identity, _task_identity_records())
        duplicate_action = _duplicate_action_from_payload(payload)
        matched_job = _matched_duplicate_job(duplicate)
        if duplicate_action and not duplicate.detected:
            raise ValueError("duplicateAction 只能用于已检测到的重复任务。")
        if duplicate_action and duplicate_action not in duplicate.allowed_actions:
            raise ValueError("duplicateAction 不适用于当前重复任务状态。")
        if duplicate.kind is DuplicateKind.ACTIVE_EXACT:
            raise DuplicateTaskError(duplicate)
        if duplicate_action == "reject":
            raise DuplicateTaskError(duplicate, "duplicate task rejected")
        if duplicate_action == "reuse":
            if not matched_job:
                raise ValueError("未找到可复用的重复任务。")
            return _reuse_completed_duplicate(
                payload=payload,
                matched_job=matched_job,
                duplicate=duplicate,
                analysis_requested=analysis_requested,
                analysis_skip_reason=analysis_skip_reason,
                processing_profile=processing_profile,
                asr_route=asr_route,
                identity_schema_version=identity.schema_version,
                knowledge_id=identity.knowledge_id,
                request_fingerprint=identity.request_fingerprint,
            )
        if duplicate_action == "resume":
            if not matched_job:
                raise ValueError("未找到可恢复的重复任务。")
            command = _build_resume_command(matched_job.cli_task_id)
    if analysis_requested and not ProviderConfigResolver(
        WEB_PROVIDER_CONFIG
    ).resolve("deepseek").configured:
        raise ValueError(
            "DeepSeek 尚未配置（config_required）；请配置后运行分析，"
            "或明确选择“仅转写”。"
    )
    env_overrides = ProviderConfigResolver(WEB_PROVIDER_CONFIG).env_overrides()
    job = _job_from_request(
        command=command,
        payload=payload,
        analysis_requested=analysis_requested,
        analysis_skip_reason=analysis_skip_reason,
        processing_profile=processing_profile,
        asr_route=asr_route,
        identity_schema_version=identity.schema_version,
        knowledge_id=identity.knowledge_id,
        request_fingerprint=identity.request_fingerprint,
        duplicate=duplicate,
    )
    with JOBS_LOCK:
        JOBS[job.id] = job
        try:
            _persist_job(job, strict=True)
        except OSError:
            JOBS.pop(job.id, None)
            raise
        if env_overrides:
            JOB_ENV_OVERRIDES[job.id] = env_overrides
        JOB_ENV_OVERRIDES.setdefault(job.id, {})["COMPUTE_PROFILE"] = job.compute_profile
    thread = threading.Thread(target=_run_scheduled_job, args=(job,), daemon=True)
    thread.start()
    return job


def _run_scheduled_job(job: Job) -> None:
    global ACTIVE_PIPELINES
    with JOB_SCHEDULER_CONDITION:
        while True:
            if job.status != "queued":
                return
            queued = sorted(
                (item for item in JOBS.values() if item.status == "queued"),
                key=lambda item: (item.created_at, item.id),
            )
            if (
                ACTIVE_PIPELINES < MAX_ACTIVE_PIPELINES
                and queued
                and queued[0].id == job.id
            ):
                ACTIVE_PIPELINES += 1
                job.queue_reason = ""
                job.active_resource = "pipeline"
                _persist_job(job)
                break
            position = next(
                (index + 1 for index, item in enumerate(queued) if item.id == job.id),
                1,
            )
            job.queue_reason = f"等待处理队列（第 {position} 位）"
            _persist_job(job)
            JOB_SCHEDULER_CONDITION.wait(timeout=0.5)
    try:
        _run_job(job)
    finally:
        with JOB_SCHEDULER_CONDITION:
            ACTIVE_PIPELINES = max(0, ACTIVE_PIPELINES - 1)
            job.active_resource = ""
            JOB_SCHEDULER_CONDITION.notify_all()


def _run_job(job: Job) -> None:
    before = _snapshot_output_dirs()
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    with JOBS_LOCK:
        env.update(JOB_ENV_OVERRIDES.pop(job.id, {}))
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
            creationflags=(0x00004000 if os.name == "nt" and job.compute_profile == "responsive" else 0),
        )
        assert process.stdout is not None
        for line in process.stdout:
            _handle_cli_output_line(job, line.rstrip())
        job.returncode = process.wait()
        if not job.output_dir:
            job.output_dir = _find_new_output_dir(before)
        if not job.knowledge_id and job.output_dir:
            job.knowledge_id = Path(job.output_dir).name
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


def _restore_scheduler_jobs() -> None:
    """Requeue persisted jobs after a clean Web process start."""
    with JOB_SCHEDULER_CONDITION:
        for job in JOBS.values():
            if job.status == "running":
                job.status = "interrupted"
                job.error = "Web 服务重启，任务未自动恢复。"
                job.finished_at = time.time()
                _persist_job(job)
            if job.status == "queued":
                threading.Thread(
                    target=_run_scheduled_job,
                    args=(job,),
                    daemon=True,
                    name=f"job-scheduler-{job.id[-8:]}",
                ).start()


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
        job.knowledge_id = str(payload.get("knowledge_id") or job.knowledge_id)
        job.identity_schema_version = str(payload.get("identity_schema_version") or job.identity_schema_version)
        job.request_fingerprint = str(payload.get("request_fingerprint") or job.request_fingerprint)
        job.analysis_profile = str(payload.get("analysis_profile") or job.analysis_profile)
        job.processing_profile = normalize_processing_profile(
            str(payload.get("processing_profile") or job.processing_profile)
        )
    elif event == "task_completed" and isinstance(payload.get("result"), dict):
        result = payload["result"]
        job.output_dir = str(result.get("output_dir") or "")
        job.knowledge_id = str(result.get("knowledge_id") or "")
        job.identity_schema_version = str(result.get("identity_schema_version") or job.identity_schema_version)
        job.request_fingerprint = str(result.get("request_fingerprint") or job.request_fingerprint)
        job.analysis_profile = str(result.get("analysis_profile") or job.analysis_profile)
        job.processing_profile = normalize_processing_profile(
            str(result.get("processing_profile") or job.processing_profile)
        )
        analysis = result.get("analysis") if isinstance(result.get("analysis"), dict) else {}
        job.analysis_requested = bool(result.get("analysis_requested", job.analysis_requested))
        job.analysis_status = str(result.get("analysis_status") or analysis.get("status") or job.analysis_status)
        job.analysis_skip_reason = str(result.get("analysis_skip_reason") or "")
        job.analysis_provider = str(result.get("analysis_provider") or analysis.get("provider") or "")
        job.analysis_model = str(result.get("analysis_model") or analysis.get("model") or "")
        job.transcript_only = bool(result.get("transcript_only", not job.analysis_requested))
        job.transcript_status = str(result.get("transcript_status") or job.transcript_status)
        job.transcript_provider = str(result.get("transcript_provider") or "")
        job.transcript_model = str(result.get("transcript_model") or "")
        job.transcript_route_requested = str(
            result.get("transcript_route_requested") or job.transcript_route_requested
        )
        job.transcript_fallback_used = bool(result.get("transcript_fallback_used", False))
        job.transcript_fallback_reason = str(result.get("transcript_fallback_reason") or "")
        job.transcript_actual_provider = str(result.get("transcript_actual_provider") or "")
        job.transcript_actual_device = str(result.get("transcript_actual_device") or "")
        job.asr_worker_status = str(result.get("asr_worker_status") or "completed")
        job.worker_exitcode = result.get("worker_exitcode")
        job.last_activity_at = str(result.get("last_activity_at") or "")
        job.last_heartbeat_at = str(result.get("last_heartbeat_at") or "")
        job.last_segment_at = str(result.get("last_segment_at") or "")
        job.last_segment_end = float(result.get("last_segment_end") or 0)
        job.transcript_progress = float(result.get("transcript_progress") or 0)
    elif event == "asr_status":
        worker_event = str(payload.get("worker_event") or "")
        job.transcript_route_requested = str(
            payload.get("requested_route") or job.transcript_route_requested
        )
        job.transcript_actual_provider = str(
            payload.get("actual_provider") or job.transcript_actual_provider
        )
        job.transcript_actual_device = str(
            payload.get("actual_device") or job.transcript_actual_device
        )
        job.transcript_fallback_used = bool(
            payload.get("fallback_used", job.transcript_fallback_used)
        )
        job.transcript_fallback_reason = str(
            payload.get("fallback_reason") or job.transcript_fallback_reason
        )
        job.asr_worker_status = str(
            payload.get("asr_worker_status") or job.asr_worker_status
        )
        if payload.get("worker_exitcode") is not None:
            job.worker_exitcode = int(payload["worker_exitcode"])
        job.last_activity_at = str(payload.get("last_activity_at") or job.last_activity_at)
        job.last_heartbeat_at = str(
            payload.get("last_heartbeat_at") or job.last_heartbeat_at
        )
        job.last_segment_at = str(
            payload.get("last_segment_at") or job.last_segment_at
        )
        job.last_segment_end = float(payload.get("last_segment_end") or job.last_segment_end)
        job.transcript_progress = float(
            payload.get("transcript_progress") or job.transcript_progress
        )
        job.transcript_status = str(
            payload.get("transcript_status") or job.transcript_status
        )
        if worker_event == "error" and payload.get("reason"):
            job.error_code = str(payload["reason"])
        elif (
            job.transcript_fallback_reason.startswith("cpu_")
            and job.transcript_status in {"failed", "timeout"}
        ):
            # Compatibility for older CLI events that placed terminal CPU errors
            # in fallback_reason. New events use error_code/reason instead.
            job.error_code = job.transcript_fallback_reason
            job.transcript_fallback_reason = ""
    elif event == "task_failed" and isinstance(payload.get("error"), dict):
        job.error = str(payload["error"].get("message") or "")
        job.error_code = job.error_code or str(payload["error"].get("code") or "")
    stage = str(payload.get("stage") or "")
    progress = payload.get("progress")
    detail = f"{event}{' ' + stage if stage else ''}"
    if isinstance(progress, (int, float)):
        detail += f" {float(progress):.0%}"
    _append_log(job, detail)
    if event == "asr_status" and _should_persist_asr_job(job):
        _persist_job(job)


def _should_persist_asr_job(job: Job) -> bool:
    now = time.monotonic()
    state = JOB_ASR_PERSIST_STATE.setdefault(
        job.id,
        {
            "at": 0.0,
            "progress": 0.0,
            "segments": 0,
            "fallback": False,
        },
    )
    if job.asr_worker_status == "transcribing" and job.last_segment_at:
        state["segments"] = int(state["segments"]) + 1
    force = (
        job.transcript_status in {"completed", "failed", "timeout"}
        or job.asr_worker_status
        in {"model_loaded", "terminated", "failed", "completed", "finalizing"}
        or job.transcript_fallback_used != bool(state["fallback"])
    )
    threshold = (
        now - float(state["at"]) >= 10
        or int(state["segments"]) >= 20
        or job.transcript_progress - float(state["progress"]) >= 0.02
    )
    if not (force or threshold):
        return False
    state.update(
        {
            "at": now,
            "progress": job.transcript_progress,
            "segments": 0,
            "fallback": job.transcript_fallback_used,
        }
    )
    return True


def _append_runtime_logs(job: Job) -> None:
    _append_log(job, f"当前 Python 路径：{sys.executable}")
    _append_log(job, f"当前工作目录：{PROJECT_ROOT}")
    _append_log(job, f"知识包目录：{OUTPUT_ROOT}")
    if NETWORK_PROXY_STATUS.enabled:
        _append_log(
            job,
            f"网络代理：{NETWORK_PROXY_STATUS.endpoint}（{NETWORK_PROXY_STATUS.source}）",
        )
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
    payload: dict[str, Any] = {
        "version": __version__,
        "uiMode": "diagnostic" if _diagnostic_ui_mode() else "product",
        "dataDirectory": data_directory_status(),
    }
    if _diagnostic_flag("SHOW_TECH_DETAILS"):
        payload.update(
            {
                "network": NETWORK_PROXY_STATUS.public_payload(),
                "inProjectVenv": _is_project_venv_python(),
                "warning": _runtime_python_warning(),
                "pythonExecutable": sys.executable,
                "projectRoot": str(PROJECT_ROOT),
                "outputRoot": str(OUTPUT_ROOT),
                "tools": tools,
                "providers": [
                    {
                        key: value
                        for key, value in item.items()
                        if key
                        in {
                            "provider",
                            "name",
                            "configured",
                            "model",
                            "keySource",
                            "configSource",
                        }
                    }
                    for item in ProviderConfigResolver(WEB_PROVIDER_CONFIG).statuses()
                ],
            }
        )
    return payload


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
    return _display_output_dir(newest)


def _snapshot_job(job: Job) -> Job:
    return Job(
        id=job.id,
        command=list(job.command),
        schema_version=job.schema_version,
        analysis_profile=job.analysis_profile,
        processing_profile=job.processing_profile,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        status=job.status,
        returncode=job.returncode,
        logs=list(job.logs),
        cli_task_id=job.cli_task_id,
        knowledge_id=job.knowledge_id,
        identity_schema_version=job.identity_schema_version,
        request_fingerprint=job.request_fingerprint,
        duplicate_kind=job.duplicate_kind,
        duplicate_matched_task_id=job.duplicate_matched_task_id,
        duplicate_matched_knowledge_id=job.duplicate_matched_knowledge_id,
        duplicate_allowed_actions=list(job.duplicate_allowed_actions),
        output_dir=job.output_dir,
        error=job.error,
    )


def provider_config_payload() -> dict[str, Any]:
    statuses = ProviderConfigResolver(WEB_PROVIDER_CONFIG).statuses()
    safe_statuses = []
    for item in statuses:
        safe_item = {key: value for key, value in item.items() if key != "keyTail"}
        if isinstance(safe_item.get("lastTest"), dict):
            safe_item["lastTest"] = {
                key: value
                for key, value in safe_item["lastTest"].items()
                if key not in {"model", "provider", "error"}
            }
        safe_statuses.append(safe_item)
    if not _diagnostic_ui_mode():
        safe_statuses = [
            {
                "service": PRODUCT_PROVIDER_SERVICES.get(
                    str(item.get("provider") or item.get("name") or ""),
                    "service",
                ),
                "configured": bool(item.get("configured")),
                "lastTest": item.get("lastTest") or {},
            }
            for item in safe_statuses
        ]
    return {
        "providers": safe_statuses,
        "message": "API Key 默认仅用于当前本地运行会话，服务重启后需要重新填写。",
    }


def apply_provider_config(payload: dict[str, Any]) -> dict[str, Any]:
    WEB_PROVIDER_CONFIG.set_config(
        str(payload.get("provider") or ""),
        api_key=str(payload["apiKey"]) if "apiKey" in payload else None,
        base_url=str(payload["baseUrl"]) if "baseUrl" in payload else None,
        model=str(payload["model"]) if "model" in payload else None,
    )
    return provider_config_payload()


def clear_provider_config(provider: str) -> dict[str, Any]:
    WEB_PROVIDER_CONFIG.clear(provider)
    return provider_config_payload()


def test_provider_config(payload: dict[str, Any]) -> dict[str, Any]:
    provider_name = str(payload.get("provider") or "")
    current = ProviderConfigResolver(WEB_PROVIDER_CONFIG).resolve(provider_name)
    temporary_store = WebProviderConfigStore()
    temporary_store.set_config(
        provider_name,
        api_key=str(payload.get("apiKey") or "") or current.api_key,
        base_url=str(payload.get("baseUrl") or "") or current.base_url,
        model=str(payload.get("model") or "") or current.model,
    )
    resolver = ProviderConfigResolver(temporary_store)
    normalized_provider = resolver.resolve(provider_name).provider
    if normalized_provider == "groq":
        result = test_groq_connection(resolver.resolve("groq"))
    else:
        provider = resolver.provider(normalized_provider)
        result = test_provider_connection(provider)
    result["testedAt"] = time.time()
    WEB_PROVIDER_CONFIG.set_last_test(normalized_provider, result)
    if _diagnostic_ui_mode():
        public_test = {
            key: value
            for key, value in result.items()
            if key not in {"apiKey", "key", "keyTail", "headers"}
        }
    else:
        public_test = {
            key: value
            for key, value in result.items()
            if key in {"ok", "durationMs", "testedAt", "errorType"}
        }
        if not public_test.get("ok"):
            public_test["error"] = "连接测试失败，请检查凭据、网络和服务配置。"
    return {"test": public_test, **provider_config_payload()}


def _with_api_config_hint(message: str) -> str:
    text = sanitize_provider_error(message)
    triggers = ("未配置", "api_key", "鉴权", "HTTP 400", "HTTP 401", "HTTP 403", "HTTP 429", "Gemini", "DeepSeek")
    if any(item.lower() in text.lower() for item in triggers) and "API 配置" not in text:
        return f"{text} 请前往“API 配置”检查 Provider、模型和 Key。"
    return text


def job_to_dict(job: Job) -> dict[str, Any]:
    output_files: list[dict[str, str]] = []
    output_available = False
    if job.output_dir:
        output_path = _resolve_output_dir_reference(job.output_dir)
        if output_path.exists() and _is_within_output_root(output_path):
            output_available = True
            output_files = [
                {
                    "name": path.name,
                    "url": _output_file_url(path),
                }
                for path in sorted(output_path.iterdir())
                if path.is_file()
            ]
    payload = {
        "id": job.id,
        "createdAt": job.created_at,
        "updatedAt": job.updated_at,
        "startedAt": job.started_at,
        "finishedAt": job.finished_at,
        "status": job.status,
        "computeProfile": job.compute_profile,
        "queueReason": job.queue_reason,
        "activeResource": job.active_resource,
        "analysisProfile": job.analysis_profile,
        "processingProfile": job.processing_profile,
        "analysisRequested": job.analysis_requested,
        "analysisStatus": job.analysis_status,
        "analysisSkipReason": job.analysis_skip_reason,
        "transcriptOnly": job.transcript_only,
        "transcriptStatus": job.transcript_status,
        "transcriptRouteRequested": job.transcript_route_requested,
        "transcriptFallbackUsed": job.transcript_fallback_used,
        "lastActivityAt": job.last_activity_at,
        "lastSegmentEnd": job.last_segment_end,
        "transcriptProgress": job.transcript_progress,
        "logs": [],
        "knowledgeId": job.knowledge_id if (output_available or not job.output_dir) else "",
        "duplicateDecision": {
            "kind": job.duplicate_kind,
            "matchedTaskId": job.duplicate_matched_task_id,
            "matchedKnowledgeId": job.duplicate_matched_knowledge_id,
            "allowedActions": list(job.duplicate_allowed_actions),
        },
        "outputFiles": output_files,
        "error": _product_message(job.error),
    }
    if _diagnostic_flag("SHOW_TECH_DETAILS"):
        payload.update(
            {
                "command": [_safe_process_log(part) for part in job.command],
                "analysisProvider": job.analysis_provider,
                "analysisModel": job.analysis_model,
                "transcriptProvider": job.transcript_provider,
                "transcriptModel": job.transcript_model,
                "transcriptFallbackReason": job.transcript_fallback_reason,
                "transcriptActualProvider": job.transcript_actual_provider,
                "transcriptActualDevice": job.transcript_actual_device,
                "asrWorkerStatus": job.asr_worker_status,
                "lastHeartbeatAt": job.last_heartbeat_at,
                "lastSegmentAt": job.last_segment_at,
                "workerExitcode": job.worker_exitcode,
                "returncode": job.returncode,
                "cliTaskId": job.cli_task_id,
                "errorCode": job.error_code,
                "outputDir": _display_output_dir(output_path) if output_available else "",
            }
        )
    if _diagnostic_flag("SHOW_RAW_PROCESS_LOGS"):
        payload["logs"] = [_safe_process_log(line) for line in job.logs]
    payload["error"] = (
        _safe_process_log(str(payload.get("error") or ""))
        if _diagnostic_ui_mode()
        else _product_message(str(payload.get("error") or ""))
    )
    if "errorCode" in payload:
        payload["errorCode"] = _safe_process_log(str(payload.get("errorCode") or ""))
    return payload


def _resolve_output_dir_reference(value: str) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def _display_output_dir(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return str(resolved)


def _is_within_output_root(path: Path) -> bool:
    try:
        path.resolve().relative_to(OUTPUT_ROOT.resolve())
        return True
    except ValueError:
        return False


def _output_file_url(path: Path) -> str:
    output_root = OUTPUT_ROOT.resolve()
    relative = path.resolve().relative_to(output_root).as_posix()
    return "/output/" + quote(relative, safe="/")


def _processing_timing(manifest: dict[str, Any]) -> tuple[int | None, float | None, bool]:
    stored_duration = manifest.get("full_completion_duration_ms")
    if isinstance(stored_duration, (int, float)) and stored_duration >= 0:
        return int(stored_duration), _timestamp_ms(manifest.get("created_at")), False

    started_at = _parse_datetime(manifest.get("created_at"))
    completed_at = _parse_datetime(manifest.get("completed_at"))
    status = str(manifest.get("status") or "")
    is_live = status in {"created", "running", "processing"}
    if started_at and (completed_at or is_live):
        end = datetime.now(timezone.utc) if is_live else completed_at
        assert end is not None
        return max(0, int((end - started_at).total_seconds() * 1000)), started_at.timestamp() * 1000, is_live

    metrics = manifest.get("stage_metrics")
    if isinstance(metrics, dict):
        total = sum(
            float(metric.get("duration_ms") or 0)
            for metric in metrics.values()
            if isinstance(metric, dict)
        )
        if total > 0:
            return int(total), _timestamp_ms(manifest.get("created_at")), False
    return None, _timestamp_ms(manifest.get("created_at")), False


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _timestamp_ms(value: Any) -> float | None:
    parsed = _parse_datetime(value)
    return parsed.timestamp() * 1000 if parsed else None


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
        transcript_ready = inspection.transcript_segments > 0
        analysis_ready = (
            inspection.analysis_status == "success"
            and meaningful_analysis(analysis)
        )
        display_status = manifest.get("status") or ("completed" if (directory / "transcript.md").exists() else "unknown")
        if inspection.level == "invalid" and str(display_status).startswith("completed"):
            display_status = "invalid"
        elif transcript_ready and not analysis_ready and str(manifest.get("analysis_status")) == "skipped":
            display_status = "transcript_completed"
        processing_duration_ms, processing_started_at, processing_timing_live = (
            _processing_timing(manifest)
        )
        source_duration = source.get("duration") if isinstance(source, dict) else None
        if not isinstance(source_duration, (int, float)):
            source_duration = metadata.get("duration")
        items.append(
            {
                "id": str(manifest.get("knowledge_id") or directory.name),
                "legacy_id": directory.name if str(manifest.get("knowledge_id") or directory.name) != directory.name else "",
                "title": source.get("title") or metadata.get("title") or directory.name,
                "platform": source.get("platform") or metadata.get("source") or "unknown",
                "sourceType": source.get("source_type") or "unknown",
                "author": source.get("author") or metadata.get("author") or "",
                "thumbnail": source.get("thumbnail") or "",
                "duration": source_duration if isinstance(source_duration, (int, float)) else None,
                "analysisAt": manifest.get("completed_at") or "",
                "status": display_status,
                "currentStage": manifest.get("current_stage") or "",
                "updatedAt": directory.stat().st_mtime,
                "hasAnalysis": bool(analysis.get("summary") or analysis.get("highlights") or analysis.get("chapters")),
                "transcriptReady": transcript_ready,
                "analysisReady": analysis_ready,
                "analysisStatus": inspection.analysis_status,
                "analysisSkipReason": str(manifest.get("analysis_skip_reason") or ""),
                "analysisProfile": manifest.get("analysis_profile") or "summary",
                "processingProfile": manifest.get("processing_profile") or "complete",
                "firstReadableResultDurationMs": manifest.get("first_readable_result_duration_ms"),
                "processingDurationMs": processing_duration_ms,
                "processingStartedAt": processing_started_at,
                "processingTimingLive": processing_timing_live,
                "integrity": inspection.level,
                "integrityIssues": [issue.message for issue in inspection.issues[:5]],
                "chapterCount": _timeline_count(directory),
            }
        )
    return sorted(items, key=lambda item: item["updatedAt"], reverse=True)


def _collection_memberships() -> dict[str, list[dict[str, str]]]:
    memberships: dict[str, list[dict[str, str]]] = {}
    for record in KNOWLEDGE_SET_STORE.list():
        for item in record.items:
            knowledge_id = str(item.knowledge_id or "").strip()
            if knowledge_id:
                memberships.setdefault(knowledge_id, []).append(
                    {"kind": "series", "collectionId": record.set_id, "title": record.title}
                )
    for record in FOLDER_SET_STORE.list():
        for item in record.items:
            knowledge_id = str(item.knowledge_id or "").strip()
            if knowledge_id:
                memberships.setdefault(knowledge_id, []).append(
                    {"kind": "folder", "collectionId": record.set_id, "title": record.title}
                )
    return memberships


def library_items_with_membership() -> list[dict[str, Any]]:
    items = list_library_items()
    collection_memberships = _collection_memberships()
    project_memberships = PROJECT_GROUP_STORE.memberships()
    for item in items:
        knowledge_id = str(item.get("id") or "")
        collections = collection_memberships.get(knowledge_id, [])
        item["collectionMemberships"] = collections
        item["inCollection"] = bool(collections)
        item["projectId"] = project_memberships.get(knowledge_id, "")
    return items


def _search_cache_signature(directory: Path) -> tuple[tuple[str, int, int], ...]:
    names = (
        "metadata.json",
        "manifest.json",
        "analysis.json",
        "user_notes.md",
        "transcript.grouped.md",
        "transcript.raw.jsonl",
        "page_content.json",
    )
    signature: list[tuple[str, int, int]] = []
    for name in names:
        path = directory / name
        try:
            status = path.stat()
        except OSError:
            continue
        signature.append((name, status.st_mtime_ns, status.st_size))
    return tuple(signature)


def _read_search_text(path: Path, limit: int = SEARCH_FILE_LIMIT) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return handle.read(limit)
    except OSError:
        return ""


def _flatten_search_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (int, float, bool)):
        return [str(value)]
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(_flatten_search_values(item))
        return result
    if isinstance(value, dict):
        result = []
        for key, item in value.items():
            if str(key).lower() in {"raw_response", "provider", "model", "prompt"}:
                continue
            result.extend(_flatten_search_values(item))
        return result
    return []


def _normalized_search_text(*values: Any) -> str:
    flattened: list[str] = []
    for value in values:
        flattened.extend(_flatten_search_values(value))
    return " ".join(" ".join(flattened).split())


def _search_document(item: dict[str, Any], *, include_deep: bool = False) -> dict[str, Any]:
    knowledge_id = str(item.get("id") or "").strip()
    directory = resolve_library_dir(knowledge_id)
    cache_key = str(directory.resolve())
    signature = _search_cache_signature(directory)
    with SEARCH_DOCUMENT_CACHE_LOCK:
        cached = SEARCH_DOCUMENT_CACHE.get(cache_key)
        if cached and cached.get("signature") == signature and (not include_deep or cached["document"].get("deepLoaded")):
            return cached["document"]
    if cached and cached.get("signature") == signature:
        document = dict(cached["document"])
    else:
        analysis = _load_json_file(directory / "analysis.json")
        summary = _normalized_search_text(analysis.get("summary"))
        document = {
            "fast": _normalized_search_text(
                summary,
                analysis.get("highlights"),
                analysis.get("tags"),
                analysis.get("keywords"),
                _read_search_text(directory / "user_notes.md", 250_000),
            ),
            "deep": "",
            "deepLabel": "",
            "deepLoaded": False,
            "summary": summary[:1200],
        }
    if include_deep and not document.get("deepLoaded"):
        if (directory / "page_content.json").is_file():
            page = _load_json_file(directory / "page_content.json")
            blocks = page.get("blocks") if isinstance(page.get("blocks"), list) else []
            document["deep"] = _normalized_search_text(
                [
                    {"heading": block.get("heading"), "text": block.get("text")}
                    for block in blocks
                    if isinstance(block, dict)
                ]
            )
            document["deepLabel"] = "网页正文"
        else:
            deep_text = _read_search_text(directory / "transcript.grouped.md")
            if not deep_text:
                deep_text = _read_search_text(directory / "transcript.raw.jsonl")
            document["deep"] = _normalized_search_text(deep_text)
            document["deepLabel"] = "字幕正文"
        document["deepLoaded"] = True
    with SEARCH_DOCUMENT_CACHE_LOCK:
        SEARCH_DOCUMENT_CACHE[cache_key] = {"signature": signature, "document": document}
    return document


def _search_match_score(query: str, title: str, subtitle: str, fast_text: str, deep_text: str) -> tuple[int, str, str]:
    if not query:
        return 0, "recent", ""
    normalized_query = query.casefold()
    title_folded = title.casefold()
    subtitle_folded = subtitle.casefold()
    if title_folded == normalized_query:
        return 140, "title", title
    if title_folded.startswith(normalized_query):
        return 120, "title", title
    if normalized_query in title_folded:
        return 100, "title", title
    if normalized_query in subtitle_folded:
        return 70, "metadata", subtitle
    if normalized_query in fast_text.casefold():
        return 45, "knowledge", fast_text
    if deep_text and normalized_query in deep_text.casefold():
        return 25, "deep", deep_text
    return -1, "", ""


def _search_snippet(text: str, query: str, *, limit: int = 260) -> str:
    normalized = " ".join(str(text or "").split())
    if not normalized:
        return ""
    index = normalized.casefold().find(query.casefold()) if query else 0
    if index < 0:
        index = 0
    start = max(0, index - limit // 3)
    end = min(len(normalized), start + limit)
    snippet = normalized[start:end]
    if start:
        snippet = f"…{snippet}"
    if end < len(normalized):
        snippet = f"{snippet}…"
    snippet = sanitize_message(snippet)
    snippet = re.sub(r"(?i)file:///[^\s]+", "[本地路径]", snippet)
    snippet = re.sub(r"(?i)\b[A-Z]:[\\/](?:[^\s<>|]+[\\/]?)+", "[本地路径]", snippet)
    return snippet


def _sanitize_search_public_text(value: Any, *, limit: int = 500) -> str:
    return _search_snippet(str(value or ""), "", limit=limit)


def search_local_knowledge(query: str, *, kind: str = "all", deep: bool = False, limit: int = 50) -> dict[str, Any]:
    query = str(query or "").strip()
    if len(query) > 200:
        raise ValueError("搜索内容不能超过 200 个字符。")
    if kind not in {"all", "knowledge", "collection", "project"}:
        raise ValueError("kind 只能是 all、knowledge、collection 或 project。")
    if not 1 <= limit <= 50:
        raise ValueError("limit 必须在 1 到 50 之间。")

    results: list[dict[str, Any]] = []
    if kind in {"all", "knowledge"}:
        for item in library_items_with_membership():
            if query:
                try:
                    document = _search_document(item, include_deep=deep)
                except (FileNotFoundError, ValueError, OSError):
                    continue
            else:
                document = {"fast": "", "deep": "", "deepLabel": "", "summary": ""}
            title = str(item.get("title") or item.get("id") or "未命名记录")
            subtitle = " · ".join(
                value for value in (str(item.get("author") or ""), str(item.get("platform") or "")) if value
            )
            deep_text = document["deep"] if deep and query else ""
            score, match_field, matched_text = _search_match_score(query, title, subtitle, document["fast"], deep_text)
            if score < 0:
                continue
            if match_field == "deep":
                match_field = document["deepLabel"]
            results.append({
                "kind": "knowledge",
                "id": str(item.get("id") or ""),
                "title": _sanitize_search_public_text(title, limit=300),
                "subtitle": _sanitize_search_public_text(subtitle, limit=300),
                "status": str(item.get("status") or ""),
                "updatedAt": item.get("updatedAt"),
                "duration": item.get("duration"),
                "itemCount": None,
                "collectionKind": None,
                "matchField": match_field,
                "snippet": _search_snippet(matched_text or document["summary"] or title, query),
                "preview": _search_snippet(document["summary"] or document["fast"], query, limit=600),
                "score": score,
            })

    if kind in {"all", "collection"}:
        collections = [(record, "series") for record in KNOWLEDGE_SET_STORE.list()] + [
            (record, "folder") for record in FOLDER_SET_STORE.list()
        ]
        for record, collection_kind in collections:
            public = record.to_public()
            title = str(public.get("title") or "未命名合集")
            subtitle = "视频系列" if collection_kind == "series" else "本地文件夹集"
            score, match_field, matched_text = _search_match_score(query, title, subtitle, "", "")
            if score < 0:
                continue
            item_count = int(public.get("itemCount") or 0)
            results.append({
                "kind": "collection",
                "id": str(public.get("setId") or ""),
                "title": _sanitize_search_public_text(title, limit=300),
                "subtitle": _sanitize_search_public_text(subtitle, limit=300),
                "status": "",
                "updatedAt": public.get("updatedAt"),
                "duration": None,
                "itemCount": item_count,
                "collectionKind": collection_kind,
                "matchField": match_field,
                "snippet": _search_snippet(matched_text or title, query),
                "preview": f"{item_count} 个视频",
                "score": score,
            })

    if kind in {"all", "project"}:
        for public in _public_projects():
            title = str(public.get("title") or "未命名项目")
            score, match_field, matched_text = _search_match_score(query, title, "项目", "", "")
            if score < 0:
                continue
            item_count = int(public.get("itemCount") or 0)
            results.append({
                "kind": "project",
                "id": str(public.get("projectId") or ""),
                "title": _sanitize_search_public_text(title, limit=300),
                "subtitle": "项目",
                "status": "",
                "updatedAt": public.get("updatedAt"),
                "duration": None,
                "itemCount": item_count,
                "collectionKind": None,
                "matchField": match_field,
                "snippet": _search_snippet(matched_text or title, query),
                "preview": f"{item_count} 条知识记录",
                "score": score,
            })

    def sort_key(item: dict[str, Any]) -> tuple[int, float, str]:
        updated = item.get("updatedAt")
        if isinstance(updated, (int, float)):
            timestamp = float(updated)
        else:
            parsed = _parse_datetime(updated)
            timestamp = parsed.timestamp() if parsed else 0.0
        return (-int(item.get("score") or 0), -timestamp, str(item.get("title") or "").casefold())

    results.sort(key=sort_key)
    truncated = len(results) > limit
    return {
        "query": query,
        "kind": kind,
        "deep": bool(deep and query),
        "items": results[:limit],
        "truncated": truncated,
    }


def _available_knowledge_ids() -> set[str]:
    if not OUTPUT_ROOT.exists():
        return set()
    knowledge_ids: set[str] = set()
    for directory in OUTPUT_ROOT.iterdir():
        if not _is_knowledge_package(directory):
            continue
        manifest = _load_json_file(directory / "manifest.json")
        knowledge_ids.add(str(manifest.get("knowledge_id") or directory.name))
    return knowledge_ids


def _public_projects(valid_ids: set[str] | None = None) -> list[dict[str, Any]]:
    available_ids = valid_ids if valid_ids is not None else _available_knowledge_ids()
    return [record.to_public(valid_knowledge_ids=available_ids) for record in PROJECT_GROUP_STORE.list()]


def resolve_knowledge_by_source_url(source_url: str) -> dict[str, Any]:
    """Resolve a normalized HTTP source URL to sanitized local knowledge IDs.

    The Bridge uses this only as a local index lookup; it never fetches the
    supplied URL. Multiple package revisions may exist for one source, so the
    newest library item is returned first while preserving all matching IDs.
    """
    normalized = normalize_source_url(str(source_url or ""))
    matches: list[dict[str, Any]] = []
    for item in list_library_items():
        knowledge_id = str(item.get("id") or "").strip()
        if not knowledge_id:
            continue
        try:
            knowledge = load_knowledge_package(knowledge_id)
        except (FileNotFoundError, ValueError, OSError):
            continue
        source = knowledge.get("source") if isinstance(knowledge.get("source"), dict) else {}
        candidate = str(source.get("canonical_url") or source.get("source_url") or "")
        try:
            candidate_normalized = normalize_source_url(candidate)
        except ValueError:
            continue
        if not source_urls_equivalent(candidate_normalized, normalized):
            continue
        source_type = str(source.get("source_type") or "online_video")
        matches.append(
            {
                "knowledge_id": knowledge_id,
                "title": str(source.get("title") or knowledge.get("title") or knowledge_id),
                "source": {
                    "kind": "web_page" if source_type == "web_page" else "video",
                    "url": candidate_normalized,
                },
                "transcript_available": bool(knowledge.get("transcriptReady")),
                "analysis_available": bool(knowledge.get("analysisReady")),
            }
        )
    if not matches:
        raise FileNotFoundError(normalized)
    return {"source_url": normalized, "matches": matches}


def load_knowledge_package(knowledge_id: str) -> dict[str, Any]:
    directory = resolve_library_dir(knowledge_id)
    metadata = _load_json_file(directory / "metadata.json")
    manifest = _load_json_file(directory / "manifest.json")
    source = manifest.get("source") if isinstance(manifest.get("source"), dict) else dict(metadata)
    source = dict(source)
    local_path = str(source.pop("local_path", "") or source.pop("source_path", "") or metadata.get("source_path") or "")
    analysis = _normalize_analysis_view(_load_json_file(directory / "analysis.json"))
    analysis.pop("raw_response", None)
    inspection = inspect_knowledge_package(directory)
    if inspection.analysis_status == "invalid":
        analysis = {
            "status": "failed",
            "error": "知识包中的 analysis.json 无效，请运行 CLI inspect 查看详情。",
        }
    manifest_view = dict(manifest)
    manifest_view.setdefault("analysis_profile", "summary")
    manifest_view.setdefault("processing_profile", "complete")
    manifest_view.setdefault("stage_metrics", {})
    analysis_status = str(manifest_view.get("analysis_status") or analysis.get("status") or "pending")
    with JOBS_LOCK:
        legacy_job = next(
            (
                job
                for job in JOBS.values()
                if job.cli_task_id
                and job.cli_task_id == str(manifest_view.get("task_id") or "")
            ),
            None,
        )
    manifest_view.setdefault(
        "analysis_requested",
        legacy_job.analysis_requested if legacy_job else analysis_status != "skipped",
    )
    manifest_view.setdefault(
        "analysis_skip_reason",
        (
            legacy_job.analysis_skip_reason
            if legacy_job
            else "legacy_transcript_only" if analysis_status == "skipped" else ""
        ),
    )
    manifest_view.setdefault("analysis_provider", manifest_view.get("llm_provider") or analysis.get("provider") or "")
    manifest_view.setdefault("analysis_model", manifest_view.get("llm_model") or analysis.get("model") or "")
    manifest_view.setdefault(
        "transcript_only",
        legacy_job.transcript_only
        if legacy_job
        else not bool(manifest_view["analysis_requested"]),
    )
    if inspection.level == "invalid" and str(manifest_view.get("status") or "").startswith("completed"):
        manifest_view["status"] = "invalid"
        manifest_view["errors"] = [
            *list(manifest_view.get("errors") or []),
            *[issue.message for issue in inspection.issues if issue.severity == "error"][:5],
        ]
    timeline_payload = _load_json_file(directory / "timeline.json")
    visual_insights = _load_json_file(directory / "visual_insights.json")
    comments_payload = _load_json_file(directory / "comments.json")
    comment_insights = _load_json_file(directory / "comment_insights.json")
    timeline = timeline_payload.get("items", []) if isinstance(timeline_payload, dict) else []
    if not isinstance(timeline, list):
        timeline = []
    transcript_ready = inspection.transcript_segments > 0
    analysis_ready = (
        inspection.analysis_status == "success"
        and meaningful_analysis(analysis)
    )
    public_knowledge_id = str(manifest.get("knowledge_id") or knowledge_id)
    encoded_id = quote(public_knowledge_id, safe="")
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
    declared_source_type = str(source.get("source_type") or "")
    is_page = declared_source_type == "web_page"
    media_kind = "page" if is_page else "external"
    if media_available:
        media_kind = "audio" if media_path.suffix.lower() in {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus"} else "video"
    external_url = source.get("canonical_url") or source.get("source_url") or metadata.get("source_url") or ""
    embed = None if is_page else _external_player_descriptor(str(external_url))
    platform = str(source.get("platform") or metadata.get("platform") or "local").lower()
    normalized_platform = "bilibili" if platform in {"bili", "bilibili"} else platform
    if normalized_platform not in {"local", "youtube", "bilibili"}:
        normalized_platform = "generic" if external_url else "local"
    video_id = str((embed or {}).get("videoId") or source.get("video_id") or metadata.get("video_id") or "")
    payload = {
        "id": public_knowledge_id,
        "knowledge_id": public_knowledge_id,
        "legacy_id": directory.name if public_knowledge_id != directory.name else "",
        "source_type": declared_source_type or ("online_video" if external_url and not media_available else "local"),
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
        "transcriptReady": transcript_ready,
        "analysisReady": analysis_ready,
        "analysisRequested": bool(manifest_view.get("analysis_requested")),
        "analysisStatus": str(manifest_view.get("analysis_status") or analysis.get("status") or "pending"),
        "analysisSkipReason": str(manifest_view.get("analysis_skip_reason") or ""),
        "visualInsights": visual_insights,
        "comments": comments_payload.get("items", []) if isinstance(comments_payload.get("items"), list) else [],
        "commentInsights": comment_insights,
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
            "previewStatus": (
                "page_source"
                if is_page
                else
                "external_only"
                if external_url and not media_available and not embed
                else "available" if media_available or embed else "unavailable"
            ),
        },
    }
    return payload if _diagnostic_ui_mode() else _strip_product_details(payload)


def _strip_product_details(value: Any, path: tuple[str, ...] = ()) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_product_details(item, (*path, key))
            for key, item in value.items()
            if not _is_product_sensitive_key(key, path)
        }
    if isinstance(value, list):
        return [_strip_product_details(item, path) for item in value]
    return value


def _is_product_sensitive_key(key: str, path: tuple[str, ...]) -> bool:
    normalized_path = tuple(item.lower() for item in path)
    normalized_key = key.lower()
    if normalized_path[-2:] == ("media", "embed") and normalized_key in {
        "provider",
        "videoid",
        "url",
    }:
        return False
    return normalized_key in PRODUCT_SENSITIVE_KEYS


def _normalize_analysis_view(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {}
    try:
        return AnalysisResult.model_validate(payload).model_dump(mode="json")
    except (TypeError, ValueError):
        return dict(payload)


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
    manifest = _load_json_file(directory / "manifest.json")
    metadata = _load_json_file(directory / "metadata.json")
    source = manifest.get("source") if isinstance(manifest.get("source"), dict) else metadata
    if str(source.get("source_type") or "") == "web_page":
        page = _load_json_file(directory / "page_content.json")
        blocks = page.get("blocks") if isinstance(page.get("blocks"), list) else []
        return [
            {
                "index": int(item.get("index", index)),
                "start": None,
                "end": None,
                "title": str(item.get("heading") or f"页面片段 {index + 1}"),
                "text": str(item.get("text") or ""),
                "keywords": [],
                "sourceLink": str(source.get("canonical_url") or source.get("source_url") or ""),
                "contentKind": "web_page",
                "position": index + 1,
            }
            for index, item in enumerate(blocks)
            if isinstance(item, dict) and str(item.get("text") or "").strip()
        ]
    grouped_path = directory / "transcript.grouped.md"
    if grouped_path.exists():
        groups = _parse_grouped_markdown(grouped_path.read_text(encoding="utf-8"))
        if groups:
            return [{**group, "contentKind": "video_subtitle"} for group in groups]
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
                "contentKind": "video_subtitle",
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
                    "contentKind": "video_subtitle",
                }
            )
        return groups
    return []


def chat_with_knowledge(payload: dict[str, Any]) -> dict[str, Any]:
    knowledge_id = str(payload.get("knowledge_id") or "").strip()
    if not knowledge_id:
        raise ValueError("knowledge_id 不能为空。")
    knowledge = load_knowledge_package(knowledge_id)
    source_manifest = knowledge.get("manifest") if isinstance(knowledge.get("manifest"), dict) else {}
    source_payload = knowledge.get("source") if isinstance(knowledge.get("source"), dict) else {}
    if (
        str(source_payload.get("source_type") or "") == "web_page"
        and not bool(source_manifest.get("content_upload_allowed"))
    ):
        raise ValueError("该网页捕获未授权上传正文，不能运行云端问答。")
    groups = load_transcript_groups(knowledge_id)
    client_history = payload.get("history") or []
    if not isinstance(client_history, list):
        raise ValueError("history 必须是数组。")
    question = str(payload.get("question") or "")
    requested_provider = str(payload.get("provider") or "auto")
    resolver = ProviderConfigResolver(WEB_PROVIDER_CONFIG)
    registry = ProviderRegistry(
        {
            "deepseek": resolver.provider("deepseek"),
            "gemini": resolver.provider("gemini"),
        }
    )
    visual_terms = ("画面", "截图", "界面", "按钮", "图表", "图像", "视觉")
    visual_question = any(term in question for term in visual_terms)
    provider = registry.resolve(
        requested_provider,
        question,
        str(payload.get("model") or "") or None,
    )
    store = ChatStore(resolve_library_dir)
    stored_state = store.load(knowledge_id)
    stored_history = stored_state.get("messages", [])
    source = knowledge.get("source") if isinstance(knowledge.get("source"), dict) else {}
    source_url = str(source.get("canonical_url") or source.get("source_url") or knowledge.get("source_url") or "")
    fingerprint = _chat_source_fingerprint(source_url, source, knowledge_id)
    if stored_state.get("source_fingerprint") and stored_state.get("source_fingerprint") != fingerprint:
        stored_state = store.reset_for_source(
            knowledge_id,
            source_url=source_url,
            source_fingerprint=fingerprint,
            provider=provider.name,
            model=provider.model_name,
        )
        stored_history = []

    if isinstance(provider, GeminiProvider):
        request = prepare_grounded_request(
            question=question,
            groups=groups,
            analysis=knowledge.get("analysis") if isinstance(knowledge.get("analysis"), dict) else {},
            source=source,
            history=stored_history if stored_history else client_history,
            allow_fallback_context=True,
        )
        if request is None:
            raise ValueError("当前知识包没有可用于视频对话的上下文。")
        media_path = None
        try:
            media_path = resolve_media_path(knowledge_id)
        except FileNotFoundError:
            pass
        directory = resolve_library_dir(knowledge_id)
        frame_paths = _chat_frame_paths(directory, knowledge)
        routed = GeminiVideoChatRouter(provider).answer(
            request.messages,
            source_url=source_url,
            media_path=media_path,
            frame_paths=frame_paths,
            remote_file_id=str(stored_state.get("remote_file_id") or ""),
        )
        result = {
            "answer": routed.response.content,
            "citations": request.citations,
            "provider": routed.response.provider,
            "model": routed.response.model,
            "usage": routed.response.usage,
            "knowledge_id": knowledge_id,
            "route": routed.route,
            "route_status": routed.route_status,
            "route_attempts": routed.attempts,
        }
        if routed.route_status == "degraded":
            result["warning"] = (
                "Gemini 视频路由已降级为"
                f" {routed.route}。{routed.degradation_reason or '仍可基于现有知识包回答。'}"
            )
        store.update_state(
            knowledge_id,
            source_url=source_url,
            source_fingerprint=fingerprint,
            provider=routed.response.provider,
            model=routed.response.model,
            route=routed.route,
            route_status=routed.route_status,
            remote_file_id=routed.remote_file_id,
            remote_expires_at=routed.remote_expires_at,
            recovery_state="degraded" if routed.route_status == "degraded" else "ready",
            degradation_reason=routed.degradation_reason,
        )
    else:
        result = answer_question(
            question=question,
            groups=groups,
            analysis=knowledge.get("analysis") if isinstance(knowledge.get("analysis"), dict) else {},
            source=source,
            history=stored_history if stored_history else client_history,
            provider=provider,
            knowledge_id=knowledge_id,
        )
        result["route"] = "text_only"
        result["route_status"] = "available"
        result["route_attempts"] = [
            {"route": "text_only", "status": "available", "reason": ""}
        ]
        store.update_state(
            knowledge_id,
            source_url=source_url,
            source_fingerprint=fingerprint,
            provider=result["provider"],
            model=result["model"],
            route="text_only",
            route_status="available",
            recovery_state="ready",
        )
    if visual_question and not isinstance(provider, GeminiProvider):
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
            "route": result.get("route", ""),
            "route_status": result.get("route_status", ""),
        }
    )
    store.append(knowledge_id, new_messages)
    return result


def _chat_source_fingerprint(source_url: str, source: dict[str, Any], knowledge_id: str) -> str:
    identity = {
        "knowledge_id": knowledge_id,
        "source_url": source_url,
        "source_id": str(source.get("source_id") or ""),
        "platform": str(source.get("platform") or ""),
    }
    return hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _chat_frame_paths(directory: Path, knowledge: dict[str, Any]) -> list[Path]:
    relative_paths = []
    highlights = (knowledge.get("analysis") or {}).get("highlights", [])
    if isinstance(highlights, list):
        relative_paths.extend(
            str(item.get("image") or "")
            for item in highlights
            if isinstance(item, dict) and item.get("image")
        )
    frames_dir = directory / "frames"
    if frames_dir.is_dir():
        relative_paths.extend(
            f"frames/{path.name}"
            for path in sorted(frames_dir.iterdir())
            if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
        )
    result = []
    for relative in relative_paths:
        candidate = (directory / relative).resolve()
        try:
            candidate.relative_to(directory)
        except ValueError:
            continue
        if candidate.is_file() and candidate not in result:
            result.append(candidate)
        if len(result) >= 8:
            break
    return result


def resolve_library_dir(knowledge_id: str) -> Path:
    decoded = unquote(knowledge_id).strip()
    if not decoded or decoded in {".", ".."} or "/" in decoded or "\\" in decoded:
        raise ValueError("知识包 ID 不合法。")
    candidate = (OUTPUT_ROOT / decoded).resolve()
    output_root = OUTPUT_ROOT.resolve()
    if candidate.parent == output_root and _is_knowledge_package(candidate):
        return candidate
    if OUTPUT_ROOT.exists():
        for directory in OUTPUT_ROOT.iterdir():
            if not _is_knowledge_package(directory):
                continue
            manifest = _load_json_file(directory / "manifest.json")
            if str(manifest.get("knowledge_id") or "") == decoded:
                return directory.resolve()
    raise FileNotFoundError(decoded)


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
    elif (
        len(parts) == 3
        and parts[0] == "assets"
        and parts[1] == "highlights"
        and Path(parts[2]).suffix.lower() == ".webp"
    ):
        pass
    elif (
        len(parts) == 3
        and parts[0] == "assets"
        and parts[1] == "tutorial"
        and Path(parts[2]).suffix.lower() == ".webp"
    ):
        pass
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


def resolve_browser_media_path(knowledge_id: str) -> Path:
    """Return a browser-compatible media path without touching the source file.

    Chromium does not provide a native HTML5 MPEG-TS demuxer. Local ``.ts``
    recordings are therefore remuxed to an MP4 preview in the private Web UI
    state directory on first access. The original recording and knowledge
    package remain read-only.
    """
    source_path = resolve_media_path(knowledge_id)
    if source_path.suffix.lower() not in TS_MEDIA_EXTENSIONS:
        return source_path

    stat_result = source_path.stat()
    fingerprint = hashlib.sha256(
        f"{source_path.resolve()}:{stat_result.st_size}:{stat_result.st_mtime_ns}".encode("utf-8")
    ).hexdigest()
    preview_path = MEDIA_PREVIEW_ROOT / f"{fingerprint}.mp4"
    if preview_path.is_file() and preview_path.stat().st_size > 0:
        return preview_path

    with MEDIA_PREVIEW_LOCK:
        if preview_path.is_file() and preview_path.stat().st_size > 0:
            return preview_path
        ensure_dir(MEDIA_PREVIEW_ROOT)
        temporary_path = preview_path.with_suffix(".tmp.mp4")
        try:
            ffmpeg = resolve_executable("ffmpeg", getattr(WEB_CONFIG, "ffmpeg_path", ""))
            run_command(
                [
                    ffmpeg,
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    str(source_path),
                    "-map",
                    "0:v:0?",
                    "-map",
                    "0:a:0?",
                    "-c",
                    "copy",
                    "-movflags",
                    "+faststart",
                    str(temporary_path),
                ],
                timeout=float(getattr(WEB_CONFIG, "ffmpeg_timeout_seconds", 600)),
            )
            if not temporary_path.is_file() or temporary_path.stat().st_size <= 0:
                raise UserFacingError("TS 视频预览转换未生成有效文件。")
            temporary_path.replace(preview_path)
        finally:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
    return preview_path


def _bridge_request_id() -> str:
    return f"req_{uuid.uuid4().hex}"


def _bridge_data(data: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": "1.0", "request_id": _bridge_request_id(), "data": data}


def _bridge_error(code: str, message: str, *, retryable: bool, details: dict[str, Any] | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message, "retryable": retryable}
    if details:
        error["details"] = details
    return {"schema_version": "1.0", "request_id": _bridge_request_id(), "error": error}


def _intake_state_from_job(job: Job) -> str:
    status = str(job.status or "").strip().lower()
    if status in {"success", "completed"}:
        return "ready"
    if status in {"failed", "interrupted", "timeout"}:
        return "failed"
    return "processing"


def _reconcile_intake(item: Any) -> Any:
    local_job_id = str(getattr(item, "local_job_id", "") or "")
    if not local_job_id:
        return item
    with JOBS_LOCK:
        job = JOBS.get(local_job_id)
        snapshot = _snapshot_job(job) if job else None
    if snapshot is None:
        return item
    error = "任务处理失败，请检查配置后重试。" if _intake_state_from_job(snapshot) == "failed" else ""
    return INTAKE_STORE.reconcile_job(
        item.intake_id,
        state=_intake_state_from_job(snapshot),
        knowledge_id=str(snapshot.knowledge_id or ""),
        error=error,
    ) or item


def _intake_task_payload(item: Any) -> dict[str, Any]:
    if item.source_kind != "video":
        raise ValueError("当前 Intake 类型尚未接入本地视频处理。")
    return {
        "sourceType": "url",
        "source": item.canonical_url,
        "backend": "deepseek",
        "mode": item.analysis_profile,
        "processingProfile": item.processing_profile,
        "asr_route": "cloud",
        "asr_fallback_enabled": True,
        "transcriptGroupSeconds": 30,
    }


def _start_page_intake(item: Any) -> None:
    thread = threading.Thread(
        target=_run_page_intake,
        args=(str(item.intake_id),),
        daemon=True,
        name=f"page-intake-{str(item.intake_id)[-8:]}",
    )
    thread.start()


def _run_page_intake(intake_id: str) -> None:
    item = INTAKE_STORE.get(intake_id)
    if item is None:
        return
    try:
        provider = (
            ProviderConfigResolver(WEB_PROVIDER_CONFIG).provider("deepseek")
            if item.content_upload_allowed
            else None
        )
        package = ingest_page_capture(item, OUTPUT_ROOT, provider=provider)
        INTAKE_STORE.reconcile_job(
            intake_id,
            state="ready",
            knowledge_id=package.manifest.knowledge_id,
        )
    except Exception as exc:
        LOGGER.warning("page_intake_failed intake_id=%s error=%s", intake_id, _safe_process_log(str(exc)))
        INTAKE_STORE.fail_action(
            intake_id,
            "网页内容处理失败，请检查捕获内容和 API 配置后重试。",
        )


def _knowledge_set_item_state_from_job(job: Job) -> str:
    status = str(job.status or "").strip().lower()
    if status in {"success", "completed"}:
        return "ready"
    if status in {"failed", "interrupted", "timeout"}:
        return "failed"
    return "processing"


def _knowledge_package_state_index() -> dict[str, str]:
    result: dict[str, str] = {}
    if not OUTPUT_ROOT.exists():
        return result
    for directory in OUTPUT_ROOT.iterdir():
        if not _is_knowledge_package(directory):
            continue
        manifest = _load_json_file(directory / "manifest.json")
        status = str(manifest.get("status") or "unknown").strip().lower()
        result[directory.name] = status
        knowledge_id = str(manifest.get("knowledge_id") or "").strip()
        if knowledge_id:
            result[knowledge_id] = status
    return result


def _record_reconciliation_is_stale(record: Any, grace_seconds: float = 60.0) -> bool:
    updated_at = _parse_datetime(getattr(record, "updated_at", ""))
    if updated_at is None:
        return True
    return (datetime.now(timezone.utc) - updated_at).total_seconds() >= grace_seconds


def _reconcile_knowledge_set(record: Any) -> Any:
    if record is None:
        return None
    job_ids = {item.local_job_id for item in record.items if item.local_job_id}
    with JOBS_LOCK:
        snapshots = {
            job_id: _snapshot_job(JOBS[job_id])
            for job_id in job_ids
            if job_id in JOBS
        }
    package_states: dict[str, str] | None = None
    updates: list[dict[str, str]] = []
    for item in list(record.items):
        if not item.local_job_id:
            continue
        snapshot = snapshots.get(item.local_job_id)
        if snapshot is not None:
            state = _knowledge_set_item_state_from_job(snapshot)
            updates.append(
                {
                    "item_id": item.item_id,
                    "state": state,
                    "knowledge_id": str(snapshot.knowledge_id or ""),
                    "error": "单个视频处理失败，请检查配置后重试。" if state == "failed" else "",
                }
            )
            continue
        if item.knowledge_id:
            if package_states is None:
                package_states = _knowledge_package_state_index()
            package_status = package_states.get(item.knowledge_id, "")
            if package_status in {"completed", "completed_with_warnings", "success"}:
                updates.append({"item_id": item.item_id, "state": "ready", "knowledge_id": item.knowledge_id, "error": ""})
                continue
            if package_status in {"failed", "interrupted", "timeout"}:
                updates.append({"item_id": item.item_id, "state": "failed", "knowledge_id": item.knowledge_id, "error": "单个视频处理失败，请重试。"})
                continue
        if item.state == "processing" and _record_reconciliation_is_stale(record):
            updates.append({"item_id": item.item_id, "state": "needs_attention", "knowledge_id": item.knowledge_id or "", "error": "原任务记录不可用，请重新开始该条目。"})
    return KNOWLEDGE_SET_STORE.reconcile_items(record.set_id, updates) or record


def _knowledge_set_task_payload(item: Any, payload: dict[str, Any], record: Any | None = None) -> dict[str, Any]:
    record = record or {}
    return {
        "sourceType": "url",
        "source": item.source_url,
        "backend": "deepseek",
        "mode": str(payload.get("mode") or getattr(record, "analysis_profile", "tutorial")),
        "processingProfile": str(payload.get("processingProfile") or getattr(record, "processing_profile", "complete")),
        "lang": str(payload.get("lang") or ""),
        "export": str(payload.get("export") or "none"),
        "asr_route": str(payload.get("asr_route") or "cloud"),
        "asr_fallback_enabled": bool(payload.get("asr_fallback_enabled", True)),
        "transcriptGroupSeconds": int(payload.get("transcriptGroupSeconds") or getattr(record, "transcript_group_seconds", 30)),
        "comments": bool(payload.get("comments", False)),
        "noFrames": bool(payload.get("noFrames", False)),
    }


def _folder_set_item_state_from_job(job: Job) -> str:
    status = str(job.status or "").lower()
    if status in {"success", "completed"}:
        return "ready"
    if status in {"failed", "interrupted", "timeout"}:
        return "failed"
    return "processing"


def _reconcile_folder_set(record: Any) -> Any:
    if record is None:
        return None
    job_ids = {item.local_job_id for item in record.items if item.local_job_id}
    with JOBS_LOCK:
        snapshots = {
            job_id: _snapshot_job(JOBS[job_id])
            for job_id in job_ids
            if job_id in JOBS
        }
    package_states: dict[str, str] | None = None
    updates: list[dict[str, str]] = []
    for item in list(record.items):
        if not item.local_job_id:
            continue
        snapshot = snapshots.get(item.local_job_id)
        if snapshot is not None:
            state = _folder_set_item_state_from_job(snapshot)
            updates.append({"item_id": item.item_id, "state": state, "knowledge_id": str(snapshot.knowledge_id or ""), "error": "本地视频处理失败，请检查配置后重试。" if state == "failed" else ""})
            continue
        if item.knowledge_id:
            if package_states is None:
                package_states = _knowledge_package_state_index()
            package_status = package_states.get(item.knowledge_id, "")
            if package_status in {"completed", "completed_with_warnings", "success"}:
                updates.append({"item_id": item.item_id, "state": "ready", "knowledge_id": item.knowledge_id, "error": ""})
                continue
        if item.state == "processing" and _record_reconciliation_is_stale(record):
            updates.append({"item_id": item.item_id, "state": "needs_attention", "knowledge_id": item.knowledge_id or "", "error": "原任务记录不可用，请重新开始该条目。"})
    return FOLDER_SET_STORE.reconcile_items(record.set_id, updates) or record


def _folder_task_payload(item: Any, payload: dict[str, Any], record: Any | None = None) -> dict[str, Any]:
    record = record or {}
    saved_mode = getattr(record, "analysis_profile", "tutorial")
    saved_processing = getattr(record, "processing_profile", "complete")
    saved_group_seconds = getattr(record, "transcript_group_seconds", 30)
    return {
        "sourceType": "file", "source": item.source_path, "backend": "deepseek",
        "mode": str(payload.get("mode") or saved_mode), "processingProfile": str(payload.get("processingProfile") or saved_processing),
        "lang": str(payload.get("lang") or ""), "export": str(payload.get("export") or "none"),
        "asr_route": str(payload.get("asr_route") or "cloud"), "asr_fallback_enabled": bool(payload.get("asr_fallback_enabled", True)),
        "transcriptGroupSeconds": int(payload.get("transcriptGroupSeconds") or saved_group_seconds),
        "comments": bool(payload.get("comments", False)), "noFrames": bool(payload.get("noFrames", False)),
    }


class VideoSummaryHandler(BaseHTTPRequestHandler):
    server_version = f"VideoSummaryWeb/{__version__}"

    def _set_bridge_cors_headers(self) -> None:
        """Reflect only a user-explicitly configured extension origin."""
        allowed = str(os.environ.get("VIEWLEDGE_BRIDGE_EXTENSION_ORIGIN") or "").strip()
        origin = str(self.headers.get("Origin") or "").strip()
        if allowed and origin == allowed and origin.startswith("chrome-extension://"):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def do_OPTIONS(self) -> None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/v1/"):
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self._set_bridge_cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Idempotency-Key")
        self.send_header("Access-Control-Max-Age", "300")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/source/inspect":
            self._send_json({"error": "该接口只接受 POST。"}, HTTPStatus.METHOD_NOT_ALLOWED)
            return
        if parsed.path == "/api/search":
            try:
                query = parse_qs(parsed.query, keep_blank_values=True)
                search_query = str((query.get("q") or [""])[0])
                kind = str((query.get("kind") or ["all"])[0])
                deep = str((query.get("deep") or ["0"])[0]).lower() in {"1", "true", "yes"}
                limit = int((query.get("limit") or ["50"])[0])
                self._send_json(search_local_knowledge(search_query, kind=kind, deep=deep, limit=limit))
            except (TypeError, ValueError) as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/projects":
            self._send_json({"projects": _public_projects()})
            return
        if parsed.path.startswith("/api/projects/"):
            project_id = unquote(parsed.path[len("/api/projects/") :].strip("/"))
            record = PROJECT_GROUP_STORE.get(project_id)
            if record is None:
                self._send_json({"error": "项目不存在。"}, HTTPStatus.NOT_FOUND)
            else:
                valid_ids = _available_knowledge_ids()
                self._send_json({"project": record.to_public(valid_knowledge_ids=valid_ids)})
            return
        if parsed.path == "/api/folder-sets":
            records = [_reconcile_folder_set(record) for record in FOLDER_SET_STORE.list()]
            self._send_json({"sets": [record.to_public() for record in records]})
            return
        if parsed.path.startswith("/api/folder-sets/"):
            set_id = unquote(parsed.path[len("/api/folder-sets/") :].strip("/"))
            record = _reconcile_folder_set(FOLDER_SET_STORE.get(set_id))
            if record is None:
                self._send_json({"error": "local folder set not found"}, HTTPStatus.NOT_FOUND)
            else:
                self._send_json({"set": record.to_public()})
            return
        if parsed.path == "/api/knowledge-sets":
            records = [_reconcile_knowledge_set(record) for record in KNOWLEDGE_SET_STORE.list()]
            self._send_json({"sets": [record.to_public() for record in records]})
            return
        if parsed.path.startswith("/api/knowledge-sets/"):
            set_id = unquote(parsed.path[len("/api/knowledge-sets/") :].strip("/"))
            record = _reconcile_knowledge_set(KNOWLEDGE_SET_STORE.get(set_id))
            if record is None:
                self._send_json({"error": "知识集不存在。"}, HTTPStatus.NOT_FOUND)
            else:
                self._send_json({"set": record.to_public()})
            return
        if parsed.path == "/v1/inbox":
            try:
                query = parse_qs(parsed.query, keep_blank_values=True)
                cursor = str((query.get("cursor") or [""])[0])
                limit = int((query.get("limit") or ["50"])[0])
                items, next_cursor = INTAKE_STORE.list_inbox(cursor, limit)
                items = [_reconcile_intake(item) for item in items]
                self._send_json(_bridge_data({"items": [item.to_public() for item in items], "next_cursor": next_cursor}))
            except ValueError as exc:
                self._send_json(_bridge_error("invalid_request", str(exc), retryable=False), HTTPStatus.BAD_REQUEST)
            return
        if parsed.path.startswith("/v1/intakes/"):
            intake_id = unquote(parsed.path[len("/v1/intakes/") :].strip("/"))
            item = INTAKE_STORE.get(intake_id)
            item = _reconcile_intake(item) if item else None
            if item is None:
                self._send_json(_bridge_error("intake_not_found", "Intake 不存在。", retryable=False), HTTPStatus.NOT_FOUND)
            else:
                self._send_json(_bridge_data(item.to_public()))
            return
        if parsed.path == "/v1/knowledge/resolve":
            try:
                query = parse_qs(parsed.query, keep_blank_values=True)
                source_url = str((query.get("source_url") or query.get("url") or [""])[0]).strip()
                if not source_url:
                    raise ValueError("source_url is required")
                self._send_json(_bridge_data(resolve_knowledge_by_source_url(source_url)))
            except FileNotFoundError:
                self._send_json(_bridge_error("knowledge_not_found", "未找到匹配的知识记录。", retryable=False), HTTPStatus.NOT_FOUND)
            except ValueError as exc:
                self._send_json(_bridge_error("invalid_request", str(exc), retryable=False), HTTPStatus.BAD_REQUEST)
            return
        if parsed.path.startswith("/v1/knowledge/") and parsed.path.endswith("/transcript"):
            knowledge_id = unquote(parsed.path[len("/v1/knowledge/") : -len("/transcript")].strip("/"))
            try:
                knowledge = load_knowledge_package(knowledge_id)
                manifest = knowledge.get("manifest") if isinstance(knowledge.get("manifest"), dict) else {}
                source = manifest.get("source") if isinstance(manifest.get("source"), dict) else {}
                source_type = str(source.get("source_type") or "unknown")
                source_url = str(source.get("canonical_url") or source.get("source_url") or "")
                if not source_url.startswith(("http://", "https://")):
                    source_url = ""
                self._send_json(_bridge_data({
                    "knowledge_id": knowledge_id,
                    "title": str(source.get("title") or knowledge.get("title") or knowledge_id),
                    "source": {"kind": "web_page" if source_type == "web_page" else "video", "url": source_url or None},
                    "groups": load_transcript_groups(knowledge_id),
                }))
            except FileNotFoundError:
                self._send_json(_bridge_error("knowledge_not_found", "知识记录不存在。", retryable=False), HTTPStatus.NOT_FOUND)
            except ValueError as exc:
                self._send_json(_bridge_error("invalid_request", str(exc), retryable=False), HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/v1/clips":
            query = parse_qs(parsed.query, keep_blank_values=True)
            knowledge_id = str((query.get("knowledge_id") or [""])[0]).strip()
            intake_id = str((query.get("intake_id") or [""])[0]).strip()
            self._send_json(_bridge_data({"clips": [item.to_public() for item in CLIP_STORE.list(knowledge_id=knowledge_id, intake_id=intake_id)]}))
            return
        if parsed.path.startswith("/v1/clips/"):
            clip_id = unquote(parsed.path[len("/v1/clips/") :].strip("/"))
            item = CLIP_STORE.get(clip_id)
            if item is None:
                self._send_json(_bridge_error("clip_not_found", "剪藏不存在。", retryable=False), HTTPStatus.NOT_FOUND)
            else:
                self._send_json(_bridge_data(item.to_public()))
            return
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
            self._send_json({"items": library_items_with_membership()})
        elif parsed.path == "/api/runtime":
            self._send_json(runtime_status_payload())
        elif parsed.path == "/api/capabilities":
            self._send_json(capability_payload())
        elif parsed.path == "/api/providers":
            self._send_json(provider_config_payload())
        elif parsed.path == "/api/provider-config":
            self._send_json(provider_config_payload())
        elif parsed.path.startswith("/api/library/"):
            self._handle_library_get(parsed.path)
        elif parsed.path == "/api/jobs":
            with JOBS_LOCK:
                job_snapshots = [
                    _snapshot_job(job)
                    for job in sorted(JOBS.values(), key=lambda item: item.created_at, reverse=True)
                ]
            jobs = [job_to_dict(job) for job in job_snapshots]
            self._send_json({"jobs": jobs})
        elif parsed.path.startswith("/api/jobs/") or parsed.path.startswith("/api/tasks/"):
            job_id = parsed.path.rsplit("/", 1)[-1]
            with JOBS_LOCK:
                job = JOBS.get(job_id)
                job_snapshot = _snapshot_job(job) if job else None
            if not job:
                self._send_json({"error": "任务不存在。"}, HTTPStatus.NOT_FOUND)
                return
            assert job_snapshot is not None
            self._send_json({"job": job_to_dict(job_snapshot)})
        elif parsed.path.startswith("/output/"):
            self._send_output_file(parsed.path)
        else:
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/projects":
            try:
                payload = self._read_json_body()
                record, replayed = PROJECT_GROUP_STORE.create(
                    str(payload.get("title") or ""),
                    self.headers.get("Idempotency-Key", ""),
                )
                valid_ids = _available_knowledge_ids()
                self._send_json(
                    {"project": record.to_public(valid_knowledge_ids=valid_ids), "idempotencyReplayed": replayed},
                    HTTPStatus.OK if replayed else HTTPStatus.CREATED,
                )
            except ValueError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except OSError:
                self._send_json({"error": "项目保存失败，请检查共享知识目录。"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if parsed.path == "/api/folder-sets":
            try:
                payload = self._read_json_body()
                source = str(payload.get("source") or payload.get("path") or "").strip()
                record, replayed = FOLDER_SET_STORE.create(
                    source,
                    str(payload.get("title") or ""),
                    self.headers.get("Idempotency-Key", ""),
                    analysis_profile=str(payload.get("analysisProfile") or payload.get("mode") or "tutorial"),
                    processing_profile=str(payload.get("processingProfile") or "complete"),
                    transcript_group_seconds=int(payload.get("transcriptGroupSeconds") or 30),
                )
                self._send_json({"set": record.to_public(), "idempotencyReplayed": replayed}, HTTPStatus.OK if replayed else HTTPStatus.CREATED)
            except (ValueError, OSError) as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path.startswith("/api/folder-sets/"):
            relative = parsed.path[len("/api/folder-sets/") :].strip("/")
            parts = relative.split("/")
            try:
                payload = self._read_json_body()
                set_id = parts[0]
                record = _reconcile_folder_set(FOLDER_SET_STORE.get(set_id))
                if record is None:
                    self._send_json({"error": "local folder set not found"}, HTTPStatus.NOT_FOUND); return
                if len(parts) == 2 and parts[1] == "children":
                    child = FOLDER_SET_STORE.create_child(set_id, str(payload.get("title") or "new folder"))
                    self._send_json({"set": child.to_public()}, HTTPStatus.CREATED); return
                if len(parts) == 2 and parts[1] == "parent":
                    parent = FOLDER_SET_STORE.create_parent(set_id, str(payload.get("title") or "parent folder"))
                    self._send_json({"set": parent.to_public()}, HTTPStatus.CREATED); return
                if len(parts) == 2 and parts[1] == "reorder":
                    child_ids = payload.get("childSetIds")
                    if not isinstance(child_ids, list): raise ValueError("childSetIds must be an array")
                    updated = FOLDER_SET_STORE.reorder_children(set_id, [str(x) for x in child_ids])
                    self._send_json({"set": updated.to_public()}); return
                if len(parts) == 4 and parts[1] == "items" and parts[3] == "analyze":
                    item_id = parts[2]
                    record, item, replayed = FOLDER_SET_STORE.begin_item_action(set_id, item_id, self.headers.get("Idempotency-Key", ""))
                    if not replayed:
                        try:
                            job = start_job(_folder_task_payload(item, payload, record))
                        except DuplicateTaskError:
                            FOLDER_SET_STORE.reconcile_item(set_id, item_id, "needs_attention", error="该视频已有重复任务，请先处理知识记录中的任务。")
                            updated = _reconcile_folder_set(FOLDER_SET_STORE.get(set_id))
                            self._send_json({"set": updated.to_public(), "error": "该视频已有重复任务，请先处理知识记录中的任务。"}, HTTPStatus.ACCEPTED)
                            return
                        except Exception:
                            FOLDER_SET_STORE.reconcile_item(set_id, item_id, "failed", error="视频任务启动失败，请检查配置后重试。")
                            updated = _reconcile_folder_set(FOLDER_SET_STORE.get(set_id))
                            self._send_json({"set": updated.to_public(), "error": "视频任务启动失败，请检查配置后重试。"}, HTTPStatus.ACCEPTED)
                            return
                        FOLDER_SET_STORE.attach_job(set_id, item_id, job.id, job.knowledge_id)
                    updated = _reconcile_folder_set(FOLDER_SET_STORE.get(set_id))
                    self._send_json({"set": updated.to_public(), "idempotencyReplayed": replayed}, HTTPStatus.OK if replayed else HTTPStatus.ACCEPTED); return
                if len(parts) == 2 and parts[1] == "analyze-all":
                    started = 0
                    for folder in FOLDER_SET_STORE.descendants(set_id, include_self=True):
                        for item in list(folder.items):
                            if item.state not in {"queued", "failed", "needs_attention"}: continue
                            try:
                                _, current, replayed = FOLDER_SET_STORE.begin_item_action(folder.set_id, item.item_id, f"batch-{uuid.uuid4().hex}")
                                if replayed: continue
                            except (KeyError, ValueError):
                                continue
                            try:
                                job = start_job(_folder_task_payload(current, payload, folder))
                            except DuplicateTaskError:
                                FOLDER_SET_STORE.reconcile_item(folder.set_id, current.item_id, "needs_attention", error="该视频已有重复任务，请先处理知识记录中的任务。")
                                continue
                            except Exception:
                                FOLDER_SET_STORE.reconcile_item(folder.set_id, current.item_id, "failed", error="视频任务启动失败，请检查配置后重试。")
                                continue
                            FOLDER_SET_STORE.attach_job(folder.set_id, current.item_id, job.id, job.knowledge_id)
                            started += 1
                    updated = _reconcile_folder_set(FOLDER_SET_STORE.get(set_id))
                    self._send_json({"set": updated.to_public(), "started": started}, HTTPStatus.ACCEPTED); return
                self._send_json({"error": "unsupported folder set action"}, HTTPStatus.BAD_REQUEST)
            except KeyError:
                self._send_json({"error": "local folder set or item not found"}, HTTPStatus.NOT_FOUND)
            except (ValueError, UserFacingError) as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if parsed.path == "/api/source/inspect":
            try:
                payload = self._read_json_body()
                source_type = str(payload.get("sourceType") or "url")
                source = str(payload.get("source") or "").strip()
                if source_type == "file":
                    path = Path(normalize_local_path(source)).expanduser()
                    if path.is_dir():
                        self._send_json(inspect_folder(str(path)))
                    elif path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS:
                        self._send_json({"kind": "single", "isCollection": False, "title": path.stem, "sourceType": "file", "items": []})
                    else:
                        raise ValueError("本地路径不存在，或不是支持的视频文件/文件夹")
                    return
                if source_type != "url" or not source:
                    raise ValueError("系列识别只支持公开视频链接。")
                if not is_bilibili_input(source):
                    self._send_json({"kind": "single", "isCollection": False, "title": "", "sourceUrl": source, "items": []})
                else:
                    self._send_json(inspect_bilibili_input(source))
            except ValueError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except UserFacingError as exc:
                self._send_json({"error": _product_message(str(exc))}, HTTPStatus.BAD_GATEWAY)
            except Exception:
                self._send_json({"error": "B站来源识别失败，请稍后重试。"}, HTTPStatus.BAD_GATEWAY)
            return
        if parsed.path == "/api/knowledge-sets":
            try:
                payload = self._read_json_body()
                inspection = payload.get("inspection") if isinstance(payload.get("inspection"), dict) else payload
                record, replayed = KNOWLEDGE_SET_STORE.create(
                    inspection,
                    self.headers.get("Idempotency-Key", ""),
                    analysis_profile=str(payload.get("analysisProfile") or payload.get("mode") or "tutorial"),
                    processing_profile=str(payload.get("processingProfile") or "complete"),
                    transcript_group_seconds=int(payload.get("transcriptGroupSeconds") or 30),
                )
                self._send_json({"set": record.to_public(), "idempotencyReplayed": replayed}, HTTPStatus.OK if replayed else HTTPStatus.CREATED)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except OSError:
                self._send_json({"error": "知识集保存失败，请检查共享知识包目录。"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if parsed.path.startswith("/api/knowledge-sets/") and parsed.path.endswith("/analyze"):
            relative = parsed.path[len("/api/knowledge-sets/") : -len("/analyze")].strip("/")
            parts = relative.split("/")
            if len(parts) != 3 or parts[1] != "items" or not parts[2]:
                self._send_json({"error": "知识集条目路径不合法。"}, HTTPStatus.BAD_REQUEST)
                return
            set_id, item_id = parts[0], parts[2]
            try:
                payload = self._read_json_body()
                record = _reconcile_knowledge_set(KNOWLEDGE_SET_STORE.get(set_id))
                if record is None:
                    self._send_json({"error": "知识集不存在。"}, HTTPStatus.NOT_FOUND)
                    return
                record, item, replayed = KNOWLEDGE_SET_STORE.begin_item_action(
                    set_id,
                    item_id,
                    self.headers.get("Idempotency-Key", ""),
                )
                if not replayed:
                    try:
                        job = start_job(_knowledge_set_task_payload(item, payload, record))
                        record = KNOWLEDGE_SET_STORE.attach_job(set_id, item_id, job.id, job.knowledge_id)
                    except DuplicateTaskError as exc:
                        KNOWLEDGE_SET_STORE.mark_duplicate(set_id, item_id, "该视频已有重复任务，请先处理重复任务。")
                        self._send_json({"error": "该视频已有重复任务。", "duplicate": _duplicate_payload(exc.decision)}, HTTPStatus.CONFLICT)
                        return
                    except ValueError:
                        record = KNOWLEDGE_SET_STORE.fail_item(set_id, item_id, "处理服务尚未准备好，请完成本地 API 配置后重试。")
                        self._send_json({"set": record.to_public(), "idempotencyReplayed": False}, HTTPStatus.ACCEPTED)
                        return
                    except Exception:
                        record = KNOWLEDGE_SET_STORE.fail_item(set_id, item_id, "单个视频任务创建失败，请稍后重试。")
                        self._send_json({"set": record.to_public(), "idempotencyReplayed": False}, HTTPStatus.ACCEPTED)
                        return
                record = _reconcile_knowledge_set(record)
                self._send_json({"set": record.to_public(), "idempotencyReplayed": replayed}, HTTPStatus.OK if replayed else HTTPStatus.ACCEPTED)
            except KeyError:
                self._send_json({"error": "知识集或条目不存在。"}, HTTPStatus.NOT_FOUND)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/v1/clips":
            try:
                payload = self._read_json_body()
                item, replayed = CLIP_STORE.create(payload, self.headers.get("Idempotency-Key", ""))
                self._send_json(_bridge_data({**item.to_public(), "idempotency_replayed": replayed}), HTTPStatus.OK if replayed else HTTPStatus.CREATED)
            except ValueError as exc:
                self._send_json(_bridge_error("invalid_request", str(exc), retryable=False), HTTPStatus.BAD_REQUEST)
            except OSError:
                self._send_json(_bridge_error("storage_unavailable", "剪藏暂时无法保存，请稍后重试。", retryable=True), HTTPStatus.SERVICE_UNAVAILABLE)
            return
        if parsed.path == "/v1/intakes":
            try:
                payload = self._read_json_body()
                item, replayed = INTAKE_STORE.create(payload, self.headers.get("Idempotency-Key", ""))
                response = _bridge_data({
                    **item.to_public(),
                    "idempotency_replayed": replayed,
                })
                self._send_json(response, HTTPStatus.OK if replayed else HTTPStatus.CREATED)
            except ValueError as exc:
                self._send_json(_bridge_error("invalid_request", str(exc), retryable=False), HTTPStatus.BAD_REQUEST)
            except OSError:
                self._send_json(_bridge_error("storage_unavailable", "收件箱暂时不可用，请稍后重试。", retryable=True), HTTPStatus.SERVICE_UNAVAILABLE)
            return
        if parsed.path.startswith("/v1/intakes/") and parsed.path.endswith("/actions"):
            intake_id = unquote(parsed.path[len("/v1/intakes/") : -len("/actions")].strip("/"))
            try:
                payload = self._read_json_body()
                action = str(payload.get("action") or "").strip().lower()
                if action not in {"start", "retry", "cancel"}:
                    raise ValueError("action 只能是 start、retry 或 cancel。")
                item = INTAKE_STORE.get(intake_id)
                if item is None:
                    self._send_json(_bridge_error("intake_not_found", "Intake 不存在。", retryable=False), HTTPStatus.NOT_FOUND)
                    return
                item = _reconcile_intake(item)
                if item.state == "duplicate":
                    self._send_json(
                        _bridge_error(
                            "duplicate_intake",
                            "该 Intake 已存在重复任务。",
                            retryable=False,
                            details={
                                "knowledge_id": item.duplicate_knowledge_id,
                                "allowed_actions": list(item.duplicate_allowed_actions),
                            },
                        ),
                        HTTPStatus.CONFLICT,
                    )
                    return
                if action == "cancel":
                    item, replayed = INTAKE_STORE.begin_action(
                        intake_id,
                        action,
                        self.headers.get("Idempotency-Key", ""),
                    )
                    self._send_json(_bridge_data({**item.to_public(), "action": action, "idempotency_replayed": replayed}))
                    return
                item, replayed = INTAKE_STORE.begin_action(
                    intake_id,
                    action,
                    self.headers.get("Idempotency-Key", ""),
                )
                if item.source_kind == "page":
                    if not replayed:
                        if item.content_upload_allowed and not ProviderConfigResolver(
                            WEB_PROVIDER_CONFIG
                        ).resolve("deepseek").configured:
                            item = INTAKE_STORE.fail_action(
                                intake_id,
                                "文字分析服务尚未配置；完成 API 配置后可重试。",
                            )
                        else:
                            _start_page_intake(item)
                    item = INTAKE_STORE.get(intake_id) or item
                    self._send_json(
                        _bridge_data(
                            {
                                **item.to_public(),
                                "action": action,
                                "idempotency_replayed": replayed,
                            }
                        ),
                        HTTPStatus.OK if replayed else HTTPStatus.ACCEPTED,
                    )
                    return
                if item.source_kind != "video":
                    item = INTAKE_STORE.fail_action(intake_id, "当前 Intake 来源类型暂不支持处理。")
                    self._send_json(
                        _bridge_data({**item.to_public(), "action": action, "idempotency_replayed": replayed}),
                        HTTPStatus.ACCEPTED,
                    )
                    return
                if not replayed:
                    try:
                        job = start_job(_intake_task_payload(item))
                        INTAKE_STORE.attach_job(intake_id, job.id, job.knowledge_id)
                    except DuplicateTaskError as exc:
                        INTAKE_STORE.mark_duplicate(
                            intake_id,
                            kind=exc.decision.kind.value,
                            knowledge_id=exc.decision.matched_knowledge_id,
                            actions=list(exc.decision.allowed_actions),
                        )
                        self._send_json(
                            _bridge_error(
                                "duplicate_intake",
                                "该 Intake 已存在重复任务。",
                                retryable=False,
                                details={"allowed_actions": list(exc.decision.allowed_actions)},
                            ),
                            HTTPStatus.CONFLICT,
                        )
                        return
                    except ValueError:
                        item = INTAKE_STORE.fail_action(
                            intake_id,
                            "处理服务尚未准备好，请完成本地 API 配置后重试。",
                        )
                        self._send_json(_bridge_data({**item.to_public(), "action": action, "idempotency_replayed": False}), HTTPStatus.ACCEPTED)
                        return
                    except Exception:
                        item = INTAKE_STORE.fail_action(intake_id, "本地处理任务创建失败，请稍后重试。")
                        self._send_json(_bridge_data({**item.to_public(), "action": action, "idempotency_replayed": False}), HTTPStatus.ACCEPTED)
                        return
                item = _reconcile_intake(item)
                self._send_json(_bridge_data({**item.to_public(), "action": action, "idempotency_replayed": replayed}), HTTPStatus.OK if replayed else HTTPStatus.ACCEPTED)
            except KeyError:
                self._send_json(_bridge_error("intake_not_found", "Intake 不存在。", retryable=False), HTTPStatus.NOT_FOUND)
            except ValueError as exc:
                message = str(exc)
                code = "invalid_request" if "Idempotency-Key" in message or "action" in message else "invalid_state"
                self._send_json(_bridge_error(code, message, retryable=False), HTTPStatus.BAD_REQUEST)
            return
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
                reanalyze_knowledge_package(
                    directory,
                    config,
                    provider=ProviderConfigResolver(WEB_PROVIDER_CONFIG).provider("deepseek"),
                )
                self._send_json({"knowledge": load_knowledge_package(knowledge_id)})
            except ValueError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except FileNotFoundError:
                self._send_json({"error": "知识包不存在。"}, HTTPStatus.NOT_FOUND)
            except UserFacingError as exc:
                status = HTTPStatus.GATEWAY_TIMEOUT if is_timeout_error(exc) else HTTPStatus.BAD_GATEWAY
                self._send_json({"error": _with_api_config_hint(str(exc))}, status)
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
                chat_payload = chat_with_knowledge(self._read_json_body())
                self._send_json(
                    chat_payload if _diagnostic_ui_mode() else _strip_product_details(chat_payload)
                )
            except ValueError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except FileNotFoundError:
                self._send_json({"error": "知识包不存在。"}, HTTPStatus.NOT_FOUND)
            except UserFacingError as exc:
                self._send_json({"error": _with_api_config_hint(str(exc))}, HTTPStatus.BAD_GATEWAY)
            except Exception:
                self._send_json({"error": "上下文对话请求失败。"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if parsed.path == "/api/provider-config":
            try:
                self._send_json(apply_provider_config(self._read_json_body()))
            except ValueError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/capabilities/refresh":
            self._send_json(capability_payload(refresh=True))
            return
        if parsed.path == "/api/provider-config/test":
            try:
                self._send_json(test_provider_config(self._read_json_body()))
            except ValueError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self._send_json({"error": sanitize_provider_error(str(exc))}, HTTPStatus.BAD_GATEWAY)
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
        except DuplicateTaskError as exc:
            self._send_json({"error": str(exc), "duplicate": _duplicate_payload(exc.decision)}, HTTPStatus.CONFLICT)
            return
        except ValueError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        except Exception as exc:
            self._send_json({"error": _with_api_config_hint(f"创建任务失败：{exc}")}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        self._send_json({"job": job_to_dict(job)}, HTTPStatus.CREATED)

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/projects/") and "/records/" in parsed.path:
            relative = parsed.path[len("/api/projects/") :].strip("/")
            project_id, marker, knowledge_id = relative.partition("/records/")
            try:
                if marker != "/records/" or not project_id or not knowledge_id:
                    raise ValueError("项目成员路径无效。")
                knowledge_id = unquote(knowledge_id)
                resolve_library_dir(knowledge_id)
                record = PROJECT_GROUP_STORE.move_knowledge(unquote(project_id), knowledge_id)
                valid_ids = _available_knowledge_ids()
                self._send_json({"project": record.to_public(valid_knowledge_ids=valid_ids)})
            except KeyError:
                self._send_json({"error": "项目不存在。"}, HTTPStatus.NOT_FOUND)
            except FileNotFoundError:
                self._send_json({"error": "知识记录不存在。"}, HTTPStatus.NOT_FOUND)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except OSError:
                self._send_json({"error": "项目保存失败，请检查共享知识目录。"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
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
        if parsed.path.startswith("/api/projects/"):
            relative = parsed.path[len("/api/projects/") :].strip("/")
            project_id, marker, knowledge_id = relative.partition("/records/")
            try:
                if marker == "/records/":
                    if not project_id or not knowledge_id:
                        raise ValueError("项目成员路径无效。")
                    record = PROJECT_GROUP_STORE.remove_knowledge(unquote(project_id), unquote(knowledge_id))
                    valid_ids = _available_knowledge_ids()
                    self._send_json({"project": record.to_public(valid_knowledge_ids=valid_ids)})
                else:
                    if not relative or "/" in relative:
                        raise ValueError("项目路径无效。")
                    deleted = PROJECT_GROUP_STORE.delete(unquote(relative))
                    self._send_json({"deletedProjectId": deleted.project_id, "unlinkedCount": len(deleted.knowledge_ids)})
            except KeyError:
                self._send_json({"error": "项目不存在。"}, HTTPStatus.NOT_FOUND)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except OSError:
                self._send_json({"error": "项目保存失败，请检查共享知识目录。"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if parsed.path.startswith("/api/provider-config/"):
            provider = unquote(parsed.path.rsplit("/", 1)[-1])
            try:
                self._send_json(clear_provider_config(provider))
            except ValueError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
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

    def do_PATCH(self) -> None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/projects/"):
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        project_id = unquote(parsed.path[len("/api/projects/") :].strip("/"))
        if not project_id or "/" in project_id:
            self._send_json({"error": "项目路径无效。"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            payload = self._read_json_body()
            record = PROJECT_GROUP_STORE.rename(project_id, str(payload.get("title") or ""))
            valid_ids = _available_knowledge_ids()
            self._send_json({"project": record.to_public(valid_knowledge_ids=valid_ids)})
        except KeyError:
            self._send_json({"error": "项目不存在。"}, HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except OSError:
            self._send_json({"error": "项目保存失败，请检查共享知识目录。"}, HTTPStatus.INTERNAL_SERVER_ERROR)

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
                self._send_path(resolve_browser_media_path(knowledge_id), allow_range=True)
                return
            if action == "file" and len(parts) >= 3:
                self._send_path(resolve_library_file(knowledge_id, "/".join(parts[2:])))
                return
        except ValueError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        except (UserFacingError, TimeoutError) as exc:
            self._send_json(
                {"error": str(exc), "code": "media_preview_unavailable"},
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
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
        if urlparse(self.path).path.startswith("/v1/"):
            self._set_bridge_cors_headers()
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
        relative = unquote(request_path.lstrip("/")).replace("\\", "/")
        if not relative.startswith("output/"):
            self._send_json({"error": "文件不存在。"}, HTTPStatus.NOT_FOUND)
            return
        path = (OUTPUT_ROOT / relative[len("output/") :].strip("/")).resolve()
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
            <label>处理模式</label>
            <select id="processingProfile">
              <option value="complete">complete（兼容完整流程）</option>
              <option value="fast">fast（优先文本）</option>
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
          <label><input id="comments" type="checkbox"> 同步公开评论</label>
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
        processingProfile: $("processingProfile").value,
        lang: $("lang").value,
        export: $("exportMode").value,
        noFrames: $("noFrames").checked,
        comments: $("comments").checked,
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

    try:
        ensure_data_directory_writable()
        server = VideoSummaryServer((args.host, args.port), VideoSummaryHandler)
        _restore_scheduler_jobs()
    except UserFacingError as exc:
        raise SystemExit(str(exc)) from exc
    except OSError as exc:
        raise SystemExit(f"端口 {args.port} 已被占用或不可用。") from exc
    url = f"http://{args.host}:{args.port}"
    print(f"Video Summary Web UI: {url}")
    runtime = runtime_status_payload()
    if _diagnostic_flag("SHOW_TECH_DETAILS"):
        print(f"Python executable: {sys.executable}")
        print(f"Working directory: {PROJECT_ROOT}")
        print("Subprocess runner: uses this Web UI process sys.executable")
        for tool in runtime.get("tools", []):
            detail = f"{tool['path']} ({tool['source']})" if tool["available"] else "未配置或未发现"
            print(f"{tool['name']}: {detail}")
        for provider in runtime.get("providers", []):
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
