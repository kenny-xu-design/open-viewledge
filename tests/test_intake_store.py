from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.intake_store import IntakeStore


def payload(*, client_request_id: str = "client-1", url: str = "https://www.youtube.com/watch?v=abc123") -> dict:
    return {
        "schema_version": "1.0",
        "client_request_id": client_request_id,
        "source": {"kind": "video", "url": url},
        "capture": {"title": "Demo", "selected_text": "private selection"},
        "preferences": {"analysis_profile": "summary", "processing_profile": "fast", "output_languages": ["source"]},
        "consent": {"user_initiated": True, "content_upload_allowed": False},
    }


class IntakeStoreTests(unittest.TestCase):
    def test_create_is_idempotent_and_persists_public_safe_record(self) -> None:
        with TemporaryDirectory() as temp:
            store = IntakeStore(Path(temp) / "intakes.json")
            first, replayed = store.create(payload(), "idem-1")
            second, replayed_again = store.create(payload(), "idem-1")

            self.assertFalse(replayed)
            self.assertTrue(replayed_again)
            self.assertEqual(first.intake_id, second.intake_id)
            self.assertEqual(first.canonical_url, "https://www.youtube.com/watch?v=abc123")
            self.assertNotIn("private selection", json.dumps(first.to_public(), ensure_ascii=False))
            self.assertEqual(IntakeStore(Path(temp) / "intakes.json").get(first.intake_id).intake_id, first.intake_id)

    def test_same_source_is_marked_duplicate_using_identity_contract(self) -> None:
        with TemporaryDirectory() as temp:
            store = IntakeStore(Path(temp) / "intakes.json")
            first, _ = store.create(payload(), "idem-1")
            second, _ = store.create(payload(client_request_id="client-2"), "idem-2")

            self.assertEqual(first.state, "queued")
            self.assertEqual(second.state, "duplicate")
            self.assertEqual(second.duplicate_kind, "active_exact")
            self.assertEqual(second.duplicate_knowledge_id, first.knowledge_id)
            self.assertEqual(second.duplicate_allowed_actions, ["reject"])

    def test_different_processing_profile_is_source_revision(self) -> None:
        with TemporaryDirectory() as temp:
            store = IntakeStore(Path(temp) / "intakes.json")
            store.create(payload(), "idem-1")
            revised = payload(client_request_id="client-2")
            revised["preferences"]["processing_profile"] = "complete"
            second, _ = store.create(revised, "idem-2")

            self.assertEqual(second.state, "duplicate")
            self.assertEqual(second.duplicate_kind, "source_revision")
            self.assertIn("revision", second.duplicate_allowed_actions)

    def test_page_intake_uses_stable_identity(self) -> None:
        with TemporaryDirectory() as temp:
            store = IntakeStore(Path(temp) / "intakes.json")
            page = payload()
            page["source"] = {"kind": "page", "url": "https://example.com/article/?utm_source=test"}
            first, _ = store.create(page, "idem-1")
            second, _ = store.create({**page, "client_request_id": "client-2"}, "idem-2")

            self.assertTrue(first.knowledge_id.startswith("k1-web-"))
            self.assertEqual(second.state, "duplicate")

    def test_invalid_consent_and_cursor_are_rejected(self) -> None:
        with TemporaryDirectory() as temp:
            store = IntakeStore(Path(temp) / "intakes.json")
            invalid = payload()
            invalid["consent"]["user_initiated"] = False
            with self.assertRaisesRegex(ValueError, "用户主动"):
                store.create(invalid, "idem-1")
            with self.assertRaisesRegex(ValueError, "cursor"):
                store.list_inbox("missing")


if __name__ == "__main__":
    unittest.main()
