from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.clip_store import ClipStore


def _payload(text: str = "字幕片段") -> dict:
    return {
        "schema_version": "1.0",
        "client_request_id": "client-1",
        "target": {"knowledge_id": "k1"},
        "source": {"url": "https://Example.com/video#section", "title": "Demo"},
        "selection": {"text": text, "prefix": "前文", "suffix": "后文", "media_start_seconds": 1, "media_end_seconds": 4},
        "note": "复习",
        "captured_at": "2026-08-08T00:00:00Z",
    }


class ClipStoreTests(unittest.TestCase):
    def test_create_is_idempotent_and_hides_internal_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = ClipStore(Path(temp) / "clips.json")
            first, first_replayed = store.create(_payload(), "clip-key")
            second, second_replayed = store.create(_payload(), "clip-key")
            self.assertFalse(first_replayed)
            self.assertTrue(second_replayed)
            self.assertEqual(first.clip_id, second.clip_id)
            public = first.to_public()
            self.assertEqual(public["source"]["url"], "https://example.com/video")
            self.assertEqual(public["kind"], "clip")
            self.assertEqual(public["note"], _payload()["note"])
            self.assertNotIn("creation_fingerprint", str(public))

    def test_changed_idempotency_payload_and_invalid_provenance_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = ClipStore(Path(temp) / "clips.json")
            store.create(_payload(), "clip-key")
            with self.assertRaises(ValueError):
                store.create(_payload("changed"), "clip-key")
            invalid = _payload(); invalid["source"]["url"] = "C:/private/video.mp4"
            with self.assertRaises(ValueError):
                store.create(invalid, "other-key")

    def test_source_url_uses_shared_tracking_parameter_normalization(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = ClipStore(Path(temp) / "clips.json")
            payload = _payload()
            payload["source"]["url"] = "https://example.com/video/?utm_source=smoke&v=1#section"
            record, _ = store.create(payload, "normalized-key")
            self.assertEqual(record.source_url, "https://example.com/video?v=1")

    def test_highlight_kind_is_persisted_and_invalid_kind_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = ClipStore(Path(temp) / "clips.json")
            payload = _payload()
            payload["kind"] = "highlight"
            record, _ = store.create(payload, "highlight-key")
            self.assertEqual(record.to_public()["kind"], "highlight")
            invalid = _payload()
            invalid["kind"] = "bookmark"
            with self.assertRaises(ValueError):
                store.create(invalid, "invalid-kind-key")

    def test_selection_time_range_and_target_are_validated(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = ClipStore(Path(temp) / "clips.json")
            invalid = _payload(); invalid["target"] = {}
            with self.assertRaises(ValueError):
                store.create(invalid, "key-1")
            invalid = _payload(); invalid["selection"]["media_end_seconds"] = 0
            invalid["selection"]["media_start_seconds"] = 2
            with self.assertRaises(ValueError):
                store.create(invalid, "key-2")


if __name__ == "__main__":
    unittest.main()
