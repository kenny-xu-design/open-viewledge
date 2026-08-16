from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src.job_store import Job
from src.knowledge_sets import KnowledgeSetStore, knowledge_set_registry_path
from src import web


def _inspection(title: str, source_id: str) -> dict[str, object]:
    return {
        "kind": "bilibili_parts",
        "title": title,
        "sourceUrl": f"https://www.bilibili.com/video/{source_id}",
        "uploader": "作者",
        "items": [
            {
                "sequence": index,
                "title": f"第 {index} 节",
                "sourceUrl": f"https://www.bilibili.com/video/{source_id}?p={index}",
                "partition": "分P",
            }
            for index in range(1, 4)
        ],
    }


class KnowledgeSetStorageTests(unittest.TestCase):
    def test_registry_is_grouped_under_shared_output_root(self) -> None:
        root = Path("shared-knowledge")
        self.assertEqual(
            knowledge_set_registry_path(root),
            root / "knowledge_sets" / "registry.json",
        )

    def test_legacy_registries_are_merged_without_modifying_sources(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_path = root / "legacy-one.json"
            second_path = root / "legacy-two.json"
            first, _ = KnowledgeSetStore(first_path).create(_inspection("课程一", "BV1111111111"), "legacy-one")
            second, _ = KnowledgeSetStore(second_path).create(_inspection("课程二", "BV2222222222"), "legacy-two")
            first_before = first_path.read_bytes()
            second_before = second_path.read_bytes()
            primary = knowledge_set_registry_path(root / "knowledge")

            records = KnowledgeSetStore(primary, legacy_paths=(first_path, second_path)).list()

            self.assertEqual({record.set_id for record in records}, {first.set_id, second.set_id})
            self.assertTrue(primary.is_file())
            self.assertEqual(first_path.read_bytes(), first_before)
            self.assertEqual(second_path.read_bytes(), second_before)
            self.assertEqual(len(KnowledgeSetStore(primary).list()), 2)

    def test_batch_reconcile_writes_once_and_identical_refresh_is_noop(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = KnowledgeSetStore(Path(temp_dir) / "sets.json")
            record, _ = store.create(_inspection("批量协调", "BV3333333333"), "batch")
            updates = [
                {"item_id": item.item_id, "state": "ready", "knowledge_id": f"kid-{item.sequence}", "error": ""}
                for item in record.items
            ]

            with patch.object(store, "_write", wraps=store._write) as write:
                store.reconcile_items(record.set_id, updates)
                self.assertEqual(write.call_count, 1)
                store.reconcile_items(record.set_id, updates)
                self.assertEqual(write.call_count, 1)

    def test_web_reconcile_batches_job_updates(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = KnowledgeSetStore(Path(temp_dir) / "sets.json")
            record, _ = store.create(_inspection("任务协调", "BV4444444444"), "jobs")
            jobs: dict[str, Job] = {}
            for item in record.items:
                job_id = f"job-{item.sequence}"
                knowledge_id = f"kid-{item.sequence}"
                store.attach_job(record.set_id, item.item_id, job_id, knowledge_id)
                jobs[job_id] = Job(id=job_id, command=[], status="success", knowledge_id=knowledge_id)

            with patch.object(store, "_write", wraps=store._write) as write, patch(
                "src.web.KNOWLEDGE_SET_STORE", store
            ), patch.dict(web.JOBS, jobs, clear=True):
                reconciled = web._reconcile_knowledge_set(store.get(record.set_id))
                self.assertEqual(write.call_count, 1)
                self.assertTrue(all(item.state == "ready" for item in reconciled.items))
                web._reconcile_knowledge_set(reconciled)
                self.assertEqual(write.call_count, 1)


if __name__ == "__main__":
    unittest.main()
