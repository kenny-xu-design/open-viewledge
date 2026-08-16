from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.cache import CACHE_ARTIFACT_TYPES, CacheStore, build_cache_key, default_cache_root, source_cache_dimensions
from src.domain.models import SourceRecord


class CacheContractTests(unittest.TestCase):
    def test_all_v14_artifact_types_have_stable_distinct_keys(self) -> None:
        keys = {
            artifact_type: build_cache_key(
                artifact_type,
                platform="youtube",
                source_id="video-id",
                language="zh",
                sample_end=30,
                processing_profile="fast",
                provider="deepseek",
                model="test",
                prompt_version="1",
            )
            for artifact_type in CACHE_ARTIFACT_TYPES
        }

        self.assertEqual(len(set(keys.values())), len(CACHE_ARTIFACT_TYPES))
        self.assertTrue(all(len(value) == 64 for value in keys.values()))
        self.assertEqual(
            build_cache_key("metadata", source_id="id", language="zh"),
            build_cache_key("metadata", language="zh", source_id="id"),
        )

    def test_source_dimensions_keep_youtube_id_and_bilibili_part(self) -> None:
        youtube = SourceRecord(
            source_type="online_video",
            platform="youtube",
            source_url="https://www.youtube.com/watch?v=abc123",
            source_id="abc123",
        )
        bilibili = SourceRecord(
            source_type="online_video",
            platform="bilibili",
            source_url="https://www.bilibili.com/video/BV123?p=3",
            source_id="BV123",
        )

        self.assertEqual(source_cache_dimensions(youtube)["youtube_video_id"], "abc123")
        self.assertEqual(source_cache_dimensions(bilibili)["bilibili_part"], "3")

    def test_cache_store_round_trip_and_invalid_entries_degrade_to_miss(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = CacheStore(Path(temp))
            key = build_cache_key("transcript", source_id="demo")
            path = store.put("transcript", key, [{"text": "cached"}])
            self.assertEqual(store.get("transcript", key), [{"text": "cached"}])

            path.write_text("{broken", encoding="utf-8")
            self.assertIsNone(store.get("transcript", key))

            with self.assertRaises(ValueError):
                store.get("transcript", "../escape")
            with self.assertRaises(ValueError):
                build_cache_key("secret", source_id="demo")

    def test_default_cache_follows_external_state_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(os.environ, {"VIEWLEDGE_STATE_ROOT": temp}, clear=False), patch.dict(os.environ, {"VIEWLEDGE_CACHE_ROOT": ""}, clear=False):
                self.assertEqual(default_cache_root(), Path(temp) / "cache" / "v1")
                self.assertEqual(CacheStore().root, Path(temp) / "cache" / "v1")


if __name__ == "__main__":
    unittest.main()
