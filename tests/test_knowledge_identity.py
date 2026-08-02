from __future__ import annotations

import unittest

from src.domain.models import SourceRecord
from src.knowledge_identity import (
    DuplicateKind,
    KnowledgeRequestDimensions,
    TaskIdentityRecord,
    build_knowledge_identity,
    build_input_knowledge_identity,
    detect_duplicate,
    normalize_source_url,
)


class KnowledgeIdentityTests(unittest.TestCase):
    def test_youtube_variants_share_stable_knowledge_id(self) -> None:
        watch = SourceRecord(
            source_type="online_video",
            platform="youtube",
            source_url="https://www.youtube.com/watch?v=AbC_123-xYz&utm_source=test",
            source_id="metadata-id-is-not-used",
        )
        short = watch.model_copy(update={"source_url": "https://youtu.be/AbC_123-xYz?t=30"})

        self.assertEqual(
            build_knowledge_identity(watch).knowledge_id,
            build_knowledge_identity(short).knowledge_id,
        )

    def test_bilibili_part_is_distinct(self) -> None:
        first = SourceRecord(
            source_type="online_video",
            platform="bilibili",
            source_url="https://www.bilibili.com/video/BV1ab411c7DE?p=1",
            source_id="BV1ab411c7DE",
        )
        second = first.model_copy(update={"source_url": "https://www.bilibili.com/video/BV1ab411c7DE?p=2"})

        self.assertNotEqual(
            build_knowledge_identity(first).knowledge_id,
            build_knowledge_identity(second).knowledge_id,
        )

    def test_generic_url_tracking_parameters_do_not_change_identity(self) -> None:
        source = SourceRecord(
            source_type="web_page",
            platform="web",
            source_url="https://Example.com/article/?b=2&a=1&utm_campaign=test#section",
        )
        clean = source.model_copy(update={"source_url": "https://example.com/article?a=1&b=2"})

        self.assertEqual(
            build_knowledge_identity(source).knowledge_id,
            build_knowledge_identity(clean).knowledge_id,
        )

    def test_local_identity_uses_source_id_not_path(self) -> None:
        first = SourceRecord(
            source_type="local_video",
            platform="local",
            source_id="content123",
            local_path="first-location.mp4",
        )
        moved = first.model_copy(update={"local_path": "second-location.mp4"})

        self.assertEqual(
            build_knowledge_identity(first).knowledge_id,
            build_knowledge_identity(moved).knowledge_id,
        )

    def test_request_dimensions_create_revision_fingerprint(self) -> None:
        source = SourceRecord(
            source_type="online_video",
            platform="youtube",
            source_url="https://youtube.com/watch?v=AbC_123-xYz",
            source_id="AbC_123-xYz",
        )
        summary = build_knowledge_identity(source, KnowledgeRequestDimensions(analysis_profile="summary"))
        tutorial = build_knowledge_identity(source, KnowledgeRequestDimensions(analysis_profile="tutorial"))

        self.assertEqual(summary.knowledge_id, tutorial.knowledge_id)
        self.assertNotEqual(summary.request_fingerprint, tutorial.request_fingerprint)

    def test_transcript_group_seconds_create_revision_fingerprint(self) -> None:
        source = SourceRecord(
            source_type="online_video",
            platform="youtube",
            source_url="https://youtube.com/watch?v=AbC_123-xYz",
            source_id="AbC_123-xYz",
        )
        grouped_30 = build_knowledge_identity(
            source,
            KnowledgeRequestDimensions(transcript_group_seconds=30),
        )
        grouped_60 = build_knowledge_identity(
            source,
            KnowledgeRequestDimensions(transcript_group_seconds=60),
        )

        self.assertEqual(grouped_30.knowledge_id, grouped_60.knowledge_id)
        self.assertNotEqual(grouped_30.request_fingerprint, grouped_60.request_fingerprint)

    def test_invalid_dimensions_are_rejected(self) -> None:
        source = SourceRecord(
            source_type="online_video",
            platform="youtube",
            source_url="https://youtube.com/watch?v=AbC_123-xYz",
            source_id="AbC_123-xYz",
        )

        with self.assertRaisesRegex(ValueError, "sample_seconds"):
            build_knowledge_identity(source, KnowledgeRequestDimensions(sample_seconds=0))
        with self.assertRaisesRegex(ValueError, "transcript_group_seconds"):
            build_knowledge_identity(source, KnowledgeRequestDimensions(transcript_group_seconds=14))

    def test_url_normalization_removes_fragment_tracking_and_default_port(self) -> None:
        self.assertEqual(
            normalize_source_url("HTTPS://Example.COM:443/path/?z=2&utm_source=test&a=1#fragment"),
            "https://example.com/path?a=1&z=2",
        )

    def test_input_identity_for_url_does_not_need_platform_metadata(self) -> None:
        identity = build_input_knowledge_identity(
            "https://www.youtube.com/watch?v=AbC_123-xYz&utm_source=test",
            is_url=True,
        )

        self.assertTrue(identity.knowledge_id.startswith("k1-youtube-"))
        self.assertTrue(identity.request_fingerprint)


class DuplicateDetectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.identity = build_knowledge_identity(
            SourceRecord(
                source_type="online_video",
                platform="youtube",
                source_url="https://youtube.com/watch?v=AbC_123-xYz",
                source_id="AbC_123-xYz",
            )
        )

    def record(self, status: str, *, fingerprint: str | None = None) -> TaskIdentityRecord:
        return TaskIdentityRecord(
            task_id=f"task-{status}",
            knowledge_id=self.identity.knowledge_id,
            request_fingerprint=fingerprint or self.identity.request_fingerprint,
            status=status,
        )

    def test_active_exact_duplicate_is_rejected_first(self) -> None:
        decision = detect_duplicate(self.identity, [self.record("completed"), self.record("running")])

        self.assertEqual(decision.kind, DuplicateKind.ACTIVE_EXACT)
        self.assertEqual(decision.allowed_actions, ("reject",))

    def test_completed_exact_duplicate_allows_reuse_or_refresh(self) -> None:
        decision = detect_duplicate(self.identity, [self.record("completed")])

        self.assertEqual(decision.kind, DuplicateKind.COMPLETED_EXACT)
        self.assertEqual(decision.allowed_actions, ("reuse", "refresh", "reject"))

    def test_recoverable_exact_duplicate_allows_resume_or_refresh(self) -> None:
        decision = detect_duplicate(self.identity, [self.record("interrupted")])

        self.assertEqual(decision.kind, DuplicateKind.RECOVERABLE_EXACT)
        self.assertEqual(decision.allowed_actions, ("resume", "refresh", "reject"))

    def test_same_source_different_request_is_revision(self) -> None:
        decision = detect_duplicate(self.identity, [self.record("completed", fingerprint="different")])

        self.assertEqual(decision.kind, DuplicateKind.SOURCE_REVISION)
        self.assertEqual(decision.allowed_actions, ("revision", "refresh", "reject"))

    def test_unrelated_knowledge_is_not_duplicate(self) -> None:
        decision = detect_duplicate(
            self.identity,
            [
                TaskIdentityRecord(
                    task_id="other",
                    knowledge_id="k1-youtube-unrelated",
                    request_fingerprint=self.identity.request_fingerprint,
                    status="running",
                )
            ],
        )

        self.assertFalse(decision.detected)


if __name__ == "__main__":
    unittest.main()
