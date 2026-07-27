from __future__ import annotations

import os
import re
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

from .domain.models import TranscriptResult, TranscriptSegment
from .providers.asr.local_whisper import LocalWhisperProvider
from .runtime_tools import resolve_executable
from .utils import UserFacingError, run_command

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> bool:
        return False


ASRRoute = Literal["cloud", "local_gpu", "local_cpu"]
LogCallback = Callable[[str], None]


def normalize_asr_route(value: str | None) -> ASRRoute:
    route = str(value or "cloud").strip().lower()
    if route not in {"cloud", "local_gpu", "local_cpu"}:
        raise UserFacingError("asr_route 必须是 cloud、local_gpu 或 local_cpu。")
    return route  # type: ignore[return-value]


class PlatformSubtitleProvider:
    name = "platform"

    def build_result(
        self, segments: list[TranscriptSegment], language: str = "", duration: float = 0
    ) -> TranscriptResult:
        return TranscriptResult(
            provider="platform",
            model="platform-subtitle",
            device="cloud",
            language=language,
            duration_seconds=duration,
            segments=segments,
        )


@dataclass(frozen=True)
class AudioChunk:
    path: Path
    offset_seconds: float
    duration_seconds: float


class GroqASRProvider:
    name = "groq"

    def __init__(
        self,
        config: object,
        *,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.config = config
        self.model_name = str(
            getattr(config, "cloud_asr_model", "whisper-large-v3-turbo")
        )
        self._client_factory = client_factory

    def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None,
        log_callback: LogCallback | None = None,
    ) -> TranscriptResult:
        load_dotenv()
        key = os.getenv("GROQ_API_KEY", "").strip()
        if not key:
            raise UserFacingError("Groq API Key 缺失，请配置 GROQ_API_KEY。")
        chunks = prepare_cloud_audio_chunks(audio_path, self.config)
        client = self._create_client(key)
        started = time.perf_counter()
        all_segments: list[TranscriptSegment] = []
        warnings: list[str] = []
        for chunk in chunks:
            _log(
                log_callback,
                f"上传：{chunk.path.stat().st_size / 1024 / 1024:.1f} MB",
            )
            response = self._request_with_retry(
                client, chunk.path, language=language, log_callback=log_callback
            )
            parsed = _segments_from_groq(response, language or "", chunk.offset_seconds)
            all_segments = merge_overlapping_segments(all_segments, parsed)
        if not all_segments:
            raise UserFacingError("Groq 返回内容为空。")
        elapsed = time.perf_counter() - started
        _log(log_callback, f"转写完成：{elapsed:.1f} 秒")
        _log(log_callback, f"字幕段：{len(all_segments)}")
        return TranscriptResult(
            provider="groq",
            model=self.model_name,
            device="cloud",
            language=language or "",
            duration_seconds=max((item.end for item in all_segments), default=0),
            segments=all_segments,
            warnings=warnings,
        )

    def _create_client(self, key: str) -> Any:
        if self._client_factory:
            return self._client_factory(
                api_key=key,
                base_url="https://api.groq.com/openai/v1",
                timeout=float(getattr(self.config, "cloud_asr_timeout_seconds", 300)),
            )
        from openai import OpenAI

        return OpenAI(
            api_key=key,
            base_url="https://api.groq.com/openai/v1",
            timeout=float(getattr(self.config, "cloud_asr_timeout_seconds", 300)),
        )

    def _request_with_retry(
        self,
        client: Any,
        path: Path,
        *,
        language: str | None,
        log_callback: LogCallback | None,
    ) -> Any:
        retries = int(getattr(self.config, "cloud_asr_max_retries", 2))
        for attempt in range(retries + 1):
            try:
                with path.open("rb") as audio:
                    kwargs: dict[str, Any] = {
                        "file": audio,
                        "model": self.model_name,
                        "response_format": "verbose_json",
                        "timestamp_granularities": ["segment"],
                        "temperature": 0,
                    }
                    if _iso_language(language):
                        kwargs["language"] = language
                    return client.audio.transcriptions.create(**kwargs)
            except Exception as exc:
                message, retryable = classify_groq_error(exc)
                if not retryable or attempt >= retries:
                    raise UserFacingError(f"云端转写失败：{message}") from exc
                _log(log_callback, f"Groq {message}，正在重试 {attempt + 1}/{retries}")
                time.sleep(min(2**attempt, 8))
        raise UserFacingError("云端转写失败。")


class LocalFasterWhisperProvider:
    name = "faster-whisper"

    def __init__(self, config: object, *, device: Literal["cuda", "cpu"], fallback: bool):
        self.provider = LocalWhisperProvider(
            config, device=device, fallback_enabled=fallback
        )
        self.device = device

    def transcribe(self, audio_path: Path, context: object) -> TranscriptResult:
        if not self.provider.is_available():
            raise UserFacingError("本地 faster-whisper 模型不可用。")
        segments = self.provider.transcribe(audio_path, context)
        telemetry = self.provider.telemetry
        return TranscriptResult(
            provider="faster-whisper",
            model=self.provider.model_name,
            device="cuda" if telemetry.device.startswith("cuda") else "cpu",
            language=str(getattr(getattr(context, "config", None), "language", "") or ""),
            duration_seconds=telemetry.audio_duration_seconds,
            segments=segments,
            warnings=list(telemetry.fallback_messages),
        )


class TranscriptionRouter:
    def __init__(
        self,
        config: object,
        *,
        route: str = "cloud",
        fallback_enabled: bool = True,
        cloud_provider: Any | None = None,
        local_provider_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.config = config
        self.route = normalize_asr_route(route)
        self.fallback_enabled = bool(fallback_enabled)
        self.cloud_provider = cloud_provider or GroqASRProvider(config)
        self.local_provider_factory = local_provider_factory or LocalFasterWhisperProvider

    def _local_attempts(
        self, audio: Path, context: object, *, include_cpu: bool
    ) -> list[tuple[str, Callable[[], TranscriptResult]]]:
        items = [("本地 GPU", lambda: self._local("cuda", False, audio, context))]
        if include_cpu:
            items.append(("本地 CPU", lambda: self._local("cpu", False, audio, context)))
        return items

    def _local(self, device: str, fallback: bool, audio: Path, context: object) -> TranscriptResult:
        provider = self.local_provider_factory(
            self.config, device=device, fallback=fallback
        )
        return provider.transcribe(audio, context)

    def transcribe(self, audio_path: Path, context: object) -> TranscriptResult:
        log = getattr(context, "log", None)
        language = str(getattr(self.config, "language", "") or "") or None
        if self.route == "cloud":
            attempts = [("Groq", lambda: self.cloud_provider.transcribe(
                audio_path, language=language, log_callback=log
            ))]
            if self.fallback_enabled:
                attempts += self._local_attempts(audio_path, context, include_cpu=True)
        elif self.route == "local_gpu":
            attempts = self._local_attempts(
                audio_path, context, include_cpu=self.fallback_enabled
            )
        else:
            attempts = [("本地 CPU", lambda: self._local("cpu", False, audio_path, context))]
        errors: list[str] = []
        for index, (label, operation) in enumerate(attempts):
            try:
                result = operation()
                result.fallback_used = index > 0
                result.warnings = errors + result.warnings
                return result
            except Exception as exc:
                message = _safe_message(exc)
                errors.append(f"{label}：{message}")
                _log(log, f"{label}失败：{message}")
                if index + 1 < len(attempts):
                    _log(log, f"已回退{attempts[index + 1][0]}")
        raise UserFacingError("转写失败：" + "；".join(errors))


def prepare_cloud_audio_chunks(audio_path: Path, config: object) -> list[AudioChunk]:
    if not audio_path.is_file():
        raise UserFacingError("待转写音频不存在。")
    duration = _wav_duration(audio_path)
    limit = int(float(getattr(config, "cloud_asr_file_limit_mb", 25)) * 1024 * 1024)
    overlap = float(getattr(config, "cloud_asr_chunk_overlap_seconds", 2))
    chunk_dir = audio_path.parent / "cloud_asr_chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    normalized = chunk_dir / "audio_16k.flac"
    _convert_audio(audio_path, normalized, config)
    if normalized.stat().st_size <= limit:
        return [AudioChunk(normalized, 0, duration)]
    target_duration = max(1.0, duration * (limit * 0.9 / normalized.stat().st_size))
    chunks: list[AudioChunk] = []
    start = 0.0
    index = 0
    while start < duration:
        length = min(target_duration, duration - start)
        path = chunk_dir / f"chunk_{index:04d}.flac"
        _convert_audio(audio_path, path, config, start=start, duration=length)
        chunks.append(AudioChunk(path, start, length))
        if start + length >= duration:
            break
        start += max(1.0, length - overlap)
        index += 1
    return chunks


def merge_overlapping_segments(
    existing: list[TranscriptSegment], incoming: list[TranscriptSegment]
) -> list[TranscriptSegment]:
    result = list(existing)
    for segment in incoming:
        duplicate = next(
            (
                old for old in reversed(result[-8:])
                if _normalized_text(old.text) == _normalized_text(segment.text)
                and segment.start <= old.end + 2.5
            ),
            None,
        )
        if duplicate:
            duplicate.end = max(duplicate.end, segment.end)
            continue
        segment.index = len(result)
        result.append(segment)
    return result


def _segments_from_groq(response: Any, language: str, offset: float) -> list[TranscriptSegment]:
    raw = getattr(response, "segments", None)
    if raw is None and isinstance(response, dict):
        raw = response.get("segments")
    segments: list[TranscriptSegment] = []
    for item in raw or []:
        get = item.get if isinstance(item, dict) else lambda key, default=None: getattr(item, key, default)
        text = str(get("text", "") or "").strip()
        if not text:
            continue
        segments.append(TranscriptSegment(
            index=len(segments),
            start=offset + float(get("start", 0) or 0),
            end=offset + float(get("end", 0) or 0),
            text=text,
            language=language,
            source="groq",
            avg_logprob=get("avg_logprob"),
            compression_ratio=get("compression_ratio"),
            no_speech_prob=get("no_speech_prob"),
        ))
    return segments


def classify_groq_error(exc: Exception) -> tuple[str, bool]:
    status = getattr(exc, "status_code", None)
    text = str(exc).lower()
    if status == 401:
        return "鉴权失败（401）", False
    if status == 413:
        return "文件过大（413）", False
    if status == 429:
        return "请求限流（429）", True
    if status and int(status) >= 500:
        return f"服务异常（{status}）", True
    if "timeout" in text or "timed out" in text:
        return "请求超时", True
    if "json" in text or "decode" in text:
        return "响应解析失败", False
    return "网络或服务请求异常", True


def _convert_audio(
    source: Path, target: Path, config: object, *, start: float = 0, duration: float | None = None
) -> None:
    ffmpeg = resolve_executable("ffmpeg", getattr(config, "ffmpeg_path", ""))
    args = [ffmpeg, "-y"]
    if start:
        args += ["-ss", f"{start:.3f}"]
    args += ["-i", str(source), "-vn", "-ac", "1", "-ar", "16000"]
    if duration is not None:
        args += ["-t", f"{duration:.3f}"]
    args += ["-c:a", "flac", str(target)]
    run_command(args)
    if not target.is_file():
        raise UserFacingError("FFmpeg 未能生成云端转写音频。")


def _wav_duration(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as audio:
            return audio.getnframes() / max(audio.getframerate(), 1)
    except (wave.Error, OSError):
        return 0.0


def _iso_language(language: str | None) -> bool:
    return bool(language and re.fullmatch(r"[a-z]{2}", language.lower()))


def _normalized_text(text: str) -> str:
    return re.sub(r"\W+", "", text, flags=re.UNICODE).lower()


def _safe_message(exc: Exception) -> str:
    message = str(exc)
    message = re.sub(r"(?i)(api[_ -]?key|authorization)\s*[:=]\s*\S+", r"\1=[已隐藏]", message)
    message = re.sub(
        r"[A-Za-z]:\\(?:[^\\\s]+\\)+", lambda _: "[本地路径]\\", message
    )
    return message[:300]


def _log(callback: LogCallback | None, message: str) -> None:
    if callback:
        callback(message)
