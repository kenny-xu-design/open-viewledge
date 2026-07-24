from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from ..domain.models import KnowledgePackage
from ..timestamps import build_timestamp_target, format_timestamp
from .models import ExportSelection


def render_knowledge_markdown(
    package: KnowledgePackage,
    selection: ExportSelection,
    *,
    chat: dict[str, Any] | None = None,
    user_notes: str = "",
    highlight_image_prefix: str = "",
) -> str:
    source, analysis = package.source, package.analysis
    profile = (analysis.analysis_profile if analysis else source.analysis_profile) or "summary"
    sections = set(selection.normalized_sections())
    lines = ["---"]
    frontmatter = {
        "title": source.title,
        "source": source.canonical_url or source.source_url,
        "platform": source.platform,
        "author": source.author,
        "knowledge_id": selection.knowledge_id,
        "analysis_profile": profile,
        "created": date.today().isoformat(),
        "type": "video-note",
        "status": "processed",
    }
    for key, value in frontmatter.items():
        lines.append(f"{key}: {json.dumps(str(value or ''), ensure_ascii=False)}")
    lines.extend(["tags:", "  - 外源/视频", "  - AI摘要", f"  - {_clean_tag(profile)}", "---", "", f"# {source.title or selection.knowledge_id}", ""])

    for section in selection.normalized_sections():
        if section == "metadata":
            _metadata(lines, package, profile)
        elif section == "summary" and analysis and analysis.summary.strip():
            lines.extend(["## 摘要", "", analysis.summary.strip(), ""])
        elif section == "highlights" and analysis and analysis.highlights:
            lines.extend(["## 亮点", ""])
            for item in analysis.highlights:
                timestamp = item.timestamp if item.timestamp is not None else item.start
                summary = item.summary or item.explanation
                target = _time_link(package, selection.knowledge_id, timestamp)
                time = f" [{format_timestamp(timestamp)}]({target})" if target else (f" {format_timestamp(timestamp)}" if timestamp is not None else "")
                lines.append(f"- **{item.title}**：{summary}{time}")
                if item.image:
                    image_path = (
                        f"{highlight_image_prefix.rstrip('/')}/{Path(item.image).name}"
                        if highlight_image_prefix
                        else item.image
                    )
                    lines.append(f"  ![[{image_path}]]")
                tags = [f"`#{_clean_tag(tag)}`" for tag in item.tags if _clean_tag(tag)]
                if tags:
                    lines.append("  " + " ".join(tags))
                lines.append("")
        elif section == "prerequisites" and analysis and analysis.prerequisites:
            _timed_items(lines, "前置条件", analysis.prerequisites, package, selection.knowledge_id)
        elif section == "steps" and analysis and analysis.steps:
            lines.extend(["## 操作步骤", ""])
            for index, item in enumerate(analysis.steps, 1):
                lines.extend([f"### {index}. {item.title}", "", item.description.strip(), ""])
                target = _time_link(package, selection.knowledge_id, item.timestamp)
                if item.timestamp is not None:
                    label = format_timestamp(item.timestamp)
                    lines.append(f"- 时间：[{label}]({target})" if target else f"- 时间：{label}")
                if item.expected_result.strip():
                    lines.append(f"- 预期结果：{item.expected_result.strip()}")
                lines.append("")
        elif section == "glossary" and analysis and analysis.glossary:
            lines.extend(["## 关键术语", ""])
            lines.extend(f"- **{item.term}**：{item.definition or '视频中未展开说明'}" for item in analysis.glossary)
            lines.append("")
        elif section == "thoughts" and analysis and analysis.thoughts:
            lines.extend(["## 思考", ""] + [f"{i}. {item.question}" for i, item in enumerate(analysis.thoughts, 1)] + [""])
        elif section == "action_items" and analysis and analysis.action_items:
            _timed_items(lines, "可执行动作", analysis.action_items, package, selection.knowledge_id, checkbox=True)
        elif section == "warnings" and analysis and analysis.warnings:
            _timed_items(lines, "注意事项", analysis.warnings, package, selection.knowledge_id)
        elif section == "chapters" and ((analysis and analysis.chapters) or package.timeline):
            lines.extend(["## 视频章节总结", ""])
            chapters = analysis.chapters if analysis and analysis.chapters else package.timeline
            for item in chapters:
                target = _time_link(package, selection.knowledge_id, item.start)
                label = format_timestamp(item.start)
                lines.append(f"### [{label}]({target}) {item.title}" if target else f"### {label} {item.title}")
                summary = getattr(item, "summary", "")
                frame_path = getattr(item, "frame_path", "")
                if frame_path:
                    lines.extend(["", f"![[{frame_path}]]"])
                if summary:
                    lines.extend(["", summary.strip()])
                lines.append("")
        elif section == "chat":
            _chat(lines, chat or {}, package, selection.knowledge_id)
        elif section == "user_notes" and user_notes.strip():
            lines.extend(["## 我的笔记", "", user_notes.strip(), ""])
        elif section == "source_materials":
            lines.extend(["## 原文资料", "", "- [分组字幕](transcript.grouped.md)", "- `transcript.raw.jsonl`", "- `timeline.json`", ""])
    return "\n".join(lines).rstrip() + "\n"


def _metadata(lines: list[str], package: KnowledgePackage, profile: str) -> None:
    source = package.source
    lines.extend(["> [!info] 视频来源", f"> - 平台：{source.platform or '未知'}", f"> - 作者：{source.author or '未知'}"])
    if source.canonical_url or source.source_url:
        lines.append(f"> - 原视频：[打开视频]({source.canonical_url or source.source_url})")
    lines.extend([f"> - 分析类型：{profile}", ""])


def _timed_items(lines: list[str], heading: str, items: list[Any], package: KnowledgePackage, knowledge_id: str, checkbox: bool = False) -> None:
    lines.extend([f"## {heading}", ""])
    for item in items:
        prefix = "- [ ]" if checkbox else "-"
        target = _time_link(package, knowledge_id, item.timestamp)
        suffix = ""
        if item.timestamp is not None:
            label = format_timestamp(item.timestamp)
            suffix = f"（[{label}]({target})）" if target else f"（{label}）"
        lines.append(f"{prefix} {item.text}{suffix}")
    lines.append("")


def _chat(lines: list[str], payload: dict[str, Any], package: KnowledgePackage, knowledge_id: str) -> None:
    messages = [item for item in payload.get("messages", []) if isinstance(item, dict) and item.get("role") in {"user", "assistant"} and str(item.get("content") or "").strip()]
    if not messages:
        return
    lines.extend(["## AI 对话记录", ""])
    question = 0
    for item in messages:
        if item["role"] == "user":
            question += 1
            lines.extend([f"### 问题 {question}", "", "> [!question] 用户", "> " + str(item["content"]).replace("\n", "\n> "), ""])
        else:
            lines.extend(["> [!answer] AI", "> " + str(item["content"]).replace("\n", "\n> "), ""])
            citations = [value for value in item.get("citations", []) if isinstance(value, dict)]
            if citations:
                lines.extend(["#### 引用", ""])
                for citation in citations:
                    seconds = citation.get("start")
                    target = _time_link(package, knowledge_id, seconds)
                    label = format_timestamp(seconds)
                    excerpt = str(citation.get("excerpt") or citation.get("title") or "字幕引用")
                    lines.append(f"- [{label}]({target})：{excerpt}" if target else f"- {label}：{excerpt}")
                lines.append("")


def _time_link(package: KnowledgePackage, knowledge_id: str, seconds: float | int | None) -> str:
    return build_timestamp_target(package.source, seconds, knowledge_id=knowledge_id)


def _clean_tag(value: object) -> str:
    return re.sub(r"[\s`#\[\]{}]+", "-", str(value or "").strip()).strip("-")[:64]
