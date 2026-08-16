from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.folder_sets import FolderSetStore, MAX_DEPTH, inspect_folder


class FolderSetTests(unittest.TestCase):
    def test_inspect_supports_ts_and_three_levels(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            (base / "01").mkdir()
            (base / "01" / "02").mkdir()
            (base / "01" / "02" / "03").mkdir()
            (base / "root.ts").write_bytes(b"root")
            (base / "01" / "a.ts").write_bytes(b"a")
            (base / "01" / "02" / "b.mp4").write_bytes(b"b")
            (base / "01" / "02" / "03" / "c.mkv").write_bytes(b"c")
            result = inspect_folder(str(base))
            self.assertEqual(result["videoCount"], 3)
            self.assertEqual(max(item["depth"] for item in result["folders"]), MAX_DEPTH)

    def test_store_hides_absolute_paths_and_reorders_only_children(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            (base / "a").mkdir(); (base / "b").mkdir()
            (base / "a" / "one.ts").write_bytes(b"one")
            (base / "b" / "two.ts").write_bytes(b"two")
            store = FolderSetStore(base / "state.json")
            root_set, replayed = store.create(str(base), "", "idem-1")
            self.assertFalse(replayed)
            public = root_set.to_public()
            self.assertNotIn(str(base), str(public))
            self.assertFalse(public["items"])
            self.assertEqual(len(public["childSetIds"]), 2)
            with self.assertRaises(ValueError):
                store.reorder_children(root_set.set_id, ["not-a-child"])
            original = list(root_set.child_set_ids)
            reordered = store.reorder_children(root_set.set_id, list(reversed(original)))
            self.assertEqual(reordered.child_set_ids, list(reversed(original)))

    def test_depth_limit_and_idempotent_create(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            base = Path(root); (base / "v.ts").write_bytes(b"v")
            store = FolderSetStore(base / "state.json")
            first, replayed = store.create(str(base), "", "same")
            again, replayed = store.create(str(base), "changed", "same")
            self.assertTrue(replayed); self.assertEqual(first.set_id, again.set_id)
            child = store.create_child(first.set_id, "child")
            grandchild = store.create_child(child.set_id, "grandchild")
            with self.assertRaises(ValueError):
                store.create_child(grandchild.set_id, "too deep")

    def test_quoted_folder_path_is_normalized_for_validation_and_creation(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            (base / "lesson.ts").write_bytes(b"video")
            quoted = f'"{base}"'
            inspection = inspect_folder(quoted)
            self.assertEqual(inspection["videoCount"], 1)
            store = FolderSetStore(base / "state.json")
            record, replayed = store.create(quoted, "", "quoted-path")
            self.assertFalse(replayed)
            self.assertEqual(record.source_path, str(base.resolve()))
            self.assertEqual(record.items[0].source_path, str((base / "lesson.ts").resolve()))

    def test_folder_set_persists_analysis_defaults_for_later_batch_runs(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            (base / "lesson.ts").write_bytes(b"video")
            store = FolderSetStore(base / "state.json")
            record, _ = store.create(
                str(base), "Course", "settings-1",
                analysis_profile="close-reading",
                processing_profile="fast",
                transcript_group_seconds=60,
            )
            public = record.to_public()
            self.assertEqual(public["analysisProfile"], "close-reading")
            self.assertEqual(public["processingProfile"], "fast")
            self.assertEqual(public["transcriptGroupSeconds"], 60)
            reloaded = FolderSetStore(base / "state.json").get(record.set_id)
            self.assertEqual(reloaded.analysis_profile, "close-reading")
            self.assertEqual(reloaded.processing_profile, "fast")
            self.assertEqual(reloaded.transcript_group_seconds, 60)

    def test_empty_folder_path_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            inspect_folder('""')

    def test_descendants_follow_child_order(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            base = Path(root); (base / "root.ts").write_bytes(b"root")
            (base / "child").mkdir(); (base / "child" / "one.ts").write_bytes(b"one")
            store = FolderSetStore(base / "state.json")
            root_set, _ = store.create(str(base), "", "tree")
            records = store.descendants(root_set.set_id, include_self=True)
            self.assertEqual([record.relative_path for record in records], ["", "child"])

    def test_can_insert_parent_for_nested_folder(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            base = Path(root); (base / "v.ts").write_bytes(b"v")
            store = FolderSetStore(base / "state.json")
            root_set, _ = store.create(str(base), "", "parent-idem")
            child = store.create_child(root_set.set_id, "child")
            parent = store.create_parent(child.set_id, "wrapper")
            self.assertEqual(parent.parent_set_id, root_set.set_id)
            self.assertEqual(store.get(child.set_id).parent_set_id, parent.set_id)
            self.assertEqual(store.get(child.set_id).depth, 2)

    def test_can_wrap_root_when_tree_has_room(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            base = Path(root); (base / "v.ts").write_bytes(b"v")
            store = FolderSetStore(base / "state.json")
            root_set, _ = store.create(str(base), "", "wrap-idem")
            parent = store.create_parent(root_set.set_id, "root wrapper")
            self.assertEqual(parent.depth, 0)
            self.assertEqual(store.get(root_set.set_id).parent_set_id, parent.set_id)

    def test_batch_reconcile_writes_once_and_skips_identical_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            (base / "one.ts").write_bytes(b"one")
            (base / "two.ts").write_bytes(b"two")
            store = FolderSetStore(base / "state.json")
            record, _ = store.create(str(base), "Course", "batch-reconcile")
            updates = [
                {"item_id": item.item_id, "state": "ready", "knowledge_id": f"kid-{item.sequence}", "error": ""}
                for item in record.items
            ]

            with patch.object(store, "_write", wraps=store._write) as write:
                store.reconcile_items(record.set_id, updates)
                self.assertEqual(write.call_count, 1)
                store.reconcile_items(record.set_id, updates)
                self.assertEqual(write.call_count, 1)


if __name__ == "__main__":
    unittest.main()
