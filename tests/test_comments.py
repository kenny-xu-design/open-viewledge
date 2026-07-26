from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.comments import CommentRepository, CommentSyncResult, CommentSyncService
from src.comments.adapters import YouTubeCommentAdapter
from src.comments.insights import CommentInsightService
from src.cache import CacheStore
from src.config import AppConfig
from src.domain.models import NormalizedComment, SourceRecord, TranscriptSegment
from src.pipeline.orchestrator import PipelineOrchestrator
from src.providers.llm.base import LLMResponse
from src.utils import UserFacingError


class _FakeYtdlp:
    def __init__(self, info: dict) -> None:
        self.info = info
        self.opts = None

    def YoutubeDL(self, opts):
        self.opts = opts
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download=False):
        return self.info


class _FakeSource:
    def __init__(self) -> None:
        self.collect_metadata = Mock(side_effect=self._metadata)
        self.acquire_subtitles = Mock(side_effect=self._subtitle)
        self.acquire_media = Mock()

    def resolve(self, input_value: str) -> SourceRecord:
        return SourceRecord(
            source_type="online_video",
            platform="youtube",
            source_url=input_value,
            canonical_url=input_value,
            source_id="abc123",
            title="online-video",
        )

    def _metadata(self) -> SourceRecord:
        return SourceRecord(
            source_type="online_video",
            platform="youtube",
            source_url="https://www.youtube.com/watch?v=abc123",
            canonical_url="https://www.youtube.com/watch?v=abc123",
            source_id="abc123",
            title="Demo",
        )

    def _subtitle(self, work_dir: Path, language: str) -> Path:
        path = work_dir / "subtitle.vtt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("WEBVTT\n", encoding="utf-8")
        return path


class _FailingCommentSyncService:
    def sync(self, *_args, **_kwargs):
        raise UserFacingError("comments closed")


class _SuccessfulCommentSyncService:
    def sync(self, source, *, processing_profile: str, enabled: bool, existing=None):
        return CommentSyncResult(
            "success",
            [
                NormalizedComment(
                    comment_id="c1",
                    author="viewer",
                    content="01:28 这里讲得很清楚",
                    likes=10,
                    source_url=source.source_url,
                    timestamps=[88.0],
                    platform="youtube",
                )
            ],
            "fast",
            "top",
            30,
        )


class _UnavailableProvider:
    name = "deepseek"
    model_name = "test"

    def is_available(self):
        return False

    def complete(self, *_args, **_kwargs):
        raise AssertionError("unavailable provider must not be called")


class _JsonProvider:
    name = "deepseek"
    model_name = "test"

    def is_available(self):
        return True

    def complete(self, messages, **kwargs):
        return LLMResponse(
            '{"hot_topics":["片段清晰"],"frequent_questions":["如何复现？"],"recommended_segments":[{"timestamp":88,"reason":"多人提及"}]}',
            self.name,
            self.model_name,
        )


class CommentFeatureTests(unittest.TestCase):
    def test_adapter_normalizes_public_comments_and_timestamps(self) -> None:
        fake = _FakeYtdlp(
            {
                "comments": [
                    {
                        "id": "c1",
                        "author": "Alice",
                        "text": "01:28 和 1:02:03 都很有用",
                        "like_count": 9,
                        "timestamp": 1_700_000_000,
                    }
                ]
            }
        )
        source = SourceRecord(
            source_type="online_video",
            platform="youtube",
            source_url="https://www.youtube.com/watch?v=abc123",
            canonical_url="https://www.youtube.com/watch?v=abc123",
            source_id="abc123",
            title="Demo",
        )

        comments = YouTubeCommentAdapter(fake).fetch(source, limit=10)

        self.assertEqual(comments[0].comment_id, "c1")
        self.assertEqual(comments[0].timestamps, [88.0, 3723.0])
        self.assertTrue(fake.opts["getcomments"])

    def test_repository_keeps_comment_timestamp_links_separate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = CommentRepository(Path(temp))
            repo.save(
                [
                    NormalizedComment(
                        comment_id="c1",
                        content="00:00 开头",
                        source_url="https://www.bilibili.com/video/BV123?p=2",
                        timestamps=[0.0],
                        platform="bilibili",
                    )
                ]
            )
            payload = (Path(temp) / "comments.md").read_text(encoding="utf-8")

        self.assertIn("t=0", payload)
        self.assertIn("00:00", payload)

    def test_insight_service_uses_local_heuristic_when_provider_unavailable(self) -> None:
        insight = CommentInsightService(_UnavailableProvider()).analyze(
            [NormalizedComment(comment_id="c1", content="为什么这里这样做？", likes=3)]
        )

        self.assertEqual(insight.status, "success")
        self.assertEqual(insight.provider, "local")
        self.assertEqual(insight.frequent_questions, ["为什么这里这样做？"])

    def test_insight_service_parses_provider_json(self) -> None:
        insight = CommentInsightService(_JsonProvider()).analyze(
            [NormalizedComment(comment_id="c1", content="01:28 很清楚", likes=3)]
        )

        self.assertEqual(insight.hot_topics, ["片段清晰"])
        self.assertEqual(insight.recommended_segments[0]["timestamp"], 88)

    def test_complete_sync_merges_top_latest_and_existing_comments(self) -> None:
        source = SourceRecord(
            source_type="online_video",
            platform="youtube",
            source_url="https://www.youtube.com/watch?v=abc123",
            source_id="abc123",
            title="Demo",
        )
        adapter = Mock()
        adapter.fetch.side_effect = [
            [NormalizedComment(comment_id="top", content="热门", likes=10)],
            [NormalizedComment(comment_id="latest", content="最新", likes=1)],
        ]

        result = CommentSyncService(youtube_adapter=adapter).sync(
            source,
            processing_profile="complete",
            enabled=True,
            existing=[NormalizedComment(comment_id="old", content="旧评论", likes=2)],
        )

        self.assertEqual(adapter.fetch.call_args_list[0].kwargs["sort"], "top")
        self.assertEqual(adapter.fetch.call_args_list[1].kwargs["sort"], "latest")
        self.assertEqual({item.comment_id for item in result.comments}, {"top", "latest", "old"})

    def test_pipeline_comment_failure_is_warning_not_task_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = _FakeSource()
            config = AppConfig(output_dir=str(Path(temp) / "output"), keep_temp_files=True)
            with (
                patch("src.pipeline.orchestrator.YtdlpSource", return_value=source),
                patch("src.pipeline.orchestrator.parse_subtitle_file", return_value=[
                    TranscriptSegment(index=0, start=0, end=3, text="字幕", language="zh", source="subtitle")
                ]),
                patch("src.pipeline.orchestrator.CommentSyncService", return_value=_FailingCommentSyncService()),
                patch("src.pipeline.orchestrator.inspect_knowledge_package", return_value=SimpleNamespace(valid=True, issues=[])),
            ):
                package = PipelineOrchestrator(
                    config,
                    no_analysis=True,
                    comments_enabled=True,
                    cache_store=CacheStore(Path(temp) / "cache"),
                ).run("https://www.youtube.com/watch?v=abc123", is_url=True)

        self.assertEqual(package.manifest.stage_status["comments_fetch"], "warning")
        self.assertEqual(package.manifest.stage_status["comments_analysis"], "skipped")
        self.assertIn("comments closed", "\n".join(package.manifest.errors))

    def test_pipeline_writes_comment_artifacts_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = _FakeSource()
            config = AppConfig(output_dir=str(Path(temp) / "output"), keep_temp_files=True)
            with (
                patch("src.pipeline.orchestrator.YtdlpSource", return_value=source),
                patch("src.pipeline.orchestrator.parse_subtitle_file", return_value=[
                    TranscriptSegment(index=0, start=0, end=3, text="字幕", language="zh", source="subtitle")
                ]),
                patch("src.pipeline.orchestrator.CommentSyncService", return_value=_SuccessfulCommentSyncService()),
                patch("src.pipeline.orchestrator.DeepSeekProvider", return_value=_UnavailableProvider()),
                patch("src.pipeline.orchestrator.inspect_knowledge_package", return_value=SimpleNamespace(valid=True, issues=[])),
            ):
                package = PipelineOrchestrator(
                    config,
                    no_analysis=True,
                    comments_enabled=True,
                    processing_profile="fast",
                    cache_store=CacheStore(Path(temp) / "cache"),
                ).run("https://www.youtube.com/watch?v=abc123", is_url=True)

            self.assertEqual(package.manifest.stage_status["comments_fetch"], "completed")
            self.assertEqual(package.manifest.stage_status["comments_analysis"], "completed")
            self.assertTrue((package.output_dir / "comments.json").is_file())
            self.assertTrue((package.output_dir / "comment_insights.md").is_file())
            self.assertIn("comments.json", package.manifest.output_files)


if __name__ == "__main__":
    unittest.main()
