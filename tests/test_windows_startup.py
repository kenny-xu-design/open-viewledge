from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class WindowsStartupTests(unittest.TestCase):
    def test_start_web_registers_virtualenv_cuda_runtime_directories(self) -> None:
        script = (PROJECT_ROOT / "start_web.bat").read_text(encoding="utf-8")
        self.assertIn(r"nvidia\cublas\bin\cublas64_12.dll", script)
        self.assertIn(r"nvidia\cudnn\bin\cudnn64_9.dll", script)
        self.assertIn(r"%VENV_SITE_PACKAGES%\ctranslate2", script)
        self.assertLess(script.index(":install_dependencies"), script.index(":launch_web"))
        self.assertLess(
            script.index(r"nvidia\cublas\bin"),
            script.index(r'".venv\Scripts\python.exe" -m src.web'),
        )

    def test_windows_cuda_runtime_packages_are_declared(self) -> None:
        requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("nvidia-cublas-cu12", requirements)
        self.assertIn("nvidia-cudnn-cu12", requirements)
        self.assertIn('sys_platform == "win32"', requirements)


if __name__ == "__main__":
    unittest.main()
