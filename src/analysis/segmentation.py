from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..domain.models import AnalysisResult, ChapterSummary, HighlightItem, SegmentationMetadata, ThoughtQuestion, TimelineEntry, TranscriptGroup, TutorialStep, build_analysis_content_from_legacy


POLICY_VERSION = "adaptive-v2"


@dataclass(frozen=True)
class SegmentationPolicy:
    duration_seconds: float
    transcript_chars: int
    analysis_profile: str
    processing_profile: str
    native_chapter_count: int
    transcript_group_count: int
    visual_available: bool = False
    duration_bucket: str = "unknown"
    policy: str = "single_pass"
    strategy: str = "single_pass"
    window_seconds: int = 0
    overlap_seconds: int = 0
    chapter_target_range: tuple[int, int] = (3, 5)
    highlight_target_range: tuple[int, int] = (2, 5)
    hierarchical_output: bool = False
    coverage_gap_threshold_seconds: int = 180
    use_window_analysis: bool = False
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class AnalysisWindow:
    index: int
    start: float
    end: float
    groups: list[TranscriptGroup]


def route_segmentation_policy(
    groups: list[TranscriptGroup],
    *,
    analysis_profile: str,
    processing_profile: str,
    native_chapter_count: int = 0,
    source_duration: float | None = None,
    visual_available: bool = False,
) -> SegmentationPolicy:
    duration = float(source_duration or max((item.end for item in groups), default=0.0) or 0.0)
    chars = sum(len(item.text or "") for item in groups)
    bucket, chapter_range, highlight_range, gap_threshold = _bucket(duration)
    density = chars / max(duration, 1.0)
    sparse = chars < 1_200 or density < 0.45
    has_good_native_chapters = native_chapter_count >= max(3, chapter_range[0] // 2)
    hierarchical = analysis_profile == "tutorial"
    notes: list[str] = []
    if sparse:
        notes.append("字幕内容稀疏，允许低于建议数量范围。")
    if has_good_native_chapters:
        notes.append("存在平台章节候选，作为语义锚点参与分析。")

    use_window = False
    strategy = "single_pass"
    policy = analysis_profile
    window_seconds = 0
    overlap_seconds = 0
    if duration > 3_600 and not sparse:
        use_window = True
        strategy = "hierarchical_semantic_map_reduce"
        policy = f"long_{analysis_profile.replace('-', '_')}"
        window_seconds = 360 if analysis_profile == "tutorial" else (600 if processing_profile == "complete" else 720)
        overlap_seconds = 60
    elif duration > 1_800 and not (sparse and has_good_native_chapters):
        use_window = True
        strategy = "semantic_map_reduce"
        policy = f"medium_{analysis_profile.replace('-', '_')}"
        window_seconds = 480 if processing_profile == "complete" else 600
        overlap_seconds = 45
    elif duration > 600 and chars > 10_000:
        use_window = True
        strategy = "light_semantic_map_reduce"
        policy = f"dense_{analysis_profile.replace('-', '_')}"
        window_seconds = 420
        overlap_seconds = 30

    return SegmentationPolicy(
        duration_seconds=duration,
        transcript_chars=chars,
        analysis_profile=analysis_profile,
        processing_profile=processing_profile,
        native_chapter_count=native_chapter_count,
        transcript_group_count=len(groups),
        visual_available=visual_available,
        duration_bucket=bucket,
        policy=policy,
        strategy=strategy,
        window_seconds=window_seconds,
        overlap_seconds=overlap_seconds,
        chapter_target_range=chapter_range,
        highlight_target_range=highlight_range,
        hierarchical_output=hierarchical,
        coverage_gap_threshold_seconds=gap_threshold if not hierarchical else min(gap_threshold, 480),
        use_window_analysis=use_window,
        notes=tuple(notes),
    )


def build_analysis_windows(groups: list[TranscriptGroup], policy: SegmentationPolicy) -> list[AnalysisWindow]:
    if not policy.use_window_analysis or not groups:
        return [AnalysisWindow(index=0, start=groups[0].start if groups else 0.0, end=groups[-1].end if groups else 0.0, groups=groups)]
    windows: list[AnalysisWindow] = []
    start = max(0.0, groups[0].start)
    duration_end = max(policy.duration_seconds, groups[-1].end)
    index = 0
    while start < duration_end:
        end = min(duration_end, start + policy.window_seconds)
        selected = [item for item in groups if item.end >= start and item.start <= end]
        if selected:
            windows.append(AnalysisWindow(index=index, start=selected[0].start, end=selected[-1].end, groups=selected))
            index += 1
        if end >= duration_end:
            break
        start = max(start + 60.0, end - policy.overlap_seconds)
    return windows or [AnalysisWindow(index=0, start=groups[0].start, end=groups[-1].end, groups=groups)]


def reduce_window_results(results: list[AnalysisResult], policy: SegmentationPolicy, groups: list[TranscriptGroup]) -> AnalysisResult:
    if not results:
        return AnalysisResult(status="skipped", analysis_profile=policy.analysis_profile, processing_profile=policy.processing_profile)
    if len(results) == 1:
        return attach_segmentation(results[0], policy, groups)

    base = results[0]
    chapters = _dedupe_chapters([item for result in results for item in result.chapters])
    highlights = _dedupe_highlights([item for result in results for item in result.highlights])
    thoughts = _dedupe_thoughts([item for result in results for item in result.thoughts])
    steps = _dedupe_steps([item for result in results for item in result.steps])
    _assign_chapter_ids(chapters, highlights, steps)

    summary = "\n\n".join(_unique_texts([result.summary for result in results if result.summary.strip()]))
    one_sentence = base.one_sentence_summary or next((result.one_sentence_summary for result in results if result.one_sentence_summary), "")
    warnings = [item for result in results for item in result.warnings]
    glossary = [item for result in results for item in result.glossary]
    action_items = [item for result in results for item in result.action_items]
    prerequisites = [item for result in results for item in result.prerequisites]
    professional_terms = _dedupe_professional_terms([
        item
        for result in results
        for item in result.content.get("professional_terms", [])
        if isinstance(item, dict)
    ])
    payload: dict[str, Any] = {
        "status": "success",
        "schema_version": "2",
        "one_sentence_summary": one_sentence,
        "summary": summary,
        "highlights": [item.model_dump(mode="json") for item in highlights],
        "thoughts": [item.model_dump(mode="json") for item in thoughts],
        "chapters": [item.model_dump(mode="json") for item in chapters],
        "steps": [item.model_dump(mode="json") for item in steps],
        "warnings": [item.model_dump(mode="json") for item in warnings],
        "glossary": [item.model_dump(mode="json") for item in glossary],
        "action_items": [item.model_dump(mode="json") for item in action_items],
        "prerequisites": [item.model_dump(mode="json") for item in prerequisites],
        "professional_terms": professional_terms,
        "analysis_profile": policy.analysis_profile,
        "processing_profile": policy.processing_profile,
        "provider": base.provider,
        "model": base.model,
        "usage": _merge_usage([result.usage for result in results]),
        "source": base.source,
        "generation": {
            "visual_context_used": any(result.generation.visual_context_used for result in results),
            "comments_included": False,
        },
    }
    payload["content"] = build_analysis_content_from_legacy(payload, policy.analysis_profile)
    return attach_segmentation(AnalysisResult.model_validate(payload), policy, groups)


def attach_segmentation(result: AnalysisResult, policy: SegmentationPolicy, groups: list[TranscriptGroup], *, reanalysis_count: int = 0) -> AnalysisResult:
    chapters = result.chapters
    highlights = result.highlights
    steps = result.steps
    _assign_chapter_ids(chapters, highlights, steps)
    repaired = _repair_coverage_gaps(chapters, steps, policy, groups)
    if repaired:
        reanalysis_count += repaired
        _assign_chapter_ids(chapters, highlights, steps)
    largest_gap = largest_uncovered_gap(chapters, steps if policy.analysis_profile == "tutorial" else [], policy.duration_seconds)
    coverage_ratio = 1.0 if policy.duration_seconds <= 0 else max(0.0, min(1.0, 1.0 - largest_gap / policy.duration_seconds))
    quality_status = "ok"
    notes = list(policy.notes)
    if largest_gap > policy.coverage_gap_threshold_seconds:
        quality_status = "coverage_gap_detected"
        notes.append("发现长时间内容空档；未在无充分内容支撑时机械插入节点。")
    segmentation = SegmentationMetadata(
        policy_version=POLICY_VERSION,
        duration_seconds=policy.duration_seconds,
        duration_bucket=policy.duration_bucket,
        policy=policy.policy,
        strategy=policy.strategy,
        window_seconds=policy.window_seconds,
        overlap_seconds=policy.overlap_seconds,
        chapter_target_range=list(policy.chapter_target_range),
        highlight_target_range=list(policy.highlight_target_range),
        actual_chapter_count=len(chapters),
        actual_highlight_count=len(highlights),
        actual_tutorial_step_count=len(steps),
        coverage_ratio=round(coverage_ratio, 4),
        largest_uncovered_gap_seconds=round(largest_gap, 2),
        reanalysis_count=reanalysis_count,
        hierarchical_output=policy.hierarchical_output,
        coverage_gap_threshold_seconds=policy.coverage_gap_threshold_seconds,
        quality_status=quality_status,
        notes=notes,
    )
    content = dict(result.content)
    if policy.analysis_profile == "tutorial":
        content["steps"] = [item.model_dump(mode="json") for item in steps]
        content["chapter_summaries"] = [item.model_dump(mode="json") for item in chapters]
    elif policy.analysis_profile == "summary":
        content["chapter_summaries"] = [item.model_dump(mode="json") for item in chapters]
        terms = _dedupe_professional_terms([
            item for item in content.get("professional_terms", []) if isinstance(item, dict)
        ])
        content["professional_terms"] = terms if len(terms) >= 3 else []
    elif policy.analysis_profile == "close-reading":
        content["chapter_close_reading"] = [item.model_dump(mode="json") for item in chapters]
    return result.model_copy(update={"chapters": chapters, "highlights": highlights, "steps": steps, "content": content, "segmentation": segmentation})


def _repair_coverage_gaps(chapters: list[ChapterSummary], steps: list[TutorialStep], policy: SegmentationPolicy, groups: list[TranscriptGroup]) -> int:
    if not policy.use_window_analysis or not groups or any("字幕内容稀疏" in note for note in policy.notes):
        return 0
    repaired = 0
    for gap_start, gap_end in _coverage_gaps(chapters, steps if policy.analysis_profile == "tutorial" else [], policy.duration_seconds, policy.coverage_gap_threshold_seconds):
        candidates = [
            group
            for group in groups
            if group.start > gap_start and group.end < gap_end and len(group.text.strip()) >= 80
        ]
        if not candidates:
            continue
        group = max(candidates, key=lambda item: len(item.text.strip()))
        if any(abs(chapter.start - group.start) < 45 for chapter in chapters):
            continue
        summary = group.text.strip().replace("\n", " ")[:180]
        chapter = ChapterSummary(
            title=group.title or f"{int(group.start // 60)} 分钟附近内容",
            start=group.start,
            end=group.end,
            summary=summary,
        )
        chapters.append(chapter)
        chapters.sort(key=lambda item: item.start)
        if policy.analysis_profile == "tutorial" and _looks_like_tutorial_step(group.text):
            steps.append(
                TutorialStep(
                    chapter_id=chapter.id,
                    title=group.title or "补充教程步骤",
                    timestamp=group.representative_time if group.representative_time is not None else group.start,
                    action=summary,
                    expected_result="未明确说明",
                )
            )
            steps.sort(key=lambda item: item.timestamp if item.timestamp is not None else 0)
        repaired += 1
        if repaired >= 3:
            break
    return repaired


def _coverage_gaps(chapters: list[ChapterSummary], steps: list[TutorialStep], duration_seconds: float, threshold: int) -> list[tuple[float, float]]:
    anchors = [0.0, max(0.0, duration_seconds)]
    anchors.extend(float(item.start) for item in chapters)
    anchors.extend(float(item.timestamp) for item in steps if item.timestamp is not None)
    anchors = sorted(set(round(value, 2) for value in anchors if 0 <= value <= max(duration_seconds, 0.0)))
    return [(a, b) for a, b in zip(anchors, anchors[1:]) if b - a > threshold]


def _looks_like_tutorial_step(text: str) -> bool:
    sample = text.lower()
    return any(marker in sample for marker in ("点击", "选择", "打开", "输入", "设置", "创建", "安装", "运行", "调整", "保存", "拖", "click", "select", "create", "set", "run"))


def largest_uncovered_gap(chapters: list[ChapterSummary], steps: list[TutorialStep], duration_seconds: float) -> float:
    anchors = [0.0, max(0.0, duration_seconds)]
    anchors.extend(float(item.start) for item in chapters if item.start is not None)
    anchors.extend(float(item.timestamp) for item in steps if item.timestamp is not None)
    anchors = sorted(set(round(value, 2) for value in anchors if 0 <= value <= max(duration_seconds, 0.0)))
    if len(anchors) < 2:
        return max(duration_seconds, 0.0)
    return max(b - a for a, b in zip(anchors, anchors[1:]))


def _bucket(duration: float) -> tuple[str, tuple[int, int], tuple[int, int], int]:
    if duration <= 600:
        return "under_10m", (3, 5), (2, 5), 180
    if duration <= 1_800:
        return "10m_to_30m", (5, 9), (4, 8), 360
    if duration <= 3_600:
        return "30m_to_60m", (8, 14), (6, 12), 600
    return "60m_plus", (12, 20), (10, 18), 900


def _dedupe_chapters(items: list[ChapterSummary]) -> list[ChapterSummary]:
    result: list[ChapterSummary] = []
    for item in sorted(items, key=lambda value: value.start):
        if not item.summary.strip() and not item.title.strip():
            continue
        duplicate = next((existing for existing in result if abs(existing.start - item.start) < 45 and _similar(existing.title, item.title)), None)
        if duplicate:
            duplicate.end = max(duplicate.end, item.end)
            if len(item.summary) > len(duplicate.summary):
                duplicate.summary = item.summary
            continue
        result.append(item.model_copy())
    return result


def _dedupe_highlights(items: list[HighlightItem]) -> list[HighlightItem]:
    result: list[HighlightItem] = []
    for item in sorted(items, key=lambda value: value.timestamp if value.timestamp is not None else value.start or 0):
        timestamp = item.timestamp if item.timestamp is not None else item.start
        if not item.title.strip() or not (item.summary or item.explanation).strip():
            continue
        duplicate = next((existing for existing in result if timestamp is not None and existing.timestamp is not None and abs(existing.timestamp - timestamp) < 30 and _similar(existing.title, item.title)), None)
        if not duplicate:
            result.append(item.model_copy(update={"image": "" if item.image and item.image.startswith("assets/highlights/") else item.image}))
    return result


def _dedupe_steps(items: list[TutorialStep]) -> list[TutorialStep]:
    result: list[TutorialStep] = []
    for item in sorted(items, key=lambda value: value.timestamp if value.timestamp is not None else 0):
        if not item.title.strip() or not (item.action or item.description).strip():
            continue
        duplicate = next((existing for existing in result if item.timestamp is not None and existing.timestamp is not None and abs(existing.timestamp - item.timestamp) < 30 and _similar(existing.title, item.title)), None)
        if not duplicate:
            result.append(item.model_copy())
    return result


def _dedupe_thoughts(items: list[ThoughtQuestion]) -> list[ThoughtQuestion]:
    result: list[ThoughtQuestion] = []
    for item in items:
        if not item.question.strip():
            continue
        if any(_similar(existing.question, item.question) for existing in result):
            continue
        result.append(item.model_copy())
    return result


def _dedupe_professional_terms(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        term = str(item.get("term") or "").strip()
        definition = str(item.get("definition") or "").strip()
        identity = "".join(term.lower().split())
        if not identity or not definition or identity in seen:
            continue
        seen.add(identity)
        result.append({"term": term, "definition": definition})
        if len(result) == 8:
            break
    return result


def _assign_chapter_ids(chapters: list[ChapterSummary], highlights: list[HighlightItem], steps: list[TutorialStep]) -> None:
    for index, chapter in enumerate(chapters, 1):
        if not chapter.id:
            chapter.id = f"ch{index:03d}"
    for index, item in enumerate(highlights, 1):
        if not item.id:
            item.id = f"hl{index:03d}"
        if not item.chapter_id:
            timestamp = item.timestamp if item.timestamp is not None else item.start
            item.chapter_id = _chapter_for_timestamp(chapters, timestamp)
    for index, item in enumerate(steps, 1):
        if not item.id:
            item.id = f"st{index:03d}"
        if not item.chapter_id:
            item.chapter_id = _chapter_for_timestamp(chapters, item.timestamp)
    if chapters:
        for chapter in chapters:
            chapter.children = [
                {"type": "tutorial_step", "id": item.id, "timestamp": item.timestamp, "title": item.title}
                for item in steps
                if item.chapter_id == chapter.id
            ]


def _chapter_for_timestamp(chapters: list[ChapterSummary], timestamp: float | None) -> str:
    if timestamp is None:
        return ""
    for chapter in chapters:
        if chapter.start <= timestamp <= chapter.end:
            return chapter.id
    earlier = [chapter for chapter in chapters if chapter.start <= timestamp]
    return earlier[-1].id if earlier else (chapters[0].id if chapters else "")


def _merge_usage(usages: list[dict[str, int]]) -> dict[str, int]:
    merged: dict[str, int] = {}
    for usage in usages:
        for key, value in usage.items():
            merged[key] = merged.get(key, 0) + int(value or 0)
    return merged


def _unique_texts(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = value.strip()
        if text and text not in result:
            result.append(text)
    return result


def _similar(a: str, b: str) -> bool:
    left = "".join(str(a or "").lower().split())
    right = "".join(str(b or "").lower().split())
    return bool(left and right and (left in right or right in left))
