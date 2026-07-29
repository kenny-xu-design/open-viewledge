from __future__ import annotations

import argparse
import hashlib
import subprocess
import tempfile
import zipfile
from pathlib import Path

from build_release import BASE_ZIP, MODEL_ZIP, PRODUCT_DIR, ROOT, VERSION, scan_release


REQUIRED = (
    "start_web.bat",
    "requirements.lock.txt",
    "src/__init__.py",
    "src/web.py",
    "tools/ffmpeg/bin/ffmpeg.exe",
    "tools/ffmpeg/bin/ffprobe.exe",
    "tools/licenses/ffmpeg/LICENSE.txt",
    "tools/licenses/ffmpeg/BUILD_INFO.txt",
    "tools/licenses/ffmpeg/SOURCE.txt",
    "models/README.txt",
    "README-零基础使用.md",
    "README-本地GPU可选配置.md",
    "KNOWN_LIMITATIONS.md",
)


def verify_hash(zip_path: Path) -> str:
    sidecar = zip_path.with_suffix(zip_path.suffix + ".sha256")
    expected = sidecar.read_text(encoding="ascii").split()[0]
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    if digest != expected:
        raise SystemExit("SHA256 校验失败")
    return digest


def execute_version(path: Path) -> str:
    result = subprocess.run(
        [str(path), "-version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )
    output = (result.stdout or result.stderr).strip()
    if result.returncode != 0 or "version" not in output.lower():
        raise SystemExit(f"无法执行 {path.name} -version")
    return output.splitlines()[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify the Viewledge portable Windows release.")
    parser.add_argument("--zip", type=Path, default=ROOT / "release" / BASE_ZIP)
    args = parser.parse_args()
    zip_path = args.zip.resolve()
    digest = verify_hash(zip_path)
    with tempfile.TemporaryDirectory(prefix="viewledge-verify-") as temp:
        temp_root = Path(temp)
        with zipfile.ZipFile(zip_path) as archive:
            names = set(archive.namelist())
            archive.extractall(temp_root)
        missing = [name for name in REQUIRED if f"{PRODUCT_DIR}/{name}" not in names]
        if missing:
            raise SystemExit("ZIP 缺少：" + "、".join(missing))
        release_root = temp_root / PRODUCT_DIR
        scan_release(release_root)
        start_text = (release_root / "start_web.bat").read_text(encoding="utf-8")
        required_start_tokens = (
            "VIEWLEDGE_UI_MODE=product",
            "SHOW_TECH_DETAILS=0",
            "SHOW_RAW_PROCESS_LOGS=0",
            "requirements.lock.txt",
            "py -3.12",
        )
        if not all(token in start_text for token in required_start_tokens):
            raise SystemExit("start_web.bat 不符合产品启动契约")
        if "nvidia-" in start_text.lower():
            raise SystemExit("start_web.bat 包含 NVIDIA 安装命令")
        version_text = (release_root / "src/__init__.py").read_text(encoding="utf-8")
        if f'__version__ = "{VERSION}"' not in version_text:
            raise SystemExit("发行版本号不匹配")
        ffmpeg = execute_version(release_root / "tools/ffmpeg/bin/ffmpeg.exe")
        ffprobe = execute_version(release_root / "tools/ffmpeg/bin/ffprobe.exe")
    print(f"Verified: {zip_path}")
    print(f"SHA256: {digest}")
    print(ffmpeg)
    print(ffprobe)
    model_zip = zip_path.parent / MODEL_ZIP
    if model_zip.is_file():
        model_digest = verify_hash(model_zip)
        with zipfile.ZipFile(model_zip) as archive:
            names = set(archive.namelist())
        required_model = {
            "models/faster-whisper-small/config.json",
            "models/faster-whisper-small/model.bin",
            "models/faster-whisper-small/tokenizer.json",
        }
        if not required_model.issubset(names):
            raise SystemExit("模型扩展包缺少必要文件")
        if any("/.cache/" in name or name.endswith(".metadata") for name in names):
            raise SystemExit("模型扩展包包含本地下载缓存")
        print(f"Model extension SHA256: {model_digest}")


if __name__ == "__main__":
    main()
