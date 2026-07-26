from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from ..domain.models import AnalysisResult, HighlightItem, TimelineEntry, TutorialStep
from ..runtime_tools import resolve_executable
from ..utils import run_command


MAX_HIGHLIGHT_IMAGES = 8
MAX_TUTORIAL_STEP_IMAGES = 12
NEARBY_FRAME_SECONDS = 30.0
DEDUPLICATE_SECONDS = 2.0


@dataclass(frozen=True)
class HighlightSnapshotResult:
    analysis: AnalysisResult
    generated_count: int
    reused_count: int
    errors: list[str]


def generate_highlight_snapshots(
    media_path: Path,
    analysis: AnalysisResult,
    timeline: list[TimelineEntry],
    output_dir: Path,
    *,
    ffmpeg_path: str | Path | None = None,
) -> HighlightSnapshotResult:
    if not analysis.highlights:
        return HighlightSnapshotResult(analysis, 0, 0, [])

    highlights_dir = output_dir / "assets" / "highlights"
    highlights_dir.mkdir(parents=True, exist_ok=True)
    try:
        ffmpeg = resolve_executable("ffmpeg", ffmpeg_path)
    except Exception as exc:
        failed = [
            item.model_copy(update={"image_generation_status": "failed"})
            if _highlight_time(item) is not None
            else item
            for item in analysis.highlights
        ]
        return HighlightSnapshotResult(
            analysis.model_copy(update={"highlights": failed}),
            0,
            0,
            [f"高光截图无法启动 FFmpeg：{exc}"],
        )

    generated_count = 0
    reused_count = 0
    errors: list[str] = []
    captured_times: list[float] = []
    captured_hashes: set[str] = set()
    updated: list[HighlightItem] = []
    for index, item in enumerate(analysis.highlights):
        timestamp = _highlight_time(item)
        if timestamp is None or index >= MAX_HIGHLIGHT_IMAGES:
            updated.append(item.model_copy(update={"image_generation_status": "skipped"}))
            continue
        if any(abs(timestamp - previous) < DEDUPLICATE_SECONDS for previous in captured_times):
            updated.append(item.model_copy(update={"image_generation_status": "skipped"}))
            continue

        target = highlights_dir / f"highlight_{index + 1:03d}.webp"
        source_frame, source_timestamp = _nearest_existing_frame(timeline, output_dir, timestamp)
        try:
            if source_frame:
                command = [
                    ffmpeg,
                    "-y",
                    "-i",
                    str(source_frame),
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=min(1280\\,iw):-2:force_original_aspect_ratio=decrease",
                    "-c:v",
                    "libwebp",
                    "-quality",
                    "78",
                    str(target),
                ]
                status = "reused"
            else:
                command = [
                    ffmpeg,
                    "-y",
                    "-ss",
                    str(timestamp),
                    "-i",
                    str(media_path),
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=min(1280\\,iw):-2:force_original_aspect_ratio=decrease",
                    "-c:v",
                    "libwebp",
                    "-quality",
                    "78",
                    str(target),
                ]
                source_timestamp = timestamp
                status = "generated"
            run_command(command)
            if not target.is_file() or target.stat().st_size == 0:
                raise OSError("FFmpeg 未生成有效 WebP 文件。")
            image_hash = hashlib.sha256(target.read_bytes()).hexdigest()
            if image_hash in captured_hashes:
                target.unlink(missing_ok=True)
                updated.append(item.model_copy(update={"image_generation_status": "skipped"}))
                continue
        except Exception as exc:
            target.unlink(missing_ok=True)
            errors.append(f"高光 {index + 1} 截图失败：{exc}")
            updated.append(
                item.model_copy(
                    update={
                        "image": "",
                        "image_source_timestamp": source_timestamp,
                        "image_generation_status": "failed",
                    }
                )
            )
            continue

        captured_times.append(timestamp)
        captured_hashes.add(image_hash)
        generated_count += status == "generated"
        reused_count += status == "reused"
        updated.append(
            item.model_copy(
                update={
                    "image": target.relative_to(output_dir).as_posix(),
                    "image_source_timestamp": source_timestamp,
                    "image_generation_status": status,
                }
            )
        )

    return HighlightSnapshotResult(
        analysis.model_copy(update={"highlights": updated}),
        generated_count,
        reused_count,
        errors,
    )


def generate_tutorial_step_snapshots(
    media_path: Path,
    analysis: AnalysisResult,
    timeline: list[TimelineEntry],
    output_dir: Path,
    *,
    ffmpeg_path: str | Path | None = None,
) -> HighlightSnapshotResult:
    if analysis.analysis_profile != "tutorial" or not analysis.steps:
        return HighlightSnapshotResult(analysis, 0, 0, [])

    tutorial_dir = output_dir / "assets" / "tutorial"
    tutorial_dir.mkdir(parents=True, exist_ok=True)
    try:
        ffmpeg = resolve_executable("ffmpeg", ffmpeg_path)
    except Exception as exc:
        failed = [
            item.model_copy(update={"image_generation_status": "failed"})
            if _step_time(item) is not None
            else item
            for item in analysis.steps
        ]
        return HighlightSnapshotResult(
            _analysis_with_steps(analysis, failed),
            0,
            0,
            [f"教程步骤截图无法启动 FFmpeg：{exc}"],
        )

    generated_count = 0
    reused_count = 0
    errors: list[str] = []
    captured_times: list[float] = []
    captured_hashes: set[str] = set()
    updated: list[TutorialStep] = []
    for index, item in enumerate(analysis.steps):
        timestamp = _step_time(item)
        if timestamp is None or index >= MAX_TUTORIAL_STEP_IMAGES:
            updated.append(item.model_copy(update={"image_generation_status": "skipped"}))
            continue
        if any(abs(timestamp - previous) < DEDUPLICATE_SECONDS for previous in captured_times):
            updated.append(item.model_copy(update={"image_generation_status": "skipped"}))
            continue

        target = tutorial_dir / f"tutorial_step_{index + 1:03d}.webp"
        source_frame, source_timestamp = _nearest_existing_frame(timeline, output_dir, timestamp)
        try:
            if source_frame:
                command = [
                    ffmpeg,
                    "-y",
                    "-i",
                    str(source_frame),
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=min(1280\\,iw):-2:force_original_aspect_ratio=decrease",
                    "-c:v",
                    "libwebp",
                    "-quality",
                    "78",
                    str(target),
                ]
                status = "reused"
            else:
                command = [
                    ffmpeg,
                    "-y",
                    "-ss",
                    str(timestamp),
                    "-i",
                    str(media_path),
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=min(1280\\,iw):-2:force_original_aspect_ratio=decrease",
                    "-c:v",
                    "libwebp",
                    "-quality",
                    "78",
                    str(target),
                ]
                source_timestamp = timestamp
                status = "generated"
            run_command(command)
            if not target.is_file() or target.stat().st_size == 0:
                raise OSError("FFmpeg 未生成有效 WebP 文件。")
            image_hash = hashlib.sha256(target.read_bytes()).hexdigest()
            if image_hash in captured_hashes:
                target.unlink(missing_ok=True)
                updated.append(item.model_copy(update={"image_generation_status": "skipped"}))
                continue
        except Exception as exc:
            target.unlink(missing_ok=True)
            errors.append(f"教程步骤 {index + 1} 截图失败：{exc}")
            updated.append(
                item.model_copy(
                    update={
                        "image": "",
                        "image_source_timestamp": source_timestamp,
                        "image_generation_status": "failed",
                    }
                )
            )
            continue

        captured_times.append(timestamp)
        captured_hashes.add(image_hash)
        generated_count += status == "generated"
        reused_count += status == "reused"
        updated.append(
            item.model_copy(
                update={
                    "image": target.relative_to(output_dir).as_posix(),
                    "image_source_timestamp": source_timestamp,
                    "image_generation_status": status,
                }
            )
        )

    return HighlightSnapshotResult(_analysis_with_steps(analysis, updated), generated_count, reused_count, errors)


def _highlight_time(item: HighlightItem) -> float | None:
    value = item.timestamp if item.timestamp is not None else item.start
    return max(0.0, float(value)) if value is not None else None


def _step_time(item: TutorialStep) -> float | None:
    value = item.timestamp
    return max(0.0, float(value)) if value is not None else None


def _analysis_with_steps(analysis: AnalysisResult, steps: list[TutorialStep]) -> AnalysisResult:
    content = dict(analysis.content)
    content["steps"] = [item.model_dump(mode="json") for item in steps]
    return analysis.model_copy(update={"steps": steps, "content": content})


def _nearest_existing_frame(
    timeline: list[TimelineEntry],
    output_dir: Path,
    timestamp: float,
) -> tuple[Path | None, float]:
    candidates = [
        (abs(float(item.representative_time or item.start) - timestamp), item)
        for item in timeline
        if item.frame_path
    ]
    if not candidates:
        return None, timestamp
    distance, entry = min(candidates, key=lambda value: value[0])
    source_timestamp = float(entry.representative_time or entry.start)
    frame = output_dir / entry.frame_path
    if distance <= NEARBY_FRAME_SECONDS and frame.is_file():
        return frame, source_timestamp
    return None, timestamp
