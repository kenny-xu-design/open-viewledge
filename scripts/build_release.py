from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.5.0"
PRODUCT_DIR = f"Viewledge-v{VERSION}"
BASE_ZIP = f"Viewledge-v{VERSION}-windows.zip"
MODEL_ZIP = "Viewledge-local-asr-small-model.zip"

TOP_LEVEL_FILES = (
    ".env.example",
    "CHANGELOG.md",
    "COMMERCIAL-LICENSE.md",
    "COPYRIGHT",
    "KNOWN_LIMITATIONS.md",
    "LICENSE",
    "NOTICE",
    "README.md",
    "README-本地GPU可选配置.md",
    "README-零基础使用.md",
    "config.example.json",
    "requirements.lock.txt",
    "requirements.txt",
    "start_web.bat",
)
TREE_DIRS = ("src", "prompts", "tools")
TEXT_SUFFIXES = {".bat", ".css", ".html", ".ini", ".js", ".json", ".md", ".py", ".txt", ".yaml", ".yml"}
FORBIDDEN_PARTS = {
    ".env",
    ".git",
    ".local",
    ".venv",
    "__pycache__",
    "output",
    "release",
    "start_dev.bat",
}
FORBIDDEN_BINARY_NAMES = re.compile(
    r"(?i)(?:cublas|cudnn|cufft|curand|cusolver|cusparse|nvrtc|nvidia).*\.(?:dll|exe|lib|pyd)$"
)
SECRET_PATTERNS = (
    re.compile(r"\bgsk_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{30,}\b"),
    re.compile(r"(?i)(?:authorization|cookie|api[_-]?key)\s*[:=]\s*[\"']?[A-Za-z0-9_-]{24,}"),
)
PRIVATE_PATH_PATTERNS = (
    re.compile(r"(?i)E:\\AGT\\"),
    re.compile(r"(?i)C:\\Users\\26378\\"),
    re.compile(r"(?i)\\.codex[\\/]"),
)


def copy_tree(source: Path, destination: Path) -> None:
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns(
            "__pycache__",
            "*.pyc",
            "*.pyo",
            ".DS_Store",
            "Thumbs.db",
            "ffmpeg.exe",
            "ffprobe.exe",
        ),
    )


def validate_source(ffmpeg_bin: Path) -> None:
    required = (
        ffmpeg_bin / "ffmpeg.exe",
        ffmpeg_bin / "ffprobe.exe",
        ROOT / "tools/licenses/ffmpeg/LICENSE.txt",
        ROOT / "tools/licenses/ffmpeg/BUILD_INFO.txt",
        ROOT / "tools/licenses/ffmpeg/SOURCE.txt",
    )
    missing = []
    for path in required:
        if path.is_file():
            continue
        try:
            missing.append(str(path.relative_to(ROOT)))
        except ValueError:
            missing.append(str(path))
    if missing:
        raise SystemExit("发行依赖缺失：" + "、".join(missing))
    version_text = (ROOT / "src/__init__.py").read_text(encoding="utf-8")
    if f'__version__ = "{VERSION}"' not in version_text:
        raise SystemExit(f"src/__init__.py 版本号不是 {VERSION}")


def scan_release(root: Path) -> None:
    problems: list[str] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        lowered_parts = {part.lower() for part in relative.parts}
        if lowered_parts & {part.lower() for part in FORBIDDEN_PARTS}:
            problems.append(f"禁止内容：{relative}")
            continue
        if path.is_file() and FORBIDDEN_BINARY_NAMES.search(path.name):
            problems.append(f"NVIDIA 运行库：{relative}")
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8", errors="replace")
            if any(pattern.search(text) for pattern in SECRET_PATTERNS):
                problems.append(f"疑似凭据：{relative}")
            if any(pattern.search(text) for pattern in PRIVATE_PATH_PATTERNS):
                problems.append(f"开发机路径：{relative}")
    if problems:
        raise SystemExit("发行扫描失败：\n" + "\n".join(problems))


def write_zip(source_root: Path, zip_path: Path, prefix: str) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(source_root.rglob("*")):
            if path.is_file():
                archive.write(path, (Path(prefix) / path.relative_to(source_root)).as_posix())


def write_sha256(path: Path) -> Path:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    sidecar = path.with_suffix(path.suffix + ".sha256")
    sidecar.write_text(f"{digest.hexdigest()}  {path.name}\n", encoding="ascii")
    return sidecar


def build_base(output: Path, ffmpeg_bin: Path) -> Path:
    with tempfile.TemporaryDirectory(prefix="viewledge-release-") as temp:
        stage = Path(temp) / PRODUCT_DIR
        stage.mkdir()
        for name in TOP_LEVEL_FILES:
            shutil.copy2(ROOT / name, stage / name)
        for name in TREE_DIRS:
            copy_tree(ROOT / name, stage / name)
        bundled_bin = stage / "tools/ffmpeg/bin"
        bundled_bin.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ffmpeg_bin / "ffmpeg.exe", bundled_bin / "ffmpeg.exe")
        shutil.copy2(ffmpeg_bin / "ffprobe.exe", bundled_bin / "ffprobe.exe")
        models = stage / "models"
        models.mkdir()
        (models / "README.txt").write_text(
            "基础包不包含本地 ASR 模型。将模型扩展包解压到 Viewledge 根目录即可安装。\n",
            encoding="utf-8",
        )
        scan_release(stage)
        zip_path = output / BASE_ZIP
        write_zip(stage, zip_path, PRODUCT_DIR)
    write_sha256(zip_path)
    return zip_path


def build_model(output: Path) -> Path | None:
    source = ROOT / "models/faster-whisper-small"
    required = ("config.json", "model.bin", "tokenizer.json")
    if not all((source / name).is_file() for name in required):
        return None
    with tempfile.TemporaryDirectory(prefix="viewledge-model-") as temp:
        stage = Path(temp) / "models" / "faster-whisper-small"
        stage.mkdir(parents=True)
        for path in source.iterdir():
            if path.is_file() and path.name not in {".gitattributes"}:
                shutil.copy2(path, stage / path.name)
        zip_path = output / MODEL_ZIP
        write_zip(Path(temp), zip_path, "")
    write_sha256(zip_path)
    return zip_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Viewledge portable Windows release.")
    parser.add_argument("--output", type=Path, default=ROOT / "release")
    parser.add_argument(
        "--ffmpeg-bin",
        type=Path,
        default=ROOT / "tools/ffmpeg/bin",
        help="Directory containing the verified ffmpeg.exe and ffprobe.exe build inputs.",
    )
    parser.add_argument("--skip-model", action="store_true")
    args = parser.parse_args()
    ffmpeg_bin = args.ffmpeg_bin.resolve()
    validate_source(ffmpeg_bin)
    args.output.mkdir(parents=True, exist_ok=True)
    base = build_base(args.output, ffmpeg_bin)
    print(f"Base release: {base}")
    if not args.skip_model:
        model = build_model(args.output)
        print(f"Model extension: {model or 'not built (local model missing)'}")


if __name__ == "__main__":
    main()
