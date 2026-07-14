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
        request = _build_request(groups, profile.instruction)
        raw = self.provider.generate(request, context)
        try:
            return parse_analysis_response(raw, profile.name, self.provider.name, self.provider.model_name)
        except AnalysisParseError as exc:
            setattr(context, "analysis", exc.partial_result)
            raise UserFacingError(str(exc)) from exc


def _build_request(groups: list[TranscriptGroup], instruction: str) -> str:
    source = [{"index": item.index, "start": item.start, "end": item.end, "title": item.title, "text": item.text} for item in groups]
    schema = {
        "one_sentence_summary": "一句话结论",
        "summary": "Markdown 摘要",
        "highlights": [{"title": "亮点", "explanation": "说明", "tags": ["标签"], "start": 0, "end": 0}],
        "thoughts": [{"question": "思考问题", "related_topic": "主题", "start": 0}],
        "chapters": [{"title": "章节", "start": 0, "end": 0, "summary": "总结", "source_link": ""}],
        "terminology": [],
        "actions": [],
    }
    return (
        f"分析要求：{instruction}\n"
        "只使用下方字幕内容，不得补充不存在的信息。只返回一个 JSON 对象，不要使用 Markdown code fence。\n"
        f"JSON 结构：{json.dumps(schema, ensure_ascii=False)}\n\n"
        f"字幕分组：{json.dumps(source, ensure_ascii=False)}"
    )

