from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from typing import Any

from ..config import AppConfig
from ..domain.models import AnalysisResult, ProcessingManifest, SourceRecord, TimelineEntry, TranscriptGroup, TranscriptSegment
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

    def log(self, message: str) -> None:
        if self.log_callback:
            self.log_callback(message)

    def mark_cache_hit(self, stage: str) -> None:
        self.cache_hits.add(stage)

    def mark_stage_skipped(self, stage: str) -> None:
        self.skipped_stages.add(stage)
