from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.job_store import Job, JobStore
from src.utils import UserFacingError


class JobStoreTests(unittest.TestCase):
    def test_job_history_survives_store_recreation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "web_jobs.json"
            store = JobStore(path)
            job = Job(
                id="job-1",
                command=["python", "-m", "src.main"],
                analysis_profile="tutorial",
                processing_profile="fast",
                status="success",
                knowledge_id="demo",
                output_dir="output/demo",
                logs=["完成"],
            )
            store.upsert(job)

            reloaded = JobStore(path).load_jobs()

        self.assertEqual(len(reloaded), 1)
        self.assertEqual(reloaded[0].knowledge_id, "demo")
        self.assertEqual(reloaded[0].status, "success")
        self.assertEqual(reloaded[0].logs, ["完成"])
        self.assertEqual(reloaded[0].analysis_profile, "tutorial")
        self.assertEqual(reloaded[0].processing_profile, "fast")

    def test_running_job_becomes_interrupted_after_restart(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "web_jobs.json"
            first_store = JobStore(path)
            first_store.upsert(Job(id="job-2", command=["python"], status="running"))

            restored = JobStore(path).load_jobs()[0]
            persisted = JobStore(path).load_jobs()[0]

        self.assertEqual(restored.status, "interrupted")
        self.assertIn("服务重启", restored.error)
        self.assertIsNotNone(restored.finished_at)
        self.assertEqual(persisted.status, "interrupted")

    def test_corrupt_store_does_not_break_web_startup(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "web_jobs.json"
            path.write_text("{not-json", encoding="utf-8")
            self.assertEqual(JobStore(path).load_jobs(), [])

    def test_newer_web_task_store_schema_fails_explicitly(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "web_jobs.json"
            path.write_text('{"schema_version":"2.0","jobs":[]}', encoding="utf-8")
            with self.assertRaisesRegex(UserFacingError, "不支持"):
                JobStore(path).load_jobs()

    def test_legacy_web_job_defaults_to_complete_and_invalid_profile_fails(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "web_jobs.json"
            path.write_text(
                '{"schema_version":"1.0","jobs":[{"id":"legacy","command":["python"],"status":"success"}]}',
                encoding="utf-8",
            )
            legacy = JobStore(path).load_jobs()[0]
            self.assertEqual(legacy.processing_profile, "complete")

            path.write_text(
                '{"schema_version":"1.0","jobs":[{"id":"bad","command":["python"],"processing_profile":"turbo"}]}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(UserFacingError, "任务记录损坏"):
                JobStore(path).load_jobs()


if __name__ == "__main__":
    unittest.main()
