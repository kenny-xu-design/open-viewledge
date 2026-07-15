from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = PROJECT_ROOT / "output"
WEB_UI_ROOT = Path(__file__).resolve().parent / "web_ui"
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
}
MEDIA_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm", ".m4v", ".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus"}


@dataclass
class Job:
    id: str
    command: list[str]
    created_at: float = field(default_factory=time.time)
    status: str = "queued"
    returncode: int | None = None
    logs: list[str] = field(default_factory=list)
    output_dir: str = ""
    error: str = ""


JOBS: dict[str, Job] = {}
JOBS_LOCK = threading.Lock()


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

    command = [python_executable, "-m", "src.main"]
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
    thread = threading.Thread(target=_run_job, args=(job,), daemon=True)
    thread.start()
    return job


def _run_job(job: Job) -> None:
    before = _snapshot_output_dirs()
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    job.status = "running"
    try:
        _append_runtime_logs(job)
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
            _append_log(job, line.rstrip())
        job.returncode = process.wait()
        job.output_dir = _find_new_output_dir(before)
        job.status = "success" if job.returncode == 0 else "failed"
        if job.returncode != 0:
            job.error = f"CLI 退出码：{job.returncode}"
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)
        _append_log(job, f"处理失败：{exc}")


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
    with JOBS_LOCK:
        job.logs.append(line)
        if len(job.logs) > 400:
            job.logs = job.logs[-400:]


def _snapshot_output_dirs() -> set[Path]:
    if not OUTPUT_ROOT.exists():
        return set()
    return {path for path in OUTPUT_ROOT.iterdir() if path.is_dir()}


def _find_new_output_dir(before: set[Path]) -> str:
    if not OUTPUT_ROOT.exists():
        return ""
    candidates = [path for path in OUTPUT_ROOT.iterdir() if path.is_dir() and path not in before]
    if not candidates:
        candidates = [path for path in OUTPUT_ROOT.iterdir() if path.is_dir()]
    if not candidates:
        return ""
    newest = max(candidates, key=lambda path: path.stat().st_mtime)
    return str(newest.relative_to(PROJECT_ROOT)).replace("\\", "/")


def job_to_dict(job: Job) -> dict[str, Any]:
    output_files: list[dict[str, str]] = []
    if job.output_dir:
        output_path = (PROJECT_ROOT / job.output_dir).resolve()
        if output_path.exists():
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
        "status": job.status,
        "returncode": job.returncode,
        "logs": job.logs,
        "outputDir": job.output_dir,
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
        items.append(
            {
                "id": directory.name,
                "title": source.get("title") or metadata.get("title") or directory.name,
                "platform": source.get("platform") or metadata.get("source") or "unknown",
                "sourceType": source.get("source_type") or "unknown",
                "author": source.get("author") or metadata.get("author") or "",
                "thumbnail": source.get("thumbnail") or "",
                "status": manifest.get("status") or ("completed" if (directory / "transcript.md").exists() else "unknown"),
                "currentStage": manifest.get("current_stage") or "",
                "updatedAt": directory.stat().st_mtime,
                "hasAnalysis": bool(analysis.get("summary") or analysis.get("highlights") or analysis.get("chapters")),
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
    return {
        "id": knowledge_id,
        "status": manifest.get("status") or "unknown",
        "currentStage": manifest.get("current_stage") or "",
        "source": source,
        "manifest": manifest,
        "analysis": analysis,
        "timeline": timeline,
        "files": files,
        "frames": frames,
        "media": {
            "kind": media_kind,
            "available": media_available,
            "url": f"/api/library/{encoded_id}/media" if media_available else "",
            "externalUrl": source.get("canonical_url") or source.get("source_url") or metadata.get("source_url") or "",
            "thumbnail": source.get("thumbnail") or metadata.get("thumbnail") or "",
        },
    }


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
    return []


def resolve_library_dir(knowledge_id: str) -> Path:
    decoded = unquote(knowledge_id).strip()
    if not decoded or decoded in {".", ".."} or "/" in decoded or "\\" in decoded:
        raise ValueError("知识包 ID 不合法。")
    candidate = (OUTPUT_ROOT / decoded).resolve()
    if candidate.parent != OUTPUT_ROOT.resolve() or not _is_knowledge_package(candidate):
        raise FileNotFoundError(decoded)
    return candidate


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
    server_version = "VideoSummaryWeb/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_path(WEB_UI_ROOT / "index.html")
        elif parsed.path.startswith("/static/"):
            self._send_static(parsed.path[len("/static/") :])
        elif parsed.path == "/api/library":
            self._send_json({"items": list_library_items()})
        elif parsed.path == "/api/runtime":
            self._send_json(
                {
                    "pythonExecutable": sys.executable,
                    "projectRoot": str(PROJECT_ROOT),
                    "inProjectVenv": _is_project_venv_python(),
                    "warning": _runtime_python_warning(),
                }
            )
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
        if parsed.path == "/api/chat":
            self._send_json({"error": "上下文对话功能尚未接入"}, HTTPStatus.NOT_IMPLEMENTED)
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

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[web] {self.address_string()} - {fmt % args}")

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


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the video-summary-skill web UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5188)
    parser.add_argument("--open", action="store_true", help="Open the browser after starting.")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), VideoSummaryHandler)
    url = f"http://{args.host}:{args.port}"
    print(f"Video Summary Web UI: {url}")
    print(f"Python executable: {sys.executable}")
    print(f"Working directory: {PROJECT_ROOT}")
    print("Subprocess runner: uses this Web UI process sys.executable")
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
