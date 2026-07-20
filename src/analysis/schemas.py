from __future__ import annotations

import json
import re

from ..domain.models import AnalysisResult
from ..utils import UserFacingError
from .entities import normalize_analysis_entities


def parse_analysis_response(
    raw_response: str,
    profile: str,
    provider: str,
    model: str,
    *,
    usage: dict[str, int] | None = None,
    max_duration: float | None = None,
) -> AnalysisResult:
    cleaned = _strip_code_fence(raw_response)
    try:
        payload = json.loads(cleaned)
        if not isinstance(payload, dict):
            raise ValueError("顶层必须是 JSON 对象")
        payload = _normalize_analysis_payload(payload)
        payload.update(
            {
                "status": "success",
                "error": "",
                "raw_response": raw_response,
                "analysis_profile": profile,
                "provider": provider,
                "model": model,
                "usage": usage or {},
            }
        )
        result = AnalysisResult.model_validate(payload)
        _validate_meaningful_content(result)
        _validate_timestamps(result, max_duration)
        return normalize_analysis_entities(result)
    except (json.JSONDecodeError, ValueError) as exc:
        result = AnalysisResult(
            status="failed",
            error="模型输出不是合法的结构化 JSON。",
            raw_response=raw_response,
            analysis_profile=profile,
            provider=provider,
            model=model,
            usage=usage or {},
        )
        raise AnalysisParseError(f"模型输出不是合法的结构化 JSON：{exc}", result) from exc


class AnalysisParseError(UserFacingError):
    def __init__(self, message: str, partial_result: AnalysisResult) -> None:
        super().__init__(message)
        self.partial_result = partial_result


def _strip_code_fence(value: str) -> str:
    text = value.strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.S | re.I)
    return match.group(1).strip() if match else text


def _normalize_analysis_payload(payload: dict) -> dict:
    normalized = dict(payload)

    terminology = normalized.get("terminology")
    if isinstance(terminology, list):
        normalized["terminology"] = [
            item if isinstance(item, dict) else {"term": str(item)}
            for item in terminology
            if isinstance(item, dict) or str(item).strip()
        ]

    actions = normalized.get("actions")
    if isinstance(actions, list):
        normalized["actions"] = [text for item in actions if (text := _normalize_action(item))]

    if "glossary" not in normalized and isinstance(normalized.get("terminology"), list):
        normalized["glossary"] = [
            {"term": str(item.get("term") or item.get("name") or ""), "definition": str(item.get("definition") or item.get("description") or "")}
            for item in normalized["terminology"] if isinstance(item, dict) and (item.get("term") or item.get("name"))
        ]
    if "action_items" not in normalized and isinstance(normalized.get("actions"), list):
        normalized["action_items"] = [{"text": str(item), "timestamp": None} for item in normalized["actions"] if str(item).strip()]

    return normalized


def _normalize_action(item: object) -> str:
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        return str(item).strip()

    title = item.get("action") or item.get("title") or item.get("text")
    detail = item.get("description") or item.get("reason")
    if title and detail:
        return f"{title}：{detail}"
    return str(title or detail or "").strip()


def _validate_timestamps(result: AnalysisResult, max_duration: float | None) -> None:
    limit = float(max_duration or 0)
    values: list[tuple[str, float | None]] = []
    for index, item in enumerate(result.highlights):
        values.extend([(f"highlights[{index}].start", item.start), (f"highlights[{index}].end", item.end)])
        if item.start is not None and item.end is not None and item.end < item.start:
            raise ValueError(f"highlights[{index}] 的结束时间早于开始时间")
    for index, item in enumerate(result.thoughts):
        values.append((f"thoughts[{index}].start", item.start))
    for index, item in enumerate(result.chapters):
        values.extend([(f"chapters[{index}].start", item.start), (f"chapters[{index}].end", item.end)])
        if item.end < item.start:
            raise ValueError(f"chapters[{index}] 的结束时间早于开始时间")
    for collection_name in ("action_items", "prerequisites", "steps", "warnings"):
        for index, item in enumerate(getattr(result, collection_name)):
            values.append((f"{collection_name}[{index}].timestamp", item.timestamp))
    for field, value in values:
        if value is None:
            continue
        if value < 0 or (limit > 0 and value > limit):
            raise ValueError(f"{field} 超出字幕时间范围")


def _validate_meaningful_content(result: AnalysisResult) -> None:
    if not any(
        (
            result.one_sentence_summary.strip(),
            result.summary.strip(),
            result.highlights,
            result.thoughts,
            result.chapters,
            result.terminology,
            result.actions,
            result.glossary,
            result.action_items,
            result.prerequisites,
            result.steps,
            result.warnings,
        )
    ):
        raise ValueError("结构化分析没有包含任何有效内容")
