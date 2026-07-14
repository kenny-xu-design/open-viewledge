from .base import AdapterResult
from .bilibili_adapter import BilibiliAdapter, is_bilibili_url
from .local_file_adapter import LocalFileAdapter
from .ytdlp_adapter import YtdlpAdapter

__all__ = [
    "AdapterResult",
    "BilibiliAdapter",
    "LocalFileAdapter",
    "YtdlpAdapter",
    "is_bilibili_url",
]
