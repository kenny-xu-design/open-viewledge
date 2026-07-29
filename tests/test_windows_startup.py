from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class WindowsStartupTests(unittest.TestCase):
    def test_start_web_does_not_inject_cuda_runtime_directories(self) -> None:
        script = (PROJECT_ROOT / "start_web.bat").read_text(encoding="utf-8")
        self.assertNotIn(r"nvidia\cublas", script)
        self.assertNotIn(r"nvidia\cudnn", script)
        self.assertNotIn("VENV_SITE_PACKAGES", script)
        self.assertLess(script.index(":install_dependencies"), script.index(":launch_web"))
        self.assertIn('if not defined VIEWLEDGE_UI_MODE set "VIEWLEDGE_UI_MODE=product"', script)
        self.assertIn('if not defined SHOW_TECH_DETAILS set "SHOW_TECH_DETAILS=0"', script)
        self.assertIn('if not defined SHOW_RAW_PROCESS_LOGS set "SHOW_RAW_PROCESS_LOGS=0"', script)
        self.assertIn("requirements.lock.txt", script)
        self.assertIn("py -3.12", script)
        self.assertNotIn("py -3 -m venv", script)

    def test_default_requirements_keep_cloud_asr_without_cuda_packages(self) -> None:
        requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("openai", requirements)
        self.assertIn("faster-whisper", requirements)
        self.assertNotIn("nvidia-cublas-cu12", requirements)
        self.assertNotIn("nvidia-cudnn-cu12", requirements)
        locked = (PROJECT_ROOT / "requirements.lock.txt").read_text(encoding="utf-8")
        self.assertNotIn("nvidia-", locked.lower())

    def test_local_development_launcher_is_not_tracked(self) -> None:
        tracked = __import__("subprocess").run(
            ["git", "ls-files", "--error-unmatch", "start_dev.bat"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(tracked.returncode, 0)


if __name__ == "__main__":
    unittest.main()
