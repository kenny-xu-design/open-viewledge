from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.note_store import MAX_NOTE_BYTES, NoteConflictError, NoteStore


class NoteStoreTests(unittest.TestCase):
    def test_note_is_persisted_and_reloaded(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = NoteStore(lambda _knowledge_id: root)

            empty = store.load("demo")
            saved = store.save("demo", "# 我的笔记\n\n重要判断。", empty["revision"])
            reloaded = NoteStore(lambda _knowledge_id: root).load("demo")

        self.assertEqual(saved["content"], "# 我的笔记\n\n重要判断。")
        self.assertEqual(reloaded["content"], saved["content"])
        self.assertEqual(reloaded["revision"], saved["revision"])
        self.assertTrue(saved["updated_at"])

    def test_stale_revision_is_rejected_without_overwrite(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = NoteStore(lambda _knowledge_id: root)
            initial = store.load("demo")
            first = store.save("demo", "第一版", initial["revision"])

            with self.assertRaises(NoteConflictError) as context:
                store.save("demo", "过期覆盖", initial["revision"])

            self.assertEqual(context.exception.current["revision"], first["revision"])
            self.assertEqual(store.load("demo")["content"], "第一版")

    def test_note_size_is_limited(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = NoteStore(lambda _knowledge_id: Path(temp_dir))
            with self.assertRaisesRegex(ValueError, "1 MiB"):
                store.save("demo", "a" * (MAX_NOTE_BYTES + 1))


if __name__ == "__main__":
    unittest.main()
