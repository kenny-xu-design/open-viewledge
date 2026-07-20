from __future__ import annotations

import os
import tempfile
from pathlib import Path
from urllib.parse import quote, urlencode

from ..utils import UserFacingError, sanitize_filename


def safe_export_filename(value: str) -> str:
    return sanitize_filename(value, "video-note").rstrip(". ")[:100] + ".md"


def write_to_vault(
    markdown: str,
    vault_path: str,
    subdir: str,
    filename: str,
    *,
    overwrite: bool = False,
) -> tuple[Path, str]:
    if not vault_path.strip():
        raise UserFacingError("未配置 OBSIDIAN_VAULT_PATH。")
    vault = Path(vault_path).expanduser().resolve()
    if not vault.is_dir():
        raise UserFacingError("配置的 Obsidian Vault 不存在。")
    relative = Path(subdir.replace("\\", "/").strip("/")) if subdir.strip() else Path()
    if relative.is_absolute() or ".." in relative.parts or any(part.lower() == ".obsidian" for part in relative.parts):
        raise UserFacingError("Obsidian 导出子目录不安全。")
    target_dir = (vault / relative).resolve()
    try:
        target_dir.relative_to(vault)
    except ValueError as exc:
        raise UserFacingError("Obsidian 导出路径越界。") from exc
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / safe_export_filename(Path(filename).stem)
    if not overwrite:
        stem, suffix, counter = target.stem, target.suffix, 2
        while target.exists():
            target = target.with_name(f"{stem} ({counter}){suffix}")
            counter += 1
    handle, temporary_name = tempfile.mkstemp(prefix="obsidian-export-", suffix=".md", dir=target_dir)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as temporary:
            temporary.write(markdown)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, target)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    relative_path = target.relative_to(vault).as_posix()
    return target, build_obsidian_uri(vault.name, relative_path)


def build_obsidian_uri(vault_name: str, relative_file: str) -> str:
    return "obsidian://open?" + urlencode({"vault": vault_name, "file": relative_file}, quote_via=quote)
