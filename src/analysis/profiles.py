from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnalysisProfile:
    name: str
    instruction: str


PROFILES = {
    "summary": AnalysisProfile("summary", "概括核心观点，保持准确简洁。"),
    "tutorial": AnalysisProfile("tutorial", "突出可复现步骤、前置条件和注意事项。"),
    "viral": AnalysisProfile("viral", "分析内容结构、传播钩子和可迁移的原创表达方法。"),
    "close-reading": AnalysisProfile("close-reading", "紧贴原文进行细读，区分事实、观点与推论。"),
    "interview": AnalysisProfile("interview", "提炼访谈双方观点、论据和关键问答。"),
    "lecture": AnalysisProfile("lecture", "提炼课程概念、论证结构和学习要点。"),
    "review": AnalysisProfile("review", "提炼评测对象、判断依据、优缺点和结论。"),
}


def get_profile(name: str) -> AnalysisProfile:
    return PROFILES.get(name, PROFILES["summary"])


def resolve_analysis_profile(
    explicit: str | None,
    existing: str | None = None,
    *,
    title: str = "",
    transcript: str = "",
) -> str:
    explicit_name = str(explicit or "").strip().lower()
    if explicit_name and explicit_name != "auto":
        return explicit_name if explicit_name in PROFILES else "summary"
    existing_name = str(existing or "").strip().lower()
    if existing_name in PROFILES:
        return existing_name
    sample = f"{title}\n{transcript[:12000]}".lower()
    tutorial_signals = (
        "教程", "操作", "步骤", "工作流", "workflow", "第一步", "下一步", "然后", "最后",
        "创建", "配置", "安装", "命令", "路径", "目录", "文件", "怎么", "如何",
    )
    score = sum(1 for value in tutorial_signals if value in sample)
    return "tutorial" if score >= 3 else "summary"

