"""Run a disposable v1.5 local Bridge smoke without using project state.

The smoke starts a child Web process with temporary writable state, creates a
page Intake, starts it through the local-only path, verifies the resulting
knowledge record and transcript lookup, then checks clip idempotency and the
exact CORS opt-in. No API key, project package, or repository state is used.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ORIGIN = "chrome-extension://viewledge-v15-smoke"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request(base: str, path: str, *, method: str = "GET", payload: dict[str, Any] | None = None,
           headers: dict[str, str] | None = None) -> tuple[int, dict[str, Any], dict[str, str]]:
    body = None
    request_headers = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    try:
        with urlopen(Request(f"{base}{path}", data=body, headers=request_headers, method=method), timeout=5) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}, dict(response.headers.items())
    except HTTPError as exc:
        raw = exc.read().decode("utf-8")
        return exc.code, json.loads(raw) if raw else {}, dict(exc.headers.items())


def wait_for_runtime(base: str, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read()[-2000:] if process.stdout else ""
            raise RuntimeError(f"Web process exited early ({process.returncode}): {output}")
        try:
            status, _, _ = request(base, "/api/runtime")
            if status == 200:
                return
        except (OSError, URLError):
            pass
        time.sleep(0.1)
    raise TimeoutError("Web runtime did not become ready")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def write_video_fixture(root: Path) -> tuple[str, str]:
    """Create a minimal valid video package without media or Provider calls."""
    package = root / "knowledge" / "v15-video-fixture"
    package.mkdir(parents=True, exist_ok=True)
    source = {
        "source_type": "online_video",
        "platform": "bilibili",
        "canonical_url": "https://www.bilibili.com/video/BV1v15fixture",
        "source_url": "https://www.bilibili.com/video/BV1v15fixture",
        "source_id": "BV1v15fixture",
        "title": "v1.5 subtitle fixture",
        "duration": 12,
    }
    (package / "metadata.json").write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
    (package / "manifest.json").write_text(json.dumps({
        "schema_version": "1.0", "task_id": "v15-video-fixture-task",
        "knowledge_id": "v15-video-fixture", "status": "completed",
        "source": source, "transcript_status": "completed",
        "transcript_provider": "platform", "analysis_status": "skipped",
        "analysis_requested": False, "content_kind": "media_transcript",
    }, ensure_ascii=False), encoding="utf-8")
    (package / "analysis.json").write_text(json.dumps({"status": "skipped"}), encoding="utf-8")
    (package / "timeline.json").write_text(json.dumps({"items": [{"index": 0, "start": 1.0, "end": 4.0, "title": "Fixture", "summary": ""}]}), encoding="utf-8")
    (package / "source.md").write_text("# v1.5 subtitle fixture\n", encoding="utf-8")
    (package / "index.md").write_text("# v1.5 subtitle fixture\n", encoding="utf-8")
    (package / "transcript.raw.jsonl").write_text(json.dumps({"index": 0, "start": 1.0, "end": 4.0, "text": "字幕夹具内容", "source": "platform"}, ensure_ascii=False) + "\n", encoding="utf-8")
    (package / "transcript.grouped.md").write_text("# 分组字幕\n\n## 1. Fixture\n**时间：00:01 - 00:04**\n\n字幕夹具内容\n", encoding="utf-8")
    (package / "transcript.md").write_text("# 字幕夹具内容\n", encoding="utf-8")
    return source["canonical_url"], "v15-video-fixture"


def run() -> dict[str, Any]:
    port = free_port()
    with tempfile.TemporaryDirectory(prefix="viewledge-v15-smoke-") as temp:
        root = Path(temp)
        env = os.environ.copy()
        env.update({
            "VIEWLEDGE_STATE_ROOT": str(root / "state"),
            "VIEWLEDGE_OUTPUT_ROOT": str(root / "knowledge"),
            "VIEWLEDGE_CACHE_ROOT": str(root / "cache"),
            "VIEWLEDGE_BRIDGE_EXTENSION_ORIGIN": ORIGIN,
        })
        process = subprocess.Popen(
            [sys.executable, "-m", "src.web", "--host", "127.0.0.1", "--port", str(port)],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        base = f"http://127.0.0.1:{port}"
        try:
            wait_for_runtime(base, process)
            video_url, video_knowledge_id = write_video_fixture(root)
            status, resolved_video, _ = request(base, "/v1/knowledge/resolve?source_url=https%3A%2F%2Fwww.bilibili.com%2Fvideo%2FBV1v15fixture%3Fspm_id_from%3D333")
            require(status == 200 and resolved_video["data"]["matches"][0]["knowledge_id"] == video_knowledge_id, "video source resolve failed")
            status, video_transcript, _ = request(base, f"/v1/knowledge/{video_knowledge_id}/transcript")
            video_group = video_transcript["data"]["groups"][0]
            require(
                status == 200
                and video_transcript["data"]["source"]["kind"] == "video"
                and video_group.get("contentKind") == "video_subtitle"
                and video_group["start"] == 1.0
                and video_group["end"] == 4.0
                and video_group["text"] == "字幕夹具内容",
                "video subtitle transcript contract failed",
            )
            payload = {
                "schema_version": "1.0",
                "client_request_id": "smoke-page-1",
                "source": {"kind": "page", "url": "https://example.com/viewledge-smoke?utm_source=test"},
                "capture": {"title": "Viewledge smoke page", "selected_text": "A bounded smoke paragraph."},
                "preferences": {"analysis_profile": "summary", "processing_profile": "fast", "output_languages": ["source"]},
                "consent": {"user_initiated": True, "content_upload_allowed": False},
            }
            status, created, cors = request(
                base, "/v1/intakes", method="POST", payload=payload,
                headers={"Idempotency-Key": "smoke-page-key", "Origin": ORIGIN},
            )
            require(status == 201 and cors.get("Access-Control-Allow-Origin") == ORIGIN, "page Intake create/CORS failed")
            status, _, preflight = request(
                base, "/v1/intakes", method="OPTIONS",
                headers={
                    "Origin": ORIGIN,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type,idempotency-key",
                },
            )
            require(
                status == 204
                and preflight.get("Access-Control-Allow-Origin") == ORIGIN
                and preflight.get("Access-Control-Allow-Methods") == "GET, POST, OPTIONS"
                and "Idempotency-Key" in preflight.get("Access-Control-Allow-Headers", ""),
                "allowed extension preflight failed",
            )
            status, _, blocked_preflight = request(
                base, "/v1/intakes", method="OPTIONS",
                headers={
                    "Origin": "chrome-extension://other",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type,idempotency-key",
                },
            )
            require(status == 204 and "Access-Control-Allow-Origin" not in blocked_preflight, "arbitrary extension preflight was allowed")
            intake_id = created["data"]["intake_id"]
            status, replay, _ = request(
                base, "/v1/intakes", method="POST", payload=payload,
                headers={"Idempotency-Key": "smoke-page-key", "Origin": ORIGIN},
            )
            require(status == 200 and replay["data"]["idempotency_replayed"] and replay["data"]["intake_id"] == intake_id, "Intake replay failed")

            status, started, _ = request(
                base, f"/v1/intakes/{intake_id}/actions", method="POST", payload={"action": "start"},
                headers={"Idempotency-Key": "smoke-page-start", "Origin": ORIGIN},
            )
            require(status in {200, 202} and started["data"]["state"] in {"processing", "ready"}, "page Intake start failed")
            detail = started
            for _ in range(100):
                if detail["data"]["state"] != "processing":
                    break
                time.sleep(0.05)
                _, detail, _ = request(base, f"/v1/intakes/{intake_id}")
            require(detail["data"]["state"] == "ready", "page Intake did not reach ready")
            knowledge_id = detail["data"]["knowledge_id"]
            require(knowledge_id and "A bounded smoke paragraph." not in json.dumps(detail, ensure_ascii=False), "public Intake leaked captured text")

            status, resolved, _ = request(base, "/v1/knowledge/resolve?source_url=https%3A%2F%2Fexample.com%2Fviewledge-smoke")
            require(status == 200 and resolved["data"]["matches"][0]["knowledge_id"] == knowledge_id, "source resolve failed")
            status, transcript, _ = request(base, f"/v1/knowledge/{knowledge_id}/transcript")
            require(status == 200 and transcript["data"]["groups"], "transcript lookup failed")
            group = transcript["data"]["groups"][0]
            require(
                transcript["data"]["source"]["kind"] == "web_page"
                and group.get("contentKind") == "web_page"
                and group.get("start") is None
                and group.get("end") is None,
                "page transcript source/timestamp contract failed",
            )
            require("A bounded smoke paragraph." in group.get("text", ""), "page transcript text missing")

            clip_payload = {
                "schema_version": "1.0", "client_request_id": "smoke-clip-1", "kind": "clip",
                "target": {"knowledge_id": knowledge_id},
                "source": {"url": "https://example.com/viewledge-smoke", "title": "Viewledge smoke page"},
                "selection": {"text": "A bounded smoke paragraph.", "prefix": "", "suffix": "", "media_start_seconds": None, "media_end_seconds": None},
                "note": "smoke", "captured_at": "2026-01-01T00:00:00Z",
            }
            status, clip, _ = request(base, "/v1/clips", method="POST", payload=clip_payload, headers={"Idempotency-Key": "smoke-clip-key"})
            require(status == 201, "clip create failed")
            status, replayed_clip, _ = request(base, "/v1/clips", method="POST", payload=clip_payload, headers={"Idempotency-Key": "smoke-clip-key"})
            require(status == 200 and replayed_clip["data"]["idempotency_replayed"], "clip replay failed")
            _, clips, _ = request(base, f"/v1/clips?knowledge_id={knowledge_id}")
            require(len(clips["data"]["clips"]) == 1, "clip replay created a duplicate")

            _, _, blocked_cors = request(base, "/api/runtime", headers={"Origin": "chrome-extension://other"})
            require("Access-Control-Allow-Origin" not in blocked_cors, "arbitrary extension origin was allowed")
            return {
                "ok": True,
                "knowledge_id": knowledge_id,
                "intake_id": intake_id,
                "clip_id": clip["data"]["clip_id"],
                "transcript_kind": transcript["data"]["source"]["kind"],
                "group_content_kind": group.get("contentKind"),
                "video_subtitle_kind": video_transcript["data"]["source"]["kind"],
                "video_content_kind": video_group.get("contentKind"),
                "video_subtitle_start": video_group["start"],
            }
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False))
