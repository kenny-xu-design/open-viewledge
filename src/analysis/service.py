from __future__ import annotations

import json

from ..domain.models import AnalysisResult, TranscriptGroup
from ..utils import UserFacingError
from .profiles import get_profile
from .schemas import AnalysisParseError, parse_analysis_response
from .segmentation import AnalysisWindow, attach_segmentation, build_analysis_windows, reduce_window_results, route_segmentation_policy


_STRUCTURED_ANALYSIS_MAX_TOKENS = 8192


class AnalysisService:
    def __init__(self, provider: object) -> None:
        self.provider = provider

    def analyze(self, groups: list[TranscriptGroup], profile_name: str, context: object) -> AnalysisResult:
        profile = get_profile(profile_name)
        source = getattr(context, "source", None)
        source_url = str(getattr(source, "canonical_url", "") or getattr(source, "source_url", "") or "")
        processing_profile = str(getattr(context, "processing_profile", "complete") or "complete")
        source_payload = _source_payload(source)
        policy = route_segmentation_policy(
            groups,
            analysis_profile=profile.name,
            processing_profile=processing_profile,
            native_chapter_count=len(getattr(source, "chapters", []) or []),
            source_duration=getattr(source, "duration", None),
            visual_available=False,
        )
        windows = build_analysis_windows(groups, policy)
        if policy.use_window_analysis and len(windows) > 1:
            results = [self._analyze_window(window, windows, profile.name, profile.instruction, source_url, processing_profile, source_payload, policy, context) for window in windows]
            return reduce_window_results(results, policy, groups)
        result = self._analyze_window(windows[0], windows, profile.name, profile.instruction, source_url, processing_profile, source_payload, policy, context)
        return attach_segmentation(result, policy, groups)

    def _analyze_window(
        self,
        window: AnalysisWindow,
        windows: list[AnalysisWindow],
        profile_name: str,
        instruction: str,
        source_url: str,
        processing_profile: str,
        source_payload: dict,
        policy: object,
        context: object,
    ) -> AnalysisResult:
        request = _build_request(
            window.groups,
            profile_name,
            instruction,
            source_url,
            processing_profile,
            policy=policy,
            window=window,
            total_windows=len(windows),
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "你是视频内容分析助手。只基于提供的字幕，严格返回一个完整、可解析且尽量紧凑的 JSON 对象；"
                    "不要输出思考过程、Markdown code fence 或任何 JSON 之外的文本，不得编造。"
                ),
            },
            {"role": "user", "content": request},
        ]
        response = self.provider.complete(
            messages,
            json_mode=True,
            temperature=0.2,
            max_tokens=_STRUCTURED_ANALYSIS_MAX_TOKENS,
        )
        max_duration = max((item.end for item in window.groups), default=0.0)
        try:
            return parse_analysis_response(
                response.content,
                profile_name,
                response.provider,
                response.model,
                usage=response.usage,
                max_duration=max_duration,
                processing_profile=processing_profile,
                source=source_payload,
                coerce_timestamps=True,
            )
        except AnalysisParseError as first_error:
            repair_reason = (
                "上一个 JSON 在生成时达到输出上限，内容可能被截断。"
                if response.finish_reason == "length"
                else f"上一个 JSON 未通过校验：{first_error}。"
            )
            repair_messages = messages + [
                {"role": "assistant", "content": response.content},
                {
                    "role": "user",
                    "content": (
                        f"{repair_reason}请忽略上一次不完整内容，从头重新生成一个完整、可解析且尽量紧凑的 JSON 对象。"
                        "只返回 JSON，不要输出 Markdown、解释或思考过程。"
                    ),
                },
            ]
            repaired = self.provider.complete(
                repair_messages,
                json_mode=True,
                temperature=0.0,
                max_tokens=_STRUCTURED_ANALYSIS_MAX_TOKENS,
            )
            try:
                return parse_analysis_response(
                    repaired.content,
                    profile_name,
                    repaired.provider,
                    repaired.model,
                    usage=repaired.usage,
                    max_duration=max_duration,
                    processing_profile=processing_profile,
                    source=source_payload,
                    coerce_timestamps=True,
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


def _build_request(
    groups: list[TranscriptGroup],
    profile: str,
    instruction: str,
    source_url: str = "",
    processing_profile: str = "complete",
    *,
    policy: object | None = None,
    window: AnalysisWindow | None = None,
    total_windows: int = 1,
) -> str:
    source = [{"index": item.index, "start": item.start, "end": item.end, "title": item.title, "text": item.text} for item in groups]
    schema = _schema_for_profile(profile)
    policy_payload = _policy_payload(policy, window, total_windows)
    profile_rules = _profile_rules(profile)
    return (
        f"分析要求：{instruction}\n"
        "只使用下方字幕内容和已明确给出的来源信息，不得补充不存在的信息；没有依据的可选字段返回空字符串或空数组。\n"
        "必须区分视频事实与 AI 推断；不得把评论区、弹幕、外部热评或观众意见写入主报告。\n"
        "不得输出 API Key、Cookie、Token、Authorization 或任何凭据。只返回一个 JSON 对象，不要使用 Markdown code fence。\n"
        f"共同外壳固定字段：schema_version='2'，analysis_profile='{profile}'，processing_profile='{processing_profile}'，"
        "generation.visual_context_used=false，generation.comments_included=false，warnings 为注意事项数组。\n"
        f"分段策略：{json.dumps(policy_payload, ensure_ascii=False)}\n"
        "若这是局部窗口分析，只输出当前窗口内有真实字幕支撑的候选；时间戳必须使用全视频绝对时间。\n"
        "不得为了满足数量范围制造节点；相邻窗口重叠内容不要重复输出。\n"
        f"{profile_rules}\n"
        f"JSON 结构：{json.dumps(schema, ensure_ascii=False)}\n\n"
        f"来源链接：{source_url or '本地媒体'}\n\n"
        f"字幕分组：{json.dumps(source, ensure_ascii=False)}"
    )


def _schema_for_profile(profile: str) -> dict:
    common = {
        "schema_version": "2",
        "analysis_profile": profile,
        "processing_profile": "fast 或 complete",
        "source": {"platform": "平台", "url": "来源链接", "title": "标题"},
        "generation": {"visual_context_used": False, "comments_included": False},
        "warnings": [{"text": "视频明确说明的注意事项；没有则返回空数组", "timestamp": 0}],
    }
    legacy_base = {
        **common,
        "one_sentence_summary": "一句话结论",
        "summary": "自然段摘要",
        "terminology": [{"term": "专业术语", "definition": "视频语境中的简短解释"}],
        "highlights": [{"title": "亮点", "explanation": "说明", "tags": ["标签"], "start": 0, "end": 0}],
        "thoughts": [{"question": "思考问题", "related_topic": "主题", "start": 0}],
        "chapters": [{"title": "章节", "start": 0, "end": 0, "summary": "总结", "source_link": ""}],
    }
    schemas = {
        "summary": {
            **legacy_base,
            "actions": [],
            "glossary": [{"term": "术语", "definition": "视频语境中的简短解释"}],
            "action_items": [{"text": "可执行动作", "timestamp": 0}],
            "prerequisites": [{"text": "明确前置条件", "timestamp": 0}],
            "steps": [{"title": "操作步骤", "description": "操作说明", "timestamp": 0, "expected_result": "预期结果"}],
        },
        "tutorial": {
            **legacy_base,
            "content": {
                "tutorial_goal": "教程目标",
                "final_result": "最终成果",
                "prerequisites": ["前置条件"],
                "tools_and_materials": ["工具与材料"],
                "workflow_overview": "流程总览",
                "steps": [{
                    "timestamp": 0,
                    "chapter_id": "ch001",
                    "title": "步骤标题",
                    "objective": "步骤目标",
                    "action": "具体操作",
                    "parameters": ["关键参数"],
                    "expected_result": "预期结果",
                    "cautions": ["注意事项"],
                    "image": "",
                }],
                "key_parameters": ["关键参数与设置"],
                "troubleshooting": ["常见错误与排查"],
                "acceptance_checklist": ["完成验收清单"],
                "reusable_commands_or_templates": ["可复用命令或模板"],
                "limitations": ["教程局限"],
                "factual_basis": "视频事实依据",
                "ai_inferences": ["AI 推断；没有则留空数组"],
            },
        },
        "viral": {
            **legacy_base,
            "content": {
                "content_positioning": "内容定位",
                "target_audience": ["目标受众"],
                "title_and_cover_promise": "标题与封面承诺",
                "first_30_seconds_hook": "前 30 秒钩子",
                "content_structure": ["内容结构"],
                "retention_design": ["节奏与留存设计"],
                "emotion_and_narrative": ["情绪与叙事机制"],
                "visual_packaging_and_editing": ["视觉包装与剪辑"],
                "interaction_and_distribution": ["互动与传播设计"],
                "reusable_content_formula": ["可复用内容公式"],
                "takeaways": ["可借鉴点"],
                "risks_and_limitations": ["风险与局限"],
                "factual_basis": "视频事实依据",
                "ai_inferences": ["AI 推断；没有则留空数组"],
            },
        },
        "close-reading": {
            **legacy_base,
            "content": {
                "core_thesis": "核心命题",
                "key_concepts": ["关键概念"],
                "argument_map": ["论证地图"],
                "evidence_assessment": ["证据评估"],
                "implicit_assumptions": ["隐含假设"],
                "counterarguments": ["可能的反方观点"],
                "argument_limits": ["论证局限"],
                "visual_evidence": ["视觉证据"],
                "extended_connections": ["延伸联系"],
                "facts_to_verify": ["待核查事实"],
                "factual_basis": "视频事实依据",
                "ai_inferences": ["AI 推断；没有则留空数组"],
            },
        },
    }
    return schemas.get(profile, schemas["summary"])


def _profile_rules(profile: str) -> str:
    shared = (
        "所有分析模式都使用重大结构调整前的通用摘要骨架：summary、terminology、"
        "highlights、thoughts、chapters 使用顶层扁平字段；content 只承载当前模式真正需要的专属补充。\n"
        "summary 是主摘要正文；highlights、thoughts、chapters 按字幕中真实内容输出，"
        "不得为了凑数量制造节点，不得与 content 中的专属栏目机械重复。\n"
        "如果能从本次字幕中识别出 3 个及以上与核心内容直接相关、定义可靠的专业术语，"
        "写入 terminology；不足 3 个时返回空数组，不要用占位术语凑数。\n"
        "任何没有字幕依据的可选字段都返回空字符串或空数组，不要写“未明确说明”作为栏目占位。"
    )
    specific = {
        "summary": "标准摘要不使用 content 固定栏目。",
        "tutorial": (
            "教程模式重点补充教程目标、最终成果、前置条件、工具与材料、流程总览、完整步骤、"
            "关键参数、排错、验收清单、可复用命令或模板和教程局限。chapters 表示教程阶段；"
            "步骤只记录可复现操作，image 保持空字符串并由 tutorial + complete 的本地截图阶段填写。"
        ),
        "viral": (
            "爆款模式重点补充内容定位、目标受众、标题与封面承诺、前 30 秒钩子、内容结构、"
            "节奏与留存、情绪叙事、视觉剪辑、互动传播、可复用公式、可借鉴点和风险局限。"
        ),
        "close-reading": (
            "深度精读重点补充核心命题、关键概念、论证地图、证据评估、隐含假设、反方观点、"
            "论证局限、视觉证据、延伸联系和待核查事实；chapters 承载逐章精读。"
        ),
    }.get(profile, "")
    return f"{shared}\n{specific}".strip()


def _source_payload(source: object) -> dict:
    if source is None:
        return {}
    return {
        "platform": str(getattr(source, "platform", "") or ""),
        "url": str(getattr(source, "canonical_url", "") or getattr(source, "source_url", "") or ""),
        "title": str(getattr(source, "title", "") or ""),
        "source_id": str(getattr(source, "source_id", "") or ""),
    }


def _policy_payload(policy: object | None, window: AnalysisWindow | None, total_windows: int) -> dict:
    if policy is None:
        return {}
    return {
        "policy_version": "adaptive-v2",
        "duration_seconds": getattr(policy, "duration_seconds", 0),
        "duration_bucket": getattr(policy, "duration_bucket", "unknown"),
        "policy": getattr(policy, "policy", "single_pass"),
        "strategy": getattr(policy, "strategy", "single_pass"),
        "window_seconds": getattr(policy, "window_seconds", 0),
        "overlap_seconds": getattr(policy, "overlap_seconds", 0),
        "chapter_target_range": list(getattr(policy, "chapter_target_range", ())),
        "highlight_target_range": list(getattr(policy, "highlight_target_range", ())),
        "analysis_profile": getattr(policy, "analysis_profile", ""),
        "processing_profile": getattr(policy, "processing_profile", ""),
        "hierarchical_output": getattr(policy, "hierarchical_output", False),
        "coverage_gap_threshold_seconds": getattr(policy, "coverage_gap_threshold_seconds", 0),
        "is_local_window": total_windows > 1,
        "window_index": window.index if window else 0,
        "window_count": total_windows,
        "window_start": window.start if window else 0,
        "window_end": window.end if window else 0,
    }
