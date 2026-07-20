from __future__ import annotations

import json

from ..domain.models import AnalysisResult, TranscriptGroup
from ..utils import UserFacingError
from .profiles import get_profile
from .schemas import AnalysisParseError, parse_analysis_response


class AnalysisService:
    def __init__(self, provider: object) -> None:
        self.provider = provider

    def analyze(self, groups: list[TranscriptGroup], profile_name: str, context: object) -> AnalysisResult:
        profile = get_profile(profile_name)
        source = getattr(context, "source", None)
        source_url = str(getattr(source, "canonical_url", "") or getattr(source, "source_url", "") or "")
        request = _build_request(groups, profile.instruction, source_url)
        messages = [
            {
                "role": "system",
                "content": "你是视频内容分析助手。只基于提供的字幕，严格返回一个 JSON 对象，不得编造。",
            },
            {"role": "user", "content": request},
        ]
        response = self.provider.complete(messages, json_mode=True, temperature=0.2, max_tokens=4096)
        max_duration = max((item.end for item in groups), default=0.0)
        try:
            return parse_analysis_response(
                response.content,
                profile.name,
                response.provider,
                response.model,
                usage=response.usage,
                max_duration=max_duration,
            )
        except AnalysisParseError as first_error:
            repair_messages = messages + [
                {"role": "assistant", "content": response.content},
                {
                    "role": "user",
                    "content": f"上一个 JSON 未通过校验：{first_error}。请修复并只返回完整 JSON 对象。",
                },
            ]
            repaired = self.provider.complete(repair_messages, json_mode=True, temperature=0.0, max_tokens=4096)
            try:
                return parse_analysis_response(
                    repaired.content,
                    profile.name,
                    repaired.provider,
                    repaired.model,
                    usage=repaired.usage,
                    max_duration=max_duration,
                )
            except AnalysisParseError as exc:
                failed = exc.partial_result.model_copy(
                    update={
                        "status": "failed",
                        "error": "DeepSeek 返回结果未通过结构化校验。",
                        "raw_response": "",
                    }
                )
                setattr(context, "analysis", failed)
                raise UserFacingError(str(exc)) from exc


def _build_request(groups: list[TranscriptGroup], instruction: str, source_url: str = "") -> str:
    source = [{"index": item.index, "start": item.start, "end": item.end, "title": item.title, "text": item.text} for item in groups]
    schema = {
        "one_sentence_summary": "一句话结论",
        "summary": "Markdown 摘要",
        "highlights": [{"title": "亮点", "explanation": "说明", "tags": ["标签"], "start": 0, "end": 0}],
        "thoughts": [{"question": "思考问题", "related_topic": "主题", "start": 0}],
        "chapters": [{"title": "章节", "start": 0, "end": 0, "summary": "总结", "source_link": ""}],
        "terminology": [],
        "actions": [],
        "glossary": [{"term": "术语", "definition": "视频语境中的简短解释"}],
        "action_items": [{"text": "可执行动作", "timestamp": 0}],
        "prerequisites": [{"text": "明确前置条件", "timestamp": 0}],
        "steps": [{"title": "操作步骤", "description": "操作说明", "timestamp": 0, "expected_result": "预期结果"}],
        "warnings": [{"text": "视频明确说明的注意事项", "timestamp": 0}],
    }
    return (
        f"分析要求：{instruction}\n"
        "只使用下方字幕内容，不得补充不存在的信息。只返回一个 JSON 对象，不要使用 Markdown code fence。\n"
        f"JSON 结构：{json.dumps(schema, ensure_ascii=False)}\n\n"
        f"来源链接：{source_url or '本地媒体'}\n\n"
        f"字幕分组：{json.dumps(source, ensure_ascii=False)}"
    )
