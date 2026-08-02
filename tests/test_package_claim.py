from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.package_claim import PackageClaimLocked, acquire_package_claim, package_claim_path


class PackageClaimTests(unittest.TestCase):
    def test_first_claim_creates_secret_free_record(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            acquire_package_claim(
                root,
                knowledge_id="k1-youtube-demo",
                request_fingerprint="request-1",
                task_id="task-1",
                output_dir=root / "Demo_video",
                now=100.0,
            )
            payload = json.loads(package_claim_path(root, "k1-youtube-demo").read_text(encoding="utf-8"))

        self.assertEqual(payload["knowledge_id"], "k1-youtube-demo")
        self.assertEqual(payload["request_fingerprint"], "request-1")
        self.assertEqual(payload["task_id"], "task-1")
        self.assertEqual(payload["output_dir"], "Demo_video")
        self.assertNotIn(str(root), json.dumps(payload))

    def test_active_claim_blocks_other_task(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            acquire_package_claim(
                root,
                knowledge_id="k1-youtube-demo",
                request_fingerprint="request-1",
                task_id="task-1",
                output_dir=root / "Demo_video",
                now=100.0,
            )

            with self.assertRaises(PackageClaimLocked) as caught:
                acquire_package_claim(
                    root,
                    knowledge_id="k1-youtube-demo",
                    request_fingerprint="request-1",
                    task_id="task-2",
                    output_dir=root / "Demo_video",
                    now=120.0,
                    stale_after_seconds=3600,
                )

        self.assertEqual(caught.exception.task_id, "task-1")

    def test_same_task_can_reacquire_its_claim(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            acquire_package_claim(
                root,
                knowledge_id="k1-youtube-demo",
                request_fingerprint="request-1",
                task_id="task-1",
                output_dir=root / "Demo_video",
                now=100.0,
            )
            second = acquire_package_claim(
                root,
                knowledge_id="k1-youtube-demo",
                request_fingerprint="request-1",
                task_id="task-1",
                output_dir=root / "Demo_video",
                now=120.0,
            )

            second.release()
            self.assertFalse(package_claim_path(root, "k1-youtube-demo").exists())

    def test_stale_claim_is_recovered_by_new_task(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            acquire_package_claim(
                root,
                knowledge_id="k1-youtube-demo",
                request_fingerprint="request-1",
                task_id="task-old",
                output_dir=root / "Demo_video",
                now=100.0,
            )

            recovered = acquire_package_claim(
                root,
                knowledge_id="k1-youtube-demo",
                request_fingerprint="request-1",
                task_id="task-new",
                output_dir=root / "Demo_video",
                now=500.0,
                stale_after_seconds=60,
            )
            payload = json.loads(package_claim_path(root, "k1-youtube-demo").read_text(encoding="utf-8"))

        self.assertEqual(recovered.recovered_from_task_id, "task-old")
        self.assertEqual(payload["task_id"], "task-new")

    def test_stale_owner_cannot_refresh_over_new_claim(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            old = acquire_package_claim(
                root,
                knowledge_id="k1-youtube-demo",
                request_fingerprint="request-1",
                task_id="task-old",
                output_dir=root / "Demo_video",
                now=100.0,
            )
            acquire_package_claim(
                root,
                knowledge_id="k1-youtube-demo",
                request_fingerprint="request-1",
                task_id="task-new",
                output_dir=root / "Demo_video",
                now=500.0,
                stale_after_seconds=60,
            )

            with self.assertRaises(PackageClaimLocked):
                old.refresh(now=510.0)
            payload = json.loads(package_claim_path(root, "k1-youtube-demo").read_text(encoding="utf-8"))

        self.assertEqual(payload["task_id"], "task-new")

    def test_release_does_not_remove_another_task_claim(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            old = acquire_package_claim(
                root,
                knowledge_id="k1-youtube-demo",
                request_fingerprint="request-1",
                task_id="task-old",
                output_dir=root / "Demo_video",
                now=100.0,
            )
            acquire_package_claim(
                root,
                knowledge_id="k1-youtube-demo",
                request_fingerprint="request-1",
                task_id="task-new",
                output_dir=root / "Demo_video",
                now=500.0,
                stale_after_seconds=60,
            )

            old.release()
            payload = json.loads(package_claim_path(root, "k1-youtube-demo").read_text(encoding="utf-8"))

        self.assertEqual(payload["task_id"], "task-new")


if __name__ == "__main__":
    unittest.main()
