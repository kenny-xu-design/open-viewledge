from __future__ import annotations

import re

from ..domain.models import AnalysisResult


CANONICAL_ENTITIES = {
    r"Cursor（Corex）": "Cursor",
    r"(?i)\bagents?\.md\b": "AGENTS.md",
    r"(?i)\bdeepseek\b": "DeepSeek",
    r"(?i)\bgemini\b": "Gemini",
    r"(?i)\bobsidian\b": "Obsidian",
    r"(?i)\bworktree\b": "Worktree",
    r"(?i)\bworkflow\b": "Workflow",
    r"(?i)\bskill\b": "Skill",
}


def normalize_entities_text(value: str) -> str:
    result = str(value or "")
    for pattern, replacement in CANONICAL_ENTITIES.items():
        result = re.sub(pattern, replacement, result)
    return result


def normalize_analysis_entities(result: AnalysisResult) -> AnalysisResult:
    payload = result.model_dump()
    for key in ("one_sentence_summary", "summary"):
        payload[key] = normalize_entities_text(payload.get(key, ""))
    for key in ("highlights", "thoughts", "chapters", "glossary", "action_items", "prerequisites", "steps", "warnings"):
        for item in payload.get(key, []):
            if not isinstance(item, dict):
                continue
            for field in ("title", "explanation", "question", "related_topic", "summary", "term", "definition", "text", "description", "expected_result"):
                if field in item:
                    item[field] = normalize_entities_text(item[field])
            if isinstance(item.get("tags"), list):
                item["tags"] = [normalize_entities_text(tag) for tag in item["tags"]]
    return AnalysisResult.model_validate(payload)
