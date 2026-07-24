from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from ..processing_profiles import ProcessingProfile
from ..schema_compat import require_supported_schema


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SourceRecord(BaseModel):
    source_type: Literal["local_video", "local_audio", "online_video", "web_page"]
    platform: str = "unknown"
    source_url: str = ""
    canonical_url: str = ""
    source_id: str = ""
    local_path: str = ""
    title: str = ""
    author: str = ""
    published_at: str = ""
    captured_at: str = Field(default_factory=utc_now)
    description: str = ""
    duration: float | None = None
    thumbnail: str = ""
    language: str = ""
    chapters: list[dict[str, Any]] = Field(default_factory=list)
    analysis_profile: str = "summary"


class TranscriptSegment(BaseModel):
    index: int
    start: float
    end: float
    text: str
    language: str = ""
    source: str = ""
    confidence: float | None = None


class TranscriptGroup(BaseModel):
    index: int
    start: float
    end: float
    title: str
    text: str
    segment_indexes: list[int]
    keywords: list[str] = Field(default_factory=list)
    representative_time: float | None = None


class TimelineEntry(BaseModel):
    index: int
    start: float
    end: float
    title: str
    summary: str = ""
    keywords: list[str] = Field(default_factory=list)
    representative_time: float | None = None
    frame_path: str = ""
    source_link: str = ""


class HighlightItem(BaseModel):
    title: str
    explanation: str = ""
    tags: list[str] = Field(default_factory=list)
    start: float | None = None
    end: float | None = None
    icon: str | None = None


class ThoughtQuestion(BaseModel):
    question: str
    related_topic: str = ""
    start: float | None = None


class ChapterSummary(BaseModel):
    title: str
    start: float
    end: float
    summary: str = ""
    frame_path: str = ""
    source_link: str = ""


class GlossaryItem(BaseModel):
    term: str
    definition: str = ""


class TimedTextItem(BaseModel):
    text: str
    timestamp: float | None = None


class TutorialStep(BaseModel):
    title: str
    description: str = ""
    timestamp: float | None = None
    expected_result: str = ""


class AnalysisResult(BaseModel):
    status: Literal["success", "failed", "skipped"] = "skipped"
    error: str = ""
    schema_version: str = "2"
    one_sentence_summary: str = ""
    summary: str = ""
    highlights: list[HighlightItem] = Field(default_factory=list)
    thoughts: list[ThoughtQuestion] = Field(default_factory=list)
    chapters: list[ChapterSummary] = Field(default_factory=list)
    terminology: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    glossary: list[GlossaryItem] = Field(default_factory=list)
    action_items: list[TimedTextItem] = Field(default_factory=list)
    prerequisites: list[TimedTextItem] = Field(default_factory=list)
    steps: list[TutorialStep] = Field(default_factory=list)
    warnings: list[TimedTextItem] = Field(default_factory=list)
    raw_response: str = ""
    analysis_profile: str = "summary"
    provider: str = ""
    model: str = ""
    usage: dict[str, int] = Field(default_factory=dict)
    generated_at: str = Field(default_factory=utc_now)

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        return require_supported_schema(value, supported_major=2, object_name="分析结果", legacy_default=1)


class ProviderAttempt(BaseModel):
    provider: str
    model: str = ""
    stage: str
    started_at: str = Field(default_factory=utc_now)
    finished_at: str = ""
    success: bool = False
    error_type: str = ""
    error_message: str = ""


class StageMetric(BaseModel):
    started_at: str = Field(default_factory=utc_now)
    completed_at: str = ""
    duration_ms: int = Field(default=0, ge=0)
    attempt: int = Field(default=1, ge=1)
    cache_hit: bool = False
    error_code: str = ""
    error_message: str = ""


class ProcessingManifest(BaseModel):
    schema_version: str = "1.0"
    task_id: str
    source: SourceRecord | None = None
    status: str = "created"
    current_stage: str = ""
    privacy_mode: bool = False
    sample_seconds: int | None = None
    created_at: str = Field(default_factory=utc_now)
    completed_at: str = ""
    asr_provider: str = ""
    asr_model: str = ""
    llm_provider: str = ""
    llm_model: str = ""
    analysis_status: Literal["pending", "completed", "failed", "skipped"] = "pending"
    analysis_error: str = ""
    prompt_version: str = "1"
    analysis_profile: str = "summary"
    processing_profile: ProcessingProfile = "complete"
    errors: list[str] = Field(default_factory=list)
    output_files: list[str] = Field(default_factory=list)
    stage_status: dict[str, str] = Field(default_factory=dict)
    stage_metrics: dict[str, StageMetric] = Field(default_factory=dict)
    cache_keys: dict[str, str] = Field(default_factory=dict)
    first_readable_result_at: str = ""
    first_readable_result_duration_ms: int | None = Field(default=None, ge=0)
    full_completion_duration_ms: int | None = Field(default=None, ge=0)
    provider_attempts: list[ProviderAttempt] = Field(default_factory=list)

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        return require_supported_schema(value, supported_major=1, object_name="知识包 Manifest")


class KnowledgePackage(BaseModel):
    source: SourceRecord
    transcript_segments: list[TranscriptSegment] = Field(default_factory=list)
    transcript_groups: list[TranscriptGroup] = Field(default_factory=list)
    timeline: list[TimelineEntry] = Field(default_factory=list)
    analysis: AnalysisResult | None = None
    manifest: ProcessingManifest
    output_dir: Path

    model_config = {"arbitrary_types_allowed": True}
