from __future__ import annotations

from typing import Any

from ..domain.models import AnalysisResult
from ..timestamps import format_timestamp


SUMMARY_SECTIONS = [
    ("一句话", "one_sentence", "text"),
    ("摘要", "summary", "text"),
    ("专业术语", "professional_terms", "terms"),
    ("亮点", "highlights", "highlights"),
    ("思考", "thoughts", "thoughts"),
    ("章节总结", "chapter_summaries", "chapters"),
]

TUTORIAL_SECTIONS = [
    ("教程目标", "tutorial_goal", "text"),
    ("最终成果", "final_result", "text"),
    ("前置条件", "prerequisites", "list"),
    ("工具与材料", "tools_and_materials", "list"),
    ("流程总览", "workflow_overview", "text"),
    ("完整教程步骤", "steps", "steps"),
    ("关键参数与设置", "key_parameters", "list"),
    ("常见错误与排查", "troubleshooting", "list"),
    ("完成验收清单", "acceptance_checklist", "checklist"),
    ("可复用命令或模板", "reusable_commands_or_templates", "list"),
    ("教程局限", "limitations", "list"),
]

VIRAL_SECTIONS = [
    ("内容定位", "content_positioning", "text"),
    ("目标受众", "target_audience", "list"),
    ("标题与封面承诺", "title_and_cover_promise", "text"),
    ("前 30 秒钩子", "first_30_seconds_hook", "text"),
    ("内容结构", "content_structure", "list"),
    ("节奏与留存设计", "retention_design", "list"),
    ("情绪与叙事机制", "emotion_and_narrative", "list"),
    ("视觉包装与剪辑", "visual_packaging_and_editing", "list"),
    ("互动与传播设计", "interaction_and_distribution", "list"),
    ("可复用内容公式", "reusable_content_formula", "list"),
    ("可借鉴点", "takeaways", "list"),
    ("风险与局限", "risks_and_limitations", "list"),
]

CLOSE_READING_SECTIONS = [
    ("核心命题", "core_thesis", "text"),
    ("关键概念", "key_concepts", "list"),
    ("论证地图", "argument_map", "list"),
    ("证据评估", "evidence_assessment", "list"),
    ("隐含假设", "implicit_assumptions", "list"),
    ("可能的反方观点", "counterarguments", "list"),
    ("论证局限", "argument_limits", "list"),
    ("视觉证据", "visual_evidence", "list"),
    ("延伸联系", "extended_connections", "list"),
    ("待核查事实", "facts_to_verify", "list"),
]


def render_profile_analysis(analysis: AnalysisResult, *, heading_level: int = 2, image_prefix: str = "") -> list[str]:
    profile = analysis.analysis_profile or "summary"
    lines: list[str] = []
    if analysis.summary.strip():
        lines.extend([f"{'#' * heading_level} 摘要", "", analysis.summary.strip(), ""])
    terms = _summary_terms(analysis)
    if terms:
        lines.extend([f"{'#' * heading_level} 专业术语", "", *terms, ""])
    if profile != "summary":
        lines.extend(render_profile_details(analysis, heading_level=heading_level, image_prefix=image_prefix))
    if analysis.highlights:
        lines.extend([f"{'#' * heading_level} 亮点", ""])
        lines.extend(_highlights([item.model_dump(mode="json") for item in analysis.highlights]))
        lines.append("")
    if analysis.thoughts:
        lines.extend([f"{'#' * heading_level} 思考", ""])
        lines.extend(_thoughts([item.model_dump(mode="json") for item in analysis.thoughts]))
        lines.append("")
    if analysis.chapters:
        lines.extend([f"{'#' * heading_level} 视频章节总结", ""])
        lines.extend(_chapters([item.model_dump(mode="json") for item in analysis.chapters]))
        lines.append("")
    if not lines:
        if analysis.status == "timeout":
            message = f"AI 分析超时：{analysis.error or '请求超过时限。'}"
        elif analysis.status == "failed":
            message = f"AI 分析失败：{analysis.error or '未生成有效分析结果。'}"
        elif analysis.status == "skipped":
            message = "AI 分析未运行。"
        else:
            message = "AI 分析没有可显示的摘要。"
        lines.extend([f"{'#' * heading_level} 摘要", "", message, ""])
    return lines


def render_profile_details(
    analysis: AnalysisResult,
    *,
    heading_level: int = 2,
    image_prefix: str = "",
    exclude_keys: set[str] | None = None,
) -> list[str]:
    profile = analysis.analysis_profile or "summary"
    sections = {
        "tutorial": TUTORIAL_SECTIONS,
        "viral": VIRAL_SECTIONS,
        "close-reading": CLOSE_READING_SECTIONS,
    }.get(profile, [])
    content = analysis.content or {}
    lines: list[str] = []
    for title, key, kind in sections:
        if key in (exclude_keys or set()):
            continue
        value = content.get(key)
        rendered = _render_value(kind, value, allow_images=profile == "tutorial", image_prefix=image_prefix)
        if not rendered:
            continue
        lines.extend([f"{'#' * heading_level} {title}", "", *rendered, ""])
    _evidence(lines, content, heading_level)
    return lines


def _summary_terms(analysis: AnalysisResult) -> list[str]:
    terminology = [item for item in analysis.terminology if isinstance(item, dict)]
    if terminology:
        return _professional_terms(terminology)
    return _professional_terms([item.model_dump(mode="json") for item in analysis.glossary])


def _render_value(kind: str, value: object, *, allow_images: bool, image_prefix: str = "") -> list[str]:
    if kind == "text":
        text = _text(value)
        return [text] if text else []
    if kind == "list":
        return [f"- {item}" for item in _texts(value)]
    if kind == "checklist":
        return [f"- [ ] {item}" for item in _texts(value)]
    if kind == "chapters":
        return _chapters(value)
    if kind == "steps":
        return _steps(value, allow_images=allow_images, image_prefix=image_prefix)
    if kind == "highlights":
        return _highlights(value)
    if kind == "thoughts":
        return _thoughts(value)
    return []


def _professional_terms(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    rendered: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        term = _text(item.get("term"))
        definition = _text(item.get("definition"))
        identity = "".join(term.lower().split())
        if not identity or not definition or identity in seen:
            continue
        seen.add(identity)
        rendered.append(f"- **{term}**：{definition}")
        if len(rendered) == 8:
            break
    return rendered if len(rendered) >= 3 else []


def _highlights(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    lines: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            text = _text(item)
            if text:
                lines.append(f"- {text}")
            continue
        title = _text(item.get("title")) or "亮点"
        explanation = _text(item.get("explanation") or item.get("summary"))
        timestamp = item.get("timestamp") if item.get("timestamp") is not None else item.get("start")
        prefix = f"[{format_timestamp(timestamp)}] " if timestamp is not None else ""
        lines.append(f"- **{prefix}{title}**" + (f"：{explanation}" if explanation else ""))
    return lines


def _thoughts(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        text = _text(item.get("question")) if isinstance(item, dict) else _text(item)
        if text:
            result.append(f"- {text}")
    return result


def _chapters(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    lines: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            text = _text(item)
            if text:
                lines.append(f"- {text}")
            continue
        title = _text(item.get("title")) or "章节"
        summary = _text(item.get("summary"))
        start = item.get("start")
        prefix = f"[{format_timestamp(start)}] " if start is not None else ""
        lines.append(f"- **{prefix}{title}**" + (f"：{summary}" if summary else ""))
        children = item.get("children")
        if isinstance(children, list):
            for child in children:
                if not isinstance(child, dict):
                    continue
                child_title = _text(child.get("title"))
                child_time = child.get("timestamp")
                child_prefix = f"[{format_timestamp(child_time)}] " if child_time is not None else ""
                if child_title:
                    lines.append(f"  - {child_prefix}{child_title}")
    return lines


def _steps(value: object, *, allow_images: bool, image_prefix: str = "") -> list[str]:
    if not isinstance(value, list):
        return []
    lines: list[str] = []
    for index, item in enumerate(value, 1):
        if not isinstance(item, dict):
            continue
        title = _text(item.get("title")) or f"步骤 {index}"
        timestamp = item.get("timestamp")
        label = f"（{format_timestamp(timestamp)}）" if timestamp is not None else ""
        lines.extend([f"### {index}. {title}{label}", ""])
        for field, label_text in (
            ("objective", "目标"),
            ("action", "操作"),
            ("expected_result", "预期结果"),
        ):
            text = _text(item.get(field))
            if text:
                lines.append(f"- {label_text}：{text}")
        for field, label_text in (("parameters", "参数"), ("cautions", "注意")):
            values = _texts(item.get(field))
            if values:
                lines.append(f"- {label_text}：" + "；".join(values))
        image = _text(item.get("image")) if allow_images else ""
        if image:
            if image_prefix:
                image = f"{image_prefix.rstrip('/')}/{image.rsplit('/', 1)[-1]}"
            lines.extend(["", f"![[{image}]]"])
        lines.append("")
    return lines


def _evidence(lines: list[str], content: dict[str, Any], heading_level: int) -> None:
    factual_basis = _text(content.get("factual_basis"))
    ai_inferences = _texts(content.get("ai_inferences"))
    if factual_basis:
        lines.extend([f"{'#' * heading_level} 视频事实依据", "", factual_basis, ""])
    if ai_inferences:
        lines.extend([f"{'#' * heading_level} AI 推断", ""])
        lines.extend(f"- {item}" for item in ai_inferences)
        lines.append("")


def _texts(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
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
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("text", "summary", "description", "explanation", "title", "term", "question", "definition"):
            if key in value and str(value[key]).strip():
                return str(value[key]).strip()
        return ""
    return str(value).strip()
