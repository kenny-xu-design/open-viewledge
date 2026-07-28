from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from typing import Any

from ..config import AppConfig
from ..domain.models import AnalysisResult, ProcessingManifest, SourceRecord, TimelineEntry, TranscriptGroup, TranscriptSegment, TranscriptStatus
from ..domain.models import utc_now
from ..processing_profiles import ProcessingProfile


LogCallback = Callable[[str], None]


@dataclass
class PipelineContext:
    config: AppConfig
    input_value: str
    output_dir: Path
    analysis_profile: str
    processing_profile: ProcessingProfile = "complete"
    no_analysis: bool = False
    generate_frames: bool = True
    sample_seconds: int | None = None
    log_callback: LogCallback | None = None
    event_callback: Callable[..., None] | None = None
    manifest_save_callback: Callable[[], None] | None = None
    source: SourceRecord | None = None
    media_path: Path | None = None
    subtitle_path: Path | None = None
    legacy_transcript_path: Path | None = None
    segments: list[TranscriptSegment] = field(default_factory=list)
    groups: list[TranscriptGroup] = field(default_factory=list)
    timeline: list[TimelineEntry] = field(default_factory=list)
    analysis: AnalysisResult | None = None
    manifest: ProcessingManifest | None = None
    previous_manifest: dict[str, Any] = field(default_factory=dict)
    cache_hits: set[str] = field(default_factory=set)
    skipped_stages: set[str] = field(default_factory=set)
    _last_asr_persist_at: float = 0.0
    _last_asr_persist_progress: float = 0.0
    _asr_segments_since_persist: int = 0

    def log(self, message: str) -> None:
        if self.log_callback:
            self.log_callback(message)

    def mark_cache_hit(self, stage: str) -> None:
        self.cache_hits.add(stage)

    def mark_stage_skipped(self, stage: str) -> None:
        self.skipped_stages.add(stage)

    def asr_event(self, message: dict[str, Any]) -> None:
        if not self.manifest:
            return
        import time

        event = str(message.get("type") or "")
        now = time.monotonic()
        self.manifest.last_activity_at = utc_now()
        if event == "heartbeat":
            self.manifest.last_heartbeat_at = self.manifest.last_activity_at
        if event in {
            "waiting_resource",
            "starting",
            "model_loading",
            "model_loaded",
            "transcribing",
        }:
            self.manifest.asr_worker_status = event
            self.manifest.transcript_status = TranscriptStatus.RUNNING
        elif event == "segment":
            end = max(0.0, float(message.get("end") or 0))
            self.manifest.asr_worker_status = "transcribing"
            self.manifest.last_segment_end = end
            self.manifest.last_segment_at = self.manifest.last_activity_at
            duration = float(self.manifest.asr_audio_duration_seconds or 0)
            if duration <= 0 and self.source:
                duration = float(self.source.duration or 0)
            self.manifest.transcript_progress = (
                min(1.0, end / duration) if duration > 0 else 0
            )
            self._asr_segments_since_persist += 1
        elif event == "result":
            self.manifest.asr_worker_status = "completed"
            self.manifest.transcript_progress = 1.0
        elif event == "worker_terminated":
            self.manifest.asr_worker_status = "terminated"
        elif event == "error":
            self.manifest.asr_worker_status = (
                "terminated" if message.get("timed_out") else "failed"
            )
        should_publish = event != "heartbeat" or now - self._last_asr_persist_at >= 5
        if should_publish and self.event_callback:
            self.event_callback(
                "asr_status",
                worker_event=event,
                reason=str(message.get("reason") or ""),
                task_id=self.manifest.task_id,
                requested_route=self.manifest.transcript_route_requested,
                actual_provider=self.manifest.transcript_actual_provider,
                actual_device=self.manifest.transcript_actual_device,
                fallback_used=self.manifest.transcript_fallback_used,
                fallback_reason=self.manifest.transcript_fallback_reason,
                asr_worker_status=self.manifest.asr_worker_status,
                worker_exitcode=self.manifest.worker_exitcode,
                last_activity_at=self.manifest.last_activity_at,
                last_heartbeat_at=self.manifest.last_heartbeat_at,
                last_segment_at=self.manifest.last_segment_at,
                last_segment_end=self.manifest.last_segment_end,
                transcript_progress=self.manifest.transcript_progress,
                transcript_status=self.manifest.transcript_status,
            )
        force_flush = event in {
            "model_loaded",
            "fallback",
            "result",
            "worker_terminated",
            "error",
            "completed",
            "finalizing",
        }
        threshold_flush = (
            now - self._last_asr_persist_at >= 10
            or self._asr_segments_since_persist >= 20
            or self.manifest.transcript_progress
            - self._last_asr_persist_progress
            >= 0.02
        )
        if force_flush or threshold_flush:
            self._last_asr_persist_at = now
            self._last_asr_persist_progress = self.manifest.transcript_progress
            self._asr_segments_since_persist = 0
            if self.manifest_save_callback:
                self.manifest_save_callback()
