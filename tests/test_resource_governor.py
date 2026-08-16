from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.resource_governor import cpu_thread_limit, lock_path, resource_guard


class ResourceGovernorTests(unittest.TestCase):
    def test_cpu_thread_profiles_keep_responsive_budget_small(self) -> None:
        with patch("src.resource_governor.os.cpu_count", return_value=12):
            self.assertEqual(cpu_thread_limit("responsive"), 4)
            self.assertEqual(cpu_thread_limit("balanced"), 6)
            self.assertEqual(cpu_thread_limit("performance"), 8)
        self.assertEqual(cpu_thread_limit("responsive", 2), 2)

    def test_resource_guard_uses_state_root_and_releases_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(os.environ, {"VIEWLEDGE_STATE_ROOT": temp}, clear=False):
                with resource_guard("cpu", timeout_seconds=1):
                    self.assertTrue(lock_path("cpu").is_file())
                with resource_guard("cpu", timeout_seconds=1):
                    self.assertTrue(lock_path("cpu").is_file())


if __name__ == "__main__":
    unittest.main()
