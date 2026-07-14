from __future__ import annotations

import json
import re

from ..domain.models import AnalysisResult
from ..utils import UserFacingError


def parse_analysis_response(raw_response: str, profile: str, provider: str, model: str) -> AnalysisResult:
    cleaned = _strip_code_fence(raw_response)
    try:
        payload = json.loads(cleaned)
        if not isinstance(payload, dict):
            raise ValueError("顶层必须是 JSON 对象")
        payload = _normalize_analysis_payload(payload)
        payload.update({"raw_response": raw_response, "analysis_profile": profile, "provider": provider, "model": model})
        return AnalysisResult.model_validate(payload)
    except (json.JSONDecodeError, ValueError) as exc:
        result = AnalysisResult(raw_response=raw_response, analysis_profile=profile, provider=provider, model=model)
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
