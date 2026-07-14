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
}


def get_profile(name: str) -> AnalysisProfile:
    return PROFILES[name]

