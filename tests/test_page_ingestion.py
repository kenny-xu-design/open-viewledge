from __future__ import annotations

import json
import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.domain.models import SourceRecord
from src.intake_store import IntakeStore
from src.knowledge_identity import KnowledgeRequestDimensions, build_knowledge_identity
from src.knowledge_validation import inspect_knowledge_package
from src.page_ingestion import ingest_page_capture
from src.providers.llm import LLMResponse


def page_payload(*, upload_allowed: bool = False) -> dict:
    return {
        "schema_version": "1.0",
        "client_request_id": "page-client-1",
        "source": {"kind": "page", "url": "https://example.com/article?utm_source=test"},
        "capture": {
            "title": "Example Article",
            "selected_text": "第一段页面正文。\n\n<script>不要执行我</script>\n\n第二段事实内容。",
            "visible_text": "不应保留的整页内容",
        },
        "preferences": {
            "analysis_profile": "summary",
            "processing_profile": "fast",
            "output_languages": ["source"],
        },
        "consent": {
            "user_initiated": True,
            "content_upload_allowed": upload_allowed,
        },
    }


class FakeProvider:
    name = "deepseek"
    model_name = "test-model"

    def __init__(self) -> None:
        self.calls: list[tuple[list[dict], dict]] = []

    def is_available(self) -> bool:
        return True

    def complete(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return LLMResponse('{"summary":"页面摘要"}', self.name, self.model_name)


class PageIngestionTests(unittest.TestCase):
    def test_local_only_capture_builds_valid_page_package_without_provider(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            store = IntakeStore(root / "intakes.json")
            record, _ = store.create(page_payload(upload_allowed=False), "page-local-only")

            package = ingest_page_capture(record, root / "knowledge")
            inspection = inspect_knowledge_package(package.output_dir)
            manifest = json.loads((package.output_dir / "manifest.json").read_text(encoding="utf-8"))
            page_markdown = (package.output_dir / "page.md").read_text(encoding="utf-8")
            index_markdown = (package.output_dir / "index.md").read_text(encoding="utf-8")

            self.assertTrue(inspection.valid, [issue.message for issue in inspection.issues])
            self.assertEqual(package.source.source_type, "web_page")
            self.assertEqual(manifest["content_kind"], "web_page_capture")
            self.assertEqual(manifest["analysis_status"], "skipped")
            self.assertFalse(manifest["content_upload_allowed"])
            self.assertEqual(json.loads((package.output_dir / "timeline.json").read_text(encoding="utf-8"))["items"], [])
            self.assertIn("page_content.json", manifest["output_files"])
            self.assertNotIn("<script>", page_markdown)
            self.assertNotIn("**时间：", page_markdown)
            self.assertIn('type: "page-note"', index_markdown)
            self.assertIn("外源/网页", index_markdown)
            self.assertIn("网页来源", index_markdown)
            self.assertIn("[页面正文](page.md)", index_markdown)
            self.assertNotIn("视频来源", index_markdown)
            self.assertNotIn("分组字幕", index_markdown)
            self.assertNotIn("不应保留", json.dumps(record.to_public(), ensure_ascii=False))

    def test_allowed_capture_uses_page_safe_analysis_prompt(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            record, _ = IntakeStore(root / "intakes.json").create(
                page_payload(upload_allowed=True),
                "page-with-analysis",
            )
            provider = FakeProvider()

            package = ingest_page_capture(record, root / "knowledge", provider=provider)

            self.assertEqual(package.analysis.summary, "页面摘要")
            self.assertEqual(len(provider.calls), 1)
            messages = provider.calls[0][0]
            self.assertIn("不可信数据", messages[0]["content"])
            self.assertIn("页面正文分组", messages[1]["content"])
            self.assertNotIn("字幕分组", messages[1]["content"])

    def test_page_identity_matches_core_source_identity(self) -> None:
        with TemporaryDirectory() as temp:
            record, _ = IntakeStore(Path(temp) / "intakes.json").create(
                page_payload(),
                "page-identity",
            )
            source = SourceRecord(
                source_type="web_page",
                platform="web",
                source_url=record.canonical_url,
                canonical_url=record.canonical_url,
                source_id=hashlib.sha256(record.canonical_url.encode("utf-8")).hexdigest()[:20],
            )
            identity = build_knowledge_identity(
                source,
                KnowledgeRequestDimensions(analysis_profile="summary", processing_profile="fast"),
                input_value=record.canonical_url,
            )

            self.assertEqual(record.knowledge_id, identity.knowledge_id)
            self.assertEqual(record.source_fingerprint, identity.source_fingerprint)


if __name__ == "__main__":
    unittest.main()
