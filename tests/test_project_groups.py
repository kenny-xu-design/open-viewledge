from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.project_groups import ProjectGroupStore, project_registry_path


class ProjectGroupStoreTests(unittest.TestCase):
    def test_registry_is_isolated_under_shared_output_root(self) -> None:
        root = Path("shared-knowledge")
        self.assertEqual(project_registry_path(root), root / "projects" / "registry.json")

    def test_create_is_idempotent_and_reloadable(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = project_registry_path(Path(temp_dir))
            store = ProjectGroupStore(path)
            first, replayed = store.create("课程项目", "create-one")
            again, replayed_again = store.create("忽略的新名称", "create-one")
            self.assertFalse(replayed)
            self.assertTrue(replayed_again)
            self.assertEqual(first.project_id, again.project_id)
            self.assertEqual(ProjectGroupStore(path).get(first.project_id).title, "课程项目")

    def test_move_enforces_one_project_without_touching_knowledge_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = root / "knowledge-demo"
            package.mkdir()
            manifest = package / "manifest.json"
            manifest.write_text('{"knowledge_id":"knowledge-demo"}', encoding="utf-8")
            before = manifest.read_bytes()
            store = ProjectGroupStore(project_registry_path(root))
            first, _ = store.create("项目一", "one")
            second, _ = store.create("项目二", "two")

            store.move_knowledge(first.project_id, "knowledge-demo")
            store.move_knowledge(second.project_id, "knowledge-demo")

            self.assertEqual(store.get(first.project_id).knowledge_ids, [])
            self.assertEqual(store.get(second.project_id).knowledge_ids, ["knowledge-demo"])
            self.assertEqual(manifest.read_bytes(), before)

    def test_delete_only_removes_grouping_record(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = ProjectGroupStore(project_registry_path(root))
            project, _ = store.create("待删除", "delete")
            store.move_knowledge(project.project_id, "knowledge-demo")
            deleted = store.delete(project.project_id)
            self.assertEqual(deleted.knowledge_ids, ["knowledge-demo"])
            self.assertEqual(store.list(), [])

    def test_stale_ids_are_filtered_for_public_payload_without_rewriting(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = project_registry_path(Path(temp_dir))
            store = ProjectGroupStore(path)
            project, _ = store.create("含失效引用", "stale")
            store.move_knowledge(project.project_id, "valid")
            store.move_knowledge(project.project_id, "missing")
            before = path.read_bytes()

            public = store.get(project.project_id).to_public(valid_knowledge_ids={"valid"})

            self.assertEqual(public["knowledgeIds"], ["valid"])
            self.assertEqual(path.read_bytes(), before)
            self.assertIn("missing", json.loads(path.read_text(encoding="utf-8"))["projects"][0]["knowledge_ids"])

    def test_rename_and_remove_are_noops_when_state_is_unchanged(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = ProjectGroupStore(project_registry_path(Path(temp_dir)))
            project, _ = store.create("原名称", "rename")
            renamed = store.rename(project.project_id, "新名称")
            self.assertEqual(renamed.title, "新名称")
            store.move_knowledge(project.project_id, "knowledge-demo")
            store.remove_knowledge(project.project_id, "knowledge-demo")
            store.remove_knowledge(project.project_id, "knowledge-demo")
            self.assertEqual(store.get(project.project_id).knowledge_ids, [])


if __name__ == "__main__":
    unittest.main()
