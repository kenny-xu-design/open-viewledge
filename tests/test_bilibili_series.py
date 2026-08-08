from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.bilibili_series import inspect_bilibili_input
from src.knowledge_sets import KnowledgeSetStore


class FakeYdl:
    def __init__(self, options: dict, info: dict):
        self.info = info

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url: str, download: bool = False):
        return self.info


class FakeYtdlp:
    def __init__(self, info: dict):
        self.info = info

    def YoutubeDL(self, options: dict):
        return FakeYdl(options, self.info)


class BilibiliSeriesTests(unittest.TestCase):
    def test_multipart_pages_are_returned_in_order_with_p_links(self) -> None:
        fake = FakeYtdlp({"title": "教程", "pages": [{"part": "第一节"}, {"part": "第二节"}]})
        with patch("src.bilibili_series._import_ytdlp", return_value=fake):
            result = inspect_bilibili_input("https://www.bilibili.com/video/BV1234567890")

        self.assertEqual(result["kind"], "bilibili_parts")
        self.assertEqual([item["sequence"] for item in result["items"]], [1, 2])
        self.assertEqual(result["items"][0]["title"], "第一节")
        self.assertIn("p=2", result["items"][1]["sourceUrl"])

    def test_playlist_entries_are_returned_as_series_items(self) -> None:
        fake = FakeYtdlp(
            {
                "title": "系列教程",
                "entries": [
                    {"id": "BV1111111111", "title": "入门", "section": "基础"},
                    {"id": "BV2222222222", "title": "进阶", "section": "进阶"},
                ],
            }
        )
        with patch("src.bilibili_series._import_ytdlp", return_value=fake):
            result = inspect_bilibili_input("https://www.bilibili.com/video/BV1234567890")

        self.assertEqual(result["kind"], "bilibili_series")
        self.assertEqual(result["items"][1]["partition"], "进阶")
        self.assertTrue(result["isCollection"])

    def test_store_creation_is_idempotent_and_items_can_be_reconciled(self) -> None:
        inspection = {
            "kind": "bilibili_parts",
            "title": "教程合集",
            "sourceUrl": "https://www.bilibili.com/video/BV1234567890",
            "uploader": "作者",
            "items": [
                {"sequence": 1, "title": "第一节", "sourceUrl": "https://www.bilibili.com/video/BV1234567890?p=1", "partition": "分P"},
                {"sequence": 2, "title": "第二节", "sourceUrl": "https://www.bilibili.com/video/BV1234567890?p=2", "partition": "分P"},
            ],
        }
        with TemporaryDirectory() as temp:
            store = KnowledgeSetStore(Path(temp) / "sets.json")
            record, replayed = store.create(inspection, "set-idem")
            replay, replayed_again = store.create(inspection, "set-idem")
            self.assertFalse(replayed)
            self.assertTrue(replayed_again)
            self.assertEqual(record.set_id, replay.set_id)
            set_id = record.set_id
            item_id = record.items[0].item_id
            _, item, action_replayed = store.begin_item_action(set_id, item_id, "item-idem")
            self.assertFalse(action_replayed)
            store.attach_job(set_id, item_id, "job-1", "k1-demo")
            store.reconcile_item(set_id, item_id, state="ready", knowledge_id="k1-demo")
            refreshed = store.get(set_id)
            self.assertEqual(refreshed.items[0].state, "ready")
            self.assertEqual(refreshed.items[0].knowledge_id, "k1-demo")
            store.mark_duplicate(set_id, refreshed.items[1].item_id, "duplicate")
            self.assertEqual(store.get(set_id).items[1].state, "duplicate")


if __name__ == "__main__":
    unittest.main()
