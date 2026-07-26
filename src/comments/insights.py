from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..domain.models import CommentInsight, NormalizedComment
from ..providers.llm.base import LLMProvider
from ..utils import save_json, write_text


class CommentInsightService:
    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.provider = provider

    def analyze(self, comments: list[NormalizedComment]) -> CommentInsight:
        if not comments:
            return CommentInsight(status="skipped", error="没有可分析的评论。")
        if not self.provider or not self.provider.is_available():
            return _heuristic_insight(comments)
        prompt = _build_prompt(comments)
        try:
            response = self.provider.complete(
                [
                    {
                        "role": "system",
                        "content": (
                            "你只分析给定评论，不要编造评论、作者身份、平台反馈或视频事实。"
                            "输出 JSON，字段为 hot_topics, consensus, controversies, corrections, "
                            "frequent_questions, recommended_segments, needs_verification。"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                json_mode=True,
                temperature=0.2,
                max_tokens=1_200,
            )
            payload = _parse_json_object(response.content)
            return CommentInsight(
                status="success",
                provider=response.provider,
                model=response.model,
                hot_topics=_list(payload.get("hot_topics")),
                consensus=_list(payload.get("consensus")),
                controversies=_list(payload.get("controversies")),
                corrections=_list(payload.get("corrections")),
                frequent_questions=_list(payload.get("frequent_questions")),
                recommended_segments=_segments(payload.get("recommended_segments")),
                needs_verification=_list(payload.get("needs_verification")),
            )
        except Exception as exc:
            fallback = _heuristic_insight(comments)
            fallback.status = "failed"
            fallback.provider = getattr(self.provider, "name", "")
            fallback.model = getattr(self.provider, "model_name", "")
            fallback.error = str(exc)
            return fallback

    @staticmethod
    def save(package_dir: Path, insight: CommentInsight) -> tuple[Path, Path]:
        json_path = package_dir / "comment_insights.json"
        md_path = package_dir / "comment_insights.md"
        save_json(json_path, insight.model_dump(mode="json"))
        write_text(md_path, render_comment_insight_markdown(insight))
        return json_path, md_path


def render_comment_insight_markdown(insight: CommentInsight) -> str:
    lines = ["# 评论区洞察", "", f"状态：{insight.status}", ""]
    if insight.error:
        lines.extend([f"说明：{insight.error}", ""])
    for title, values in (
        ("热门话题", insight.hot_topics),
        ("共识", insight.consensus),
        ("争议", insight.controversies),
        ("纠错与补充", insight.corrections),
        ("高频问题", insight.frequent_questions),
        ("需要核查", insight.needs_verification),
    ):
        lines.extend([f"## {title}", ""])
        lines.extend([f"- {value}" for value in values] or ["评论区未明确体现。"])
        lines.append("")
    if insight.recommended_segments:
        lines.extend(["## 推荐关注片段", ""])
        for item in insight.recommended_segments:
            timestamp = item.get("timestamp")
            reason = item.get("reason") or "评论提及较多"
            lines.append(f"- {timestamp}s：{reason}" if timestamp is not None else f"- {reason}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _heuristic_insight(comments: list[NormalizedComment]) -> CommentInsight:
    top = sorted(comments, key=lambda item: (item.likes, item.reply_count), reverse=True)[:5]
    questions = [item.content for item in comments if "?" in item.content or "？" in item.content][:5]
    segments = [
        {"timestamp": item.timestamps[0], "reason": item.content[:80]}
        for item in comments
        if item.timestamps
    ][:5]
    return CommentInsight(
        status="success",
        provider="local",
        model="heuristic",
        hot_topics=[item.content[:120] for item in top],
        frequent_questions=questions,
        recommended_segments=segments,
        needs_verification=["评论区观点未经过事实核查，不能写入主摘要。"],
    )


def _build_prompt(comments: list[NormalizedComment]) -> str:
    items = [
        {
            "author": item.author,
            "content": item.content,
            "likes": item.likes,
            "reply_count": item.reply_count,
            "timestamps": item.timestamps,
        }
        for item in comments[:80]
    ]
    return "请分析以下评论区样本，输出严格 JSON：\n" + json.dumps(items, ensure_ascii=False)


def _parse_json_object(value: str) -> dict[str, Any]:
    text = value.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    parsed = json.loads(text)
    return parsed if isinstance(parsed, dict) else {}


def _list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:10]


def _segments(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if not isinstance(item, dict):
            continue
        result.append({"timestamp": item.get("timestamp"), "reason": str(item.get("reason") or "").strip()})
    return result[:10]
