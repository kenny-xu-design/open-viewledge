from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from ..processing_profiles import ProcessingProfile
from ..schema_compat import require_supported_schema


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TranscriptStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


def normalize_transcript_status(value: object) -> TranscriptStatus:
    normalized = str(value or TranscriptStatus.PENDING.value).strip().lower()
    if normalized == "success":
        normalized = TranscriptStatus.COMPLETED.value
    try:
        return TranscriptStatus(normalized)
    except ValueError:
        return TranscriptStatus.PENDING


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
    avg_logprob: float | None = None
    compression_ratio: float | None = None
    no_speech_prob: float | None = None
    language_probability: float | None = None
    low_confidence: bool = False
    quality_flags: list[str] = Field(default_factory=list)


class TranscriptResult(BaseModel):
    provider: Literal["platform", "groq", "faster-whisper"]
    model: str = ""
    device: Literal["cloud", "cuda", "cpu"]
    language: str = ""
    duration_seconds: float = Field(default=0, ge=0)
    segments: list[TranscriptSegment] = Field(default_factory=list)
    fallback_used: bool = False
    fallback_reason: str = ""
    warnings: list[str] = Field(default_factory=list)


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
    id: str = ""
    chapter_id: str = ""
    title: str
    explanation: str = ""
    tags: list[str] = Field(default_factory=list)
    start: float | None = None
    end: float | None = None
    icon: str | None = None
    timestamp: float | None = None
    summary: str = ""
    image: str = ""
    image_source_timestamp: float | None = None
    image_generation_status: Literal["generated", "reused", "skipped", "failed"] = "skipped"

    @model_validator(mode="after")
    def synchronize_compatible_fields(self) -> "HighlightItem":
        if self.timestamp is None:
            self.timestamp = self.start
        if self.start is None:
            self.start = self.timestamp
        if not self.summary:
            self.summary = self.explanation
        if not self.explanation:
            self.explanation = self.summary
        return self


class ThoughtQuestion(BaseModel):
    question: str
    related_topic: str = ""
    start: float | None = None


class ChapterSummary(BaseModel):
    id: str = ""
    title: str
    start: float
    end: float
    summary: str = ""
    children: list[dict[str, Any]] = Field(default_factory=list)
    frame_path: str = ""
    source_link: str = ""


class GlossaryItem(BaseModel):
    term: str
    definition: str = ""


class TimedTextItem(BaseModel):
    text: str
    timestamp: float | None = None


class TutorialStep(BaseModel):
    id: str = ""
    chapter_id: str = ""
    title: str
    description: str = ""
    timestamp: float | None = None
    objective: str = ""
    action: str = ""
    parameters: list[str] = Field(default_factory=list)
    expected_result: str = ""
    cautions: list[str] = Field(default_factory=list)
    image: str = ""
    image_source_timestamp: float | None = None
    image_generation_status: Literal["generated", "reused", "skipped", "failed"] = "skipped"

    @model_validator(mode="after")
    def synchronize_compatible_fields(self) -> "TutorialStep":
        if not self.action:
            self.action = self.description
        if not self.description:
            self.description = self.action
        return self


class AnalysisGeneration(BaseModel):
    visual_context_used: bool = False
    comments_included: bool = False


class SegmentationMetadata(BaseModel):
    policy_version: str = "adaptive-v2"
    duration_seconds: float = 0
    duration_bucket: str = "unknown"
    policy: str = "single_pass"
    strategy: str = "single_pass"
    window_seconds: int = 0
    overlap_seconds: int = 0
    chapter_target_range: list[int] = Field(default_factory=list)
    highlight_target_range: list[int] = Field(default_factory=list)
    actual_chapter_count: int = 0
    actual_highlight_count: int = 0
    actual_tutorial_step_count: int = 0
    coverage_ratio: float = 0
    largest_uncovered_gap_seconds: float = 0
    reanalysis_count: int = 0
    hierarchical_output: bool = False
    coverage_gap_threshold_seconds: int = 0
    quality_status: str = ""
    notes: list[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    status: Literal["success", "failed", "timeout", "skipped"] = "skipped"
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
    content: dict[str, Any] = Field(default_factory=dict)
    processing_profile: ProcessingProfile = "complete"
    source: dict[str, Any] = Field(default_factory=dict)
    generation: AnalysisGeneration = Field(default_factory=AnalysisGeneration)
    segmentation: SegmentationMetadata = Field(default_factory=SegmentationMetadata)
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

    @model_validator(mode="before")
    @classmethod
    def normalize_profile_content(cls, payload: object) -> object:
        if not isinstance(payload, dict):
            return payload
        data = dict(payload)
        profile = str(data.get("analysis_profile") or "summary")
        content = data.get("content")
        if not isinstance(content, dict) or not content:
            data["content"] = build_analysis_content_from_legacy(data, profile)
        else:
            data["content"] = normalize_analysis_content(content, profile)
            sync_legacy_fields_from_content(data, profile)

        generation = data.get("generation")
        if not isinstance(generation, dict):
            generation = {}
        generation["comments_included"] = False
        generation.setdefault("visual_context_used", False)
        data["generation"] = generation
        data.setdefault("source", {})
        data.setdefault("processing_profile", "complete")
        data.setdefault("segmentation", {})
        return data


def normalize_analysis_content(content: dict[str, Any], profile: str) -> dict[str, Any]:
    profile = profile if profile in {"summary", "tutorial", "viral", "close-reading"} else "summary"
    existing = dict(content)
    built = build_analysis_content_from_legacy(existing, profile)
    legacy_summary_keys = {
        "one_sentence_conclusion",
        "overview",
        "core_points",
        "key_conclusions",
        "actions_or_reflections",
        "verification_items",
    }
    for key, value in existing.items():
        if profile == "tutorial" and key == "steps":
            continue
        if profile == "summary" and key in legacy_summary_keys:
            continue
        cleaned = _without_placeholders(value)
        if cleaned not in (None, "", [], {}):
            built[key] = cleaned
    if profile == "summary":
        built["professional_terms"] = _professional_terms(built.get("professional_terms"))
    if profile != "tutorial":
        built = _without_images(built)
    return built


def build_analysis_content_from_legacy(payload: dict[str, Any], profile: str) -> dict[str, Any]:
    if profile == "tutorial":
        return _tutorial_content(payload)
    if profile == "viral":
        return _viral_content(payload)
    if profile == "close-reading":
        return _close_reading_content(payload)
    return _summary_content(payload)


def sync_legacy_fields_from_content(data: dict[str, Any], profile: str) -> None:
    content = data.get("content") if isinstance(data.get("content"), dict) else {}
    if not isinstance(content, dict):
        return
    if not data.get("one_sentence_summary"):
        data["one_sentence_summary"] = str(
            content.get("one_sentence")
            or content.get("one_sentence_conclusion")
            or content.get("tutorial_goal")
            or content.get("content_positioning")
            or content.get("core_thesis")
            or ""
        )
    if not data.get("summary"):
        data["summary"] = _content_summary_text(content, profile)
    if profile == "tutorial":
        if not data.get("steps"):
            data["steps"] = _content_steps(content)
        if not data.get("prerequisites"):
            data["prerequisites"] = [
                {"text": item, "timestamp": None}
                for item in _texts(content.get("prerequisites"))
            ]
    if profile == "summary":
        if not data.get("highlights") and isinstance(content.get("highlights"), list):
            data["highlights"] = _highlight_dicts(content["highlights"])
        if not data.get("thoughts") and isinstance(content.get("thoughts"), list):
            data["thoughts"] = _thought_dicts(content["thoughts"])
    chapter_source = content.get("chapter_summaries")
    if profile == "close-reading" and not chapter_source:
        chapter_source = content.get("chapter_close_reading")
    if not data.get("chapters") and isinstance(chapter_source, list):
        data["chapters"] = _legacy_chapters(chapter_source)


def _summary_content(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "one_sentence": _text(
            payload.get("one_sentence")
            or payload.get("one_sentence_conclusion")
            or payload.get("one_sentence_summary")
            or payload.get("summary")
        ),
        "summary": _text(payload.get("summary") or payload.get("overview")),
        "professional_terms": _professional_terms(
            payload.get("professional_terms")
            or payload.get("glossary")
            or payload.get("terminology")
        ),
        "highlights": _highlight_dicts(payload.get("highlights") or payload.get("core_points")),
        "thoughts": _thought_dicts(payload.get("thoughts") or payload.get("actions_or_reflections")),
        "chapter_summaries": _chapter_dicts(payload.get("chapter_summaries") or payload.get("chapters")),
        "factual_basis": _text(payload.get("factual_basis")),
        "ai_inferences": _texts(payload.get("ai_inferences")),
    }


def _tutorial_content(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "tutorial_goal": _text(payload.get("tutorial_goal") or payload.get("one_sentence_summary") or payload.get("summary")),
        "final_result": _text(payload.get("final_result")),
        "prerequisites": _texts(payload.get("prerequisites")),
        "tools_and_materials": _texts(payload.get("tools_and_materials") or payload.get("glossary")),
        "workflow_overview": _text(payload.get("workflow_overview") or payload.get("summary")),
        "chapter_summaries": _chapter_dicts(payload.get("chapter_summaries") or payload.get("chapters")),
        "steps": _content_steps(payload),
        "key_parameters": _texts(payload.get("key_parameters")),
        "troubleshooting": _texts(payload.get("troubleshooting") or payload.get("warnings")),
        "acceptance_checklist": _texts(payload.get("acceptance_checklist") or payload.get("action_items")),
        "reusable_commands_or_templates": _texts(payload.get("reusable_commands_or_templates") or payload.get("actions")),
        "limitations": _texts(payload.get("limitations")),
        "factual_basis": _text(payload.get("factual_basis")),
        "ai_inferences": _texts(payload.get("ai_inferences")),
    }


def _viral_content(payload: dict[str, Any]) -> dict[str, Any]:
    return _without_images({
        "content_positioning": _text(payload.get("content_positioning") or payload.get("one_sentence_summary") or payload.get("summary")),
        "target_audience": _texts(payload.get("target_audience")),
        "title_and_cover_promise": _text(payload.get("title_and_cover_promise")),
        "first_30_seconds_hook": _text(payload.get("first_30_seconds_hook")),
        "content_structure": _texts(payload.get("content_structure") or payload.get("chapters")),
        "retention_design": _texts(payload.get("retention_design")),
        "emotion_and_narrative": _texts(payload.get("emotion_and_narrative") or payload.get("thoughts")),
        "visual_packaging_and_editing": _texts(payload.get("visual_packaging_and_editing")),
        "interaction_and_distribution": _texts(payload.get("interaction_and_distribution") or payload.get("action_items")),
        "reusable_content_formula": _texts(payload.get("reusable_content_formula") or payload.get("actions")),
        "takeaways": _texts(payload.get("takeaways") or payload.get("highlights")),
        "risks_and_limitations": _texts(payload.get("risks_and_limitations") or payload.get("warnings")),
        "factual_basis": _text(payload.get("factual_basis")),
        "ai_inferences": _texts(payload.get("ai_inferences")),
    })


def _close_reading_content(payload: dict[str, Any]) -> dict[str, Any]:
    return _without_images({
        "core_thesis": _text(payload.get("core_thesis") or payload.get("one_sentence_summary") or payload.get("summary")),
        "key_concepts": _texts(payload.get("key_concepts") or payload.get("glossary") or payload.get("terminology")),
        "argument_map": _texts(payload.get("argument_map")),
        "chapter_close_reading": _chapter_dicts(payload.get("chapter_close_reading") or payload.get("chapters")),
        "evidence_assessment": _texts(payload.get("evidence_assessment") or payload.get("highlights")),
        "implicit_assumptions": _texts(payload.get("implicit_assumptions")),
        "counterarguments": _texts(payload.get("counterarguments") or payload.get("thoughts")),
        "argument_limits": _texts(payload.get("argument_limits") or payload.get("warnings")),
        "visual_evidence": _texts(payload.get("visual_evidence")),
        "extended_connections": _texts(payload.get("extended_connections") or payload.get("action_items")),
        "facts_to_verify": _texts(payload.get("facts_to_verify")),
        "factual_basis": _text(payload.get("factual_basis")),
        "ai_inferences": _texts(payload.get("ai_inferences")),
    })


def _content_steps(payload: dict[str, Any]) -> list[dict[str, Any]]:
    steps = payload.get("steps")
    if not isinstance(steps, list):
        return []
    result: list[dict[str, Any]] = []
    for item in steps:
        if hasattr(item, "model_dump"):
            item = item.model_dump(mode="json")
        if not isinstance(item, dict):
            continue
        result.append({
            "timestamp": item.get("timestamp"),
            "title": _text(item.get("title")) or "未命名步骤",
            "objective": _text(item.get("objective")),
            "action": _text(item.get("action") or item.get("description")),
            "parameters": _texts(item.get("parameters")),
            "expected_result": _text(item.get("expected_result")),
            "cautions": _texts(item.get("cautions")),
            "image": _text(item.get("image")),
            "image_source_timestamp": item.get("image_source_timestamp"),
            "image_generation_status": _text(item.get("image_generation_status")) or "skipped",
        })
    return result


def _legacy_chapters(items: list[Any]) -> list[dict[str, Any]]:
    chapters = []
    for item in items:
        if not isinstance(item, dict):
            continue
        chapters.append({
            "title": _text(item.get("title")) or "章节",
            "start": item.get("start") or item.get("timestamp") or 0,
            "end": item.get("end") or item.get("start") or item.get("timestamp") or 0,
            "summary": _text(item.get("summary") or item.get("text")),
            "source_link": _text(item.get("source_link")),
        })
    return chapters


def _chapter_dicts(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if hasattr(item, "model_dump"):
            item = item.model_dump(mode="json")
        if isinstance(item, dict):
            start = item.get("start") if item.get("start") is not None else item.get("timestamp")
            result.append({
                "title": _text(item.get("title")) or "章节",
                "start": start,
                "end": item.get("end"),
                "summary": _text(item.get("summary") or item.get("text")),
            })
        else:
            text = _text(item)
            if text:
                result.append({"title": text, "summary": text})
    return result


def _content_summary_text(content: dict[str, Any], profile: str) -> str:
    if profile == "tutorial":
        return _text(content.get("workflow_overview") or content.get("tutorial_goal"))
    if profile == "viral":
        return _text(content.get("content_positioning"))
    if profile == "close-reading":
        return _text(content.get("core_thesis"))
    return _text(
        content.get("summary")
        or content.get("overview")
        or content.get("one_sentence")
        or content.get("one_sentence_conclusion")
    )


def _professional_terms(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    rejected_categories = {
        "brand",
        "brand_name",
        "common_word",
        "unrelated_abbreviation",
        "品牌",
        "品牌名",
        "普通词",
        "无关缩写",
    }
    for item in value:
        if hasattr(item, "model_dump"):
            item = item.model_dump(mode="json")
        if not isinstance(item, dict):
            continue
        if item.get("core_related") is False or item.get("reliable") is False:
            continue
        category = str(item.get("category") or "").strip().lower()
        if category in rejected_categories:
            continue
        term = _text(item.get("term") or item.get("name"))
        definition = _text(item.get("definition") or item.get("description"))
        if not term or not definition:
            continue
        if _is_placeholder(term) or _is_placeholder(definition):
            continue
        identity = "".join(term.lower().split())
        if not identity or identity in seen:
            continue
        seen.add(identity)
        result.append({"term": term, "definition": definition})
        if len(result) == 8:
            break
    return result


def _highlight_dicts(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for item in value:
        if hasattr(item, "model_dump"):
            item = item.model_dump(mode="json")
        if isinstance(item, dict):
            title = _text(item.get("title") or item.get("text"))
            explanation = _text(item.get("explanation") or item.get("summary") or item.get("description"))
            if title:
                result.append({
                    "id": _text(item.get("id")),
                    "chapter_id": _text(item.get("chapter_id")),
                    "title": title,
                    "explanation": explanation,
                    "summary": explanation,
                    "tags": _texts(item.get("tags")),
                    "start": item.get("start") if item.get("start") is not None else item.get("timestamp"),
                    "end": item.get("end"),
                    "timestamp": item.get("timestamp") if item.get("timestamp") is not None else item.get("start"),
                })
        elif text := _text(item):
            result.append({"title": text, "explanation": text, "summary": text})
    return result


def _thought_dicts(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for item in value:
        if hasattr(item, "model_dump"):
            item = item.model_dump(mode="json")
        if isinstance(item, dict):
            question = _text(item.get("question") or item.get("text"))
            if question:
                result.append({
                    "question": question,
                    "related_topic": _text(item.get("related_topic")),
                    "start": item.get("start") if item.get("start") is not None else item.get("timestamp"),
                })
        elif text := _text(item):
            result.append({"question": text})
    return result


def _without_images(content: dict[str, Any]) -> dict[str, Any]:
    for value in content.values():
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    item.pop("image", None)
                    item.pop("image_source_timestamp", None)
                    item.pop("image_generation_status", None)
    return content


def _texts(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = _text(value)
        return [text] if text else []
    if isinstance(value, list):
        result = []
        for item in value:
            if text := _text(item):
                result.append(text)
        return result
    if text := _text(value):
        return [text]
    return []


def _text(value: object) -> str:
    if value is None:
        return ""
    if hasattr(value, "model_dump"):
        return _text(value.model_dump(mode="json"))
    if isinstance(value, str):
        text = value.strip()
        return "" if _is_placeholder(text) else text
    if isinstance(value, dict):
        for key in ("text", "summary", "description", "explanation", "title", "term", "question", "definition"):
            if key in value and str(value[key]).strip():
                return str(value[key]).strip()
        return ""
    return str(value).strip()


def _without_placeholders(value: object) -> object:
    if isinstance(value, str):
        return "" if _is_placeholder(value) else value
    if isinstance(value, list):
        return [
            cleaned
            for item in value
            if (cleaned := _without_placeholders(item)) not in (None, "", [], {})
        ]
    if isinstance(value, dict):
        return {
            key: cleaned
            for key, item in value.items()
            if (cleaned := _without_placeholders(item)) not in (None, "", [], {})
        }
    return value


def _is_placeholder(value: object) -> bool:
    return str(value or "").strip().lower() in {
        "未明确说明",
        "暂无",
        "暂无术语",
        "无",
        "none",
        "n/a",
    }


class ProviderAttempt(BaseModel):
    provider: str
    model: str = ""
    stage: str
    started_at: str = Field(default_factory=utc_now)
    finished_at: str = ""
    success: bool = False
    error_type: str = ""
    error_message: str = ""


class NormalizedComment(BaseModel):
    comment_id: str
    parent_id: str = ""
    author: str = ""
    content: str
    likes: int = Field(default=0, ge=0)
    reply_count: int = Field(default=0, ge=0)
    is_pinned: bool = False
    is_creator: bool = False
    published_at: str = ""
    source_url: str = ""
    timestamps: list[float] = Field(default_factory=list)
    platform: Literal["youtube", "bilibili", "yt-dlp"] = "yt-dlp"
    sync_cursor: str = ""
    fetched_at: str = Field(default_factory=utc_now)


class CommentInsight(BaseModel):
    status: Literal["success", "skipped", "failed"] = "skipped"
    provider: str = ""
    model: str = ""
    generated_at: str = Field(default_factory=utc_now)
    hot_topics: list[str] = Field(default_factory=list)
    consensus: list[str] = Field(default_factory=list)
    controversies: list[str] = Field(default_factory=list)
    corrections: list[str] = Field(default_factory=list)
    frequent_questions: list[str] = Field(default_factory=list)
    recommended_segments: list[dict[str, Any]] = Field(default_factory=list)
    needs_verification: list[str] = Field(default_factory=list)
    error: str = ""


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
    identity_schema_version: str = ""
    knowledge_id: str = ""
    source_fingerprint: str = ""
    request_fingerprint: str = ""
    source: SourceRecord | None = None
    status: str = "created"
    current_stage: str = ""
    privacy_mode: bool = False
    sample_seconds: int | None = None
    transcript_group_seconds: int = Field(default=30, ge=15, le=300)
    created_at: str = Field(default_factory=utc_now)
    completed_at: str = ""
    asr_provider: str = ""
    asr_model: str = ""
    asr_profile: str = ""
    asr_device: str = ""
    asr_compute_type: str = ""
    asr_batch_size: int = Field(default=0, ge=0)
    asr_beam_size: int = Field(default=0, ge=0)
    asr_low_confidence_segments: int = Field(default=0, ge=0)
    asr_local_retries: int = Field(default=0, ge=0)
    asr_audio_duration_seconds: float = Field(default=0, ge=0)
    asr_transcription_seconds: float = Field(default=0, ge=0)
    asr_rtf: float = Field(default=0, ge=0)
    transcript_status: TranscriptStatus = TranscriptStatus.PENDING
    transcript_provider: str = ""
    transcript_model: str = ""
    transcript_route_requested: Literal["cloud", "local_gpu", "local_cpu"] = "cloud"
    transcript_fallback_used: bool = False
    transcript_fallback_reason: str = ""
    transcript_actual_provider: str = ""
    transcript_actual_device: str = ""
    asr_worker_status: str = "idle"
    worker_exitcode: int | None = None
    last_activity_at: str = Field(default_factory=utc_now)
    last_heartbeat_at: str = ""
    last_segment_at: str = ""
    last_segment_end: float = Field(default=0, ge=0)
    transcript_progress: float = Field(default=0, ge=0, le=1)
    llm_provider: str = ""
    llm_model: str = ""
    analysis_requested: bool = True
    analysis_status: Literal["pending", "completed", "failed", "timeout", "skipped"] = "pending"
    analysis_skip_reason: str = ""
    analysis_provider: str = ""
    analysis_model: str = ""
    transcript_only: bool = False
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

    @field_validator("transcript_status", mode="before")
    @classmethod
    def normalize_legacy_transcript_status(cls, value: object) -> TranscriptStatus:
        return normalize_transcript_status(value)

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
