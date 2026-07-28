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

    def test_default_requirements_keep_cloud_asr_without_cuda_packages(self) -> None:
        requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("openai", requirements)
        self.assertIn("faster-whisper", requirements)
        self.assertNotIn("nvidia-cublas-cu12", requirements)
        self.assertNotIn("nvidia-cudnn-cu12", requirements)


if __name__ == "__main__":
    unittest.main()
