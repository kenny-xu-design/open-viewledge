from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from src.analysis.segmentation import attach_segmentation, build_analysis_windows, route_segmentation_policy
from src.analysis.service import AnalysisService
from src.domain.models import AnalysisResult, ChapterSummary, TranscriptGroup
from src.providers.llm.base import LLMResponse


def _groups(duration: int, *, every: int = 300, dense: bool = True) -> list[TranscriptGroup]:
    result = []
    text = "这一段包含具体操作、主题转换、参数设置和真实步骤证据。" * (8 if dense else 1)
    index = 0
    start = 0
    while start < duration:
        end = min(duration, start + every)
        result.append(TranscriptGroup(index=index, start=start, end=end, title=f"片段 {index + 1}", text=text, segment_indexes=[index]))
        index += 1
        start = end
    return result


class _WindowProvider:
    name = "deepseek"
    model_name = "fake-model"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def complete(self, messages, **kwargs):
        prompt = messages[-1]["content"]
        self.calls.append(prompt)
        source = json.loads(prompt.split("字幕分组：", 1)[1])
        first = source[0]
        start = float(first["start"])
        end = float(source[-1]["end"])
        index = len(self.calls)
        if "analysis_profile='summary'" in prompt:
            payload = {
                "summary": f"窗口 {index} 的背景、主要内容和结论。",
                "terminology": [{"term": f"术语 {index}", "definition": f"窗口 {index} 中的可靠解释"}],
                "highlights": [{"title": f"高光 {index}", "explanation": "值得回看", "start": start + 120}],
                "thoughts": [{"question": f"窗口 {index} 带来什么思考？"}],
                "chapters": [{"title": f"章节 {index}", "start": start, "end": end, "summary": "窗口内真实主题"}],
            }
        elif "analysis_profile='viral'" in prompt:
            payload = {
                "summary": f"窗口 {index} 的传播分析。",
                "terminology": [{"term": f"术语 {index}", "definition": f"窗口 {index} 中的可靠解释"}],
                "highlights": [{"title": f"高光 {index}", "explanation": "传播节点", "start": start + 120}],
                "thoughts": [{"question": f"窗口 {index} 的传播机制是什么？"}],
                "chapters": [{"title": f"章节 {index}", "start": start, "end": end, "summary": "窗口结构"}],
                "content": {"retention_design": [f"窗口 {index} 的留存方法"]},
            }
        elif "analysis_profile='close-reading'" in prompt:
            payload = {
                "summary": f"窗口 {index} 的精读摘要。",
                "terminology": [{"term": f"术语 {index}", "definition": f"窗口 {index} 中的可靠解释"}],
                "highlights": [{"title": f"证据 {index}", "explanation": "论证证据", "start": start + 120}],
                "thoughts": [{"question": f"窗口 {index} 的隐含前提是什么？"}],
                "chapters": [{"title": f"章节 {index}", "start": start, "end": end, "summary": "逐章精读"}],
                "content": {"implicit_assumptions": [f"窗口 {index} 的隐含假设"]},
            }
        else:
            payload = {
                "summary": f"窗口 {index} 的教程摘要。",
                "terminology": [{"term": f"术语 {index}", "definition": f"窗口 {index} 中的可靠解释"}],
                "chapters": [{"id": f"ch{index:03d}", "title": f"阶段 {index}", "start": start, "end": end, "summary": "窗口内真实主题"}],
                "content": {
                    "tutorial_goal": "完成长教程",
                    "workflow_overview": "按窗口提取真实阶段和步骤。",
                    "steps": [{"chapter_id": f"ch{index:03d}", "timestamp": start + 60, "title": f"步骤 {index}", "action": "执行真实操作", "expected_result": "得到阶段结果"}],
                },
                "highlights": [{"title": f"高光 {index}", "summary": "值得回看", "timestamp": start + 120}],
            }
        return LLMResponse(json.dumps(payload, ensure_ascii=False), self.name, self.model_name)


class AdaptiveSegmentationV143Tests(unittest.TestCase):
    def test_duration_buckets_have_dynamic_target_ranges(self) -> None:
        cases = [
            (360, (3, 5), (2, 5), "under_10m"),
            (1_200, (5, 9), (4, 8), "10m_to_30m"),
            (2_700, (8, 14), (6, 12), "30m_to_60m"),
            (5_400, (12, 20), (10, 18), "60m_plus"),
        ]
        for duration, chapter_range, highlight_range, bucket in cases:
            policy = route_segmentation_policy(
                _groups(duration),
                analysis_profile="summary",
                processing_profile="complete",
                source_duration=duration,
            )
            self.assertEqual(policy.duration_bucket, bucket)
            self.assertEqual(policy.chapter_target_range, chapter_range)
            self.assertEqual(policy.highlight_target_range, highlight_range)

    def test_short_video_uses_single_pass(self) -> None:
        groups = _groups(360, every=60)
        policy = route_segmentation_policy(groups, analysis_profile="summary", processing_profile="complete", source_duration=360)
        self.assertFalse(policy.use_window_analysis)
        self.assertEqual(len(build_analysis_windows(groups, policy)), 1)

    def test_low_density_long_video_can_stay_below_range_without_fake_nodes(self) -> None:
        groups = _groups(4_500, every=900, dense=False)
        policy = route_segmentation_policy(groups, analysis_profile="summary", processing_profile="complete", source_duration=4_500)
        self.assertIn("字幕内容稀疏", " ".join(policy.notes))

    def test_71_minute_tutorial_uses_hierarchical_window_analysis(self) -> None:
        groups = _groups(4_270, every=300, dense=True)
        provider = _WindowProvider()
        result = AnalysisService(provider).analyze(groups, "tutorial", SimpleNamespace(source=SimpleNamespace(duration=4_270, chapters=[]), processing_profile="complete"))

        self.assertGreater(len(provider.calls), 1)
        self.assertEqual(result.segmentation.duration_bucket, "60m_plus")
        self.assertEqual(result.segmentation.strategy, "hierarchical_semantic_map_reduce")
        self.assertTrue(result.segmentation.hierarchical_output)
        self.assertGreater(result.segmentation.actual_chapter_count, 5)
        self.assertGreater(result.segmentation.actual_highlight_count, 3)
        self.assertGreater(result.segmentation.actual_tutorial_step_count, 5)
        self.assertLessEqual(result.segmentation.largest_uncovered_gap_seconds, result.segmentation.coverage_gap_threshold_seconds)
        self.assertTrue(all(step.chapter_id for step in result.steps))

    def test_window_prompt_contains_policy_context_and_absolute_window(self) -> None:
        groups = _groups(2_700, every=300, dense=True)
        provider = _WindowProvider()
        AnalysisService(provider).analyze(groups, "summary", SimpleNamespace(source=SimpleNamespace(duration=2_700, chapters=[]), processing_profile="complete"))
        prompt = provider.calls[0]
        self.assertIn("duration_bucket", prompt)
        self.assertIn("chapter_target_range", prompt)
        self.assertIn("window_start", prompt)
        self.assertIn("时间戳必须使用全视频绝对时间", prompt)

    def test_summary_window_reduce_merges_terms_thoughts_and_all_items(self) -> None:
        groups = _groups(2_700, every=300, dense=True)
        provider = _WindowProvider()
        result = AnalysisService(provider).analyze(
            groups,
            "summary",
            SimpleNamespace(source=SimpleNamespace(duration=2_700, chapters=[]), processing_profile="complete"),
        )

        self.assertGreater(len(provider.calls), 1)
        self.assertGreaterEqual(len(result.terminology), 3)
        self.assertGreater(len(result.highlights), 5)
        self.assertGreater(len(result.thoughts), 5)
        self.assertGreater(len(result.chapters), 5)
        self.assertEqual(result.segmentation.strategy, "semantic_map_reduce")

    def test_specialized_window_reduce_preserves_details_and_common_base(self) -> None:
        groups = _groups(2_700, every=300, dense=True)
        for profile, key in (("viral", "retention_design"), ("close-reading", "implicit_assumptions")):
            with self.subTest(profile=profile):
                provider = _WindowProvider()
                result = AnalysisService(provider).analyze(
                    groups,
                    profile,
                    SimpleNamespace(source=SimpleNamespace(duration=2_700, chapters=[]), processing_profile="complete"),
                )
                self.assertGreater(len(result.content[key]), 1)
                self.assertGreaterEqual(len(result.terminology), 3)
                self.assertGreater(len(result.highlights), 5)
                self.assertGreater(len(result.thoughts), 5)
                self.assertGreater(len(result.chapters), 5)

    def test_coverage_guard_repairs_with_real_transcript_group_not_midpoint(self) -> None:
        groups = _groups(2_700, every=300, dense=True)
        policy = route_segmentation_policy(groups, analysis_profile="summary", processing_profile="complete", source_duration=2_700)
        result = AnalysisResult(
            status="success",
            analysis_profile="summary",
            chapters=[
                ChapterSummary(title="开头", start=0, end=300, summary="开头"),
                ChapterSummary(title="结尾", start=2_400, end=2_700, summary="结尾"),
            ],
        )
        repaired = attach_segmentation(result, policy, groups)
        self.assertGreater(repaired.segmentation.reanalysis_count, 0)
        self.assertTrue(any(chapter.start in {300, 600, 900, 1200, 1500, 1800, 2100} for chapter in repaired.chapters))
        self.assertFalse(any(chapter.start == 1_200 and chapter.title == "机械中点" for chapter in repaired.chapters))

    def test_coverage_guard_does_not_repair_sparse_long_video(self) -> None:
        groups = _groups(4_500, every=900, dense=False)
        policy = route_segmentation_policy(groups, analysis_profile="summary", processing_profile="complete", source_duration=4_500)
        result = AnalysisResult(status="success", analysis_profile="summary", chapters=[ChapterSummary(title="开头", start=0, end=900, summary="开头")])
        repaired = attach_segmentation(result, policy, groups)
        self.assertEqual(repaired.segmentation.reanalysis_count, 0)


if __name__ == "__main__":
    unittest.main()
