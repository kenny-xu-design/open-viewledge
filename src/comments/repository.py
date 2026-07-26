from __future__ import annotations

from pathlib import Path

from ..domain.models import NormalizedComment
from ..timestamps import build_timestamp_target, format_timestamp
from ..utils import save_json, write_text


class CommentRepository:
    def __init__(self, package_dir: Path) -> None:
        self.package_dir = package_dir

    def save(self, comments: list[NormalizedComment]) -> tuple[Path, Path]:
        json_path = self.package_dir / "comments.json"
        md_path = self.package_dir / "comments.md"
        save_json(json_path, {"items": [item.model_dump(mode="json") for item in comments]})
        write_text(md_path, self.render_markdown(comments))
        return json_path, md_path

    def load(self) -> list[NormalizedComment]:
        path = self.package_dir / "comments.json"
        if not path.is_file():
            return []
        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return []
        return [
            NormalizedComment.model_validate(item)
            for item in payload.get("items", [])
            if isinstance(item, dict)
        ]

    def render_markdown(self, comments: list[NormalizedComment]) -> str:
        lines = ["# 评论同步记录", ""]
        if not comments:
            lines.append("未同步到可用评论。")
            return "\n".join(lines).rstrip() + "\n"
        for index, item in enumerate(comments, 1):
            marker = f" @ {item.author}" if item.author else ""
            lines.append(f"## {index}. {item.likes} 赞{marker}")
            if item.timestamps:
                targets = []
                for seconds in item.timestamps:
                    target = build_timestamp_target(item.source_url, seconds)
                    label = format_timestamp(seconds)
                    targets.append(f"[{label}]({target})" if target else label)
                lines.append("时间戳：" + "、".join(targets))
                lines.append("")
            lines.append(item.content)
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"
