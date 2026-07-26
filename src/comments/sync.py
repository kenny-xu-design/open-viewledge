from __future__ import annotations

from dataclasses import dataclass

from ..domain.models import NormalizedComment, SourceRecord
from .adapters import BilibiliCommentAdapter, YouTubeCommentAdapter, YtdlpCommentAdapter


@dataclass(frozen=True)
class CommentSyncResult:
    status: str
    comments: list[NormalizedComment]
    mode: str
    sort: str
    limit: int
    message: str = ""


class CommentSyncService:
    def __init__(
        self,
        *,
        youtube_adapter: YtdlpCommentAdapter | None = None,
        bilibili_adapter: YtdlpCommentAdapter | None = None,
        generic_adapter: YtdlpCommentAdapter | None = None,
    ) -> None:
        self.youtube_adapter = youtube_adapter or YouTubeCommentAdapter()
        self.bilibili_adapter = bilibili_adapter or BilibiliCommentAdapter()
        self.generic_adapter = generic_adapter or YtdlpCommentAdapter()

    def sync(
        self,
        source: SourceRecord,
        *,
        processing_profile: str,
        enabled: bool,
        existing: list[NormalizedComment] | None = None,
    ) -> CommentSyncResult:
        mode = "fast" if processing_profile == "fast" else "complete"
        if not enabled:
            return CommentSyncResult("skipped", [], mode, "top", 0, "评论同步未启用。")
        if source.source_type != "online_video":
            return CommentSyncResult("skipped", [], mode, "top", 0, "本地媒体不支持公开评论同步。")
        limit = 30 if mode == "fast" else 120
        sort = "top" if mode == "fast" else "top+latest"
        adapter = self._adapter_for(source)
        if mode == "fast":
            comments = adapter.fetch(source, limit=limit, sort="top")
        else:
            comments = [
                *adapter.fetch(source, limit=limit // 2, sort="top"),
                *adapter.fetch(source, limit=limit // 2, sort="latest"),
                *(existing or []),
            ]
            comments = _merge_comments(comments, limit)
        if not comments:
            return CommentSyncResult("skipped", [], mode, sort, limit, "未同步到公开评论。")
        return CommentSyncResult("success", comments, mode, sort, limit)

    def _adapter_for(self, source: SourceRecord) -> YtdlpCommentAdapter:
        if source.platform == "youtube":
            return self.youtube_adapter
        if source.platform == "bilibili":
            return self.bilibili_adapter
        return self.generic_adapter


def _merge_comments(comments: list[NormalizedComment], limit: int) -> list[NormalizedComment]:
    by_id: dict[str, NormalizedComment] = {}
    for item in comments:
        by_id[item.comment_id] = item
    return sorted(
        by_id.values(),
        key=lambda item: (item.is_pinned, item.likes, item.reply_count, item.published_at or item.fetched_at),
        reverse=True,
    )[:limit]
