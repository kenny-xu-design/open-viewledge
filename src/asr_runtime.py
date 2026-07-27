from __future__ import annotations

import gc
import multiprocessing
import os
import queue
import re
import subprocess
import threading
import time
import wave
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

from .domain.models import TranscriptSegment
from .utils import ConfigRequiredError, UserFacingError


ASRProfile = Literal["fast", "balanced", "quality"]
LogCallback = Callable[[str], None]
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "small"
DEFAULT_TEMPERATURE_FALLBACK = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
_CUDA_OOM_MARKERS = (
    "out of memory",
    "cuda_error_out_of_memory",
    "cublas_status_alloc_failed",
    "cuda out of memory",
)
_CUDA_FAILURE_MARKERS = (
    "cuda",
    "cublas",
    "cudnn",
    "cufft",
    "driver",
)
_CUDA_RUNTIME_MISSING_MARKERS = (
    "library cublas",
    "library cudnn",
    "cublas64_",
    "cudnn64_",
    ".dll is not found",
)
DEFAULT_GPU_DETECT_TIMEOUT_SECONDS = 5.0
DEFAULT_GPU_MODEL_LOAD_TIMEOUT_SECONDS = 45.0
DEFAULT_GPU_FIRST_BATCH_TIMEOUT_SECONDS = 45.0
DEFAULT_TRANSCRIBE_STALL_TIMEOUT_SECONDS = 120.0
DEFAULT_RESOURCE_WAIT_TIMEOUT_SECONDS = 300.0
REQUIRED_MODEL_FILES = ("config.json", "model.bin", "tokenizer.json")
_WINDOWS_CUDA_DLL_HANDLES: list[Any] = []


def _configure_windows_cuda_dll_directories() -> None:
    if os.name != "nt" or not hasattr(os, "add_dll_directory"):
        return
    import ctypes

    site_packages = Path(os.sys.prefix) / "Lib" / "site-packages"
    directories = (
        site_packages / "nvidia" / "cublas" / "bin",
        site_packages / "nvidia" / "cudnn" / "bin",
        site_packages / "ctranslate2",
    )
    for directory in directories:
        if not directory.is_dir():
            continue
        try:
            _WINDOWS_CUDA_DLL_HANDLES.append(os.add_dll_directory(str(directory)))
        except OSError:
            continue
    for dll_name in (
        "cublas64_12.dll",
        "cublasLt64_12.dll",
        "cudnn64_9.dll",
        "cudnn_ops64_9.dll",
    ):
        try:
            _WINDOWS_CUDA_DLL_HANDLES.append(ctypes.WinDLL(dll_name))
        except OSError:
            continue


_configure_windows_cuda_dll_directories()


@dataclass(frozen=True)
class ASRSettings:
    profile: ASRProfile = "balanced"
    model: str = ""
    device: str = ""
    compute_type: str = ""
    task: str = "transcribe"
    logprob_threshold: float = -1.0
    compression_ratio_threshold: float = 2.4
    no_speech_threshold: float = 0.6
    language_probability_threshold: float = 0.5
    low_confidence_ratio_threshold: float = 0.2
    gap_retry_seconds: float = 30.0
    max_local_retries: int = 8
    fallback_enabled: bool = True
    gpu_detect_timeout_seconds: float = DEFAULT_GPU_DETECT_TIMEOUT_SECONDS
    gpu_model_load_timeout_seconds: float = DEFAULT_GPU_MODEL_LOAD_TIMEOUT_SECONDS
    gpu_first_batch_timeout_seconds: float = DEFAULT_GPU_FIRST_BATCH_TIMEOUT_SECONDS
    transcribe_stall_timeout_seconds: float = DEFAULT_TRANSCRIBE_STALL_TIMEOUT_SECONDS
    resource_wait_timeout_seconds: float = DEFAULT_RESOURCE_WAIT_TIMEOUT_SECONDS

    @classmethod
    def from_config(cls, config: object | None) -> "ASRSettings":
        if config is None:
            return cls()
        legacy_model = str(getattr(config, "whisper_model", "") or "").strip()
        explicit_model = str(getattr(config, "asr_model", "") or "").strip()
        if not explicit_model and legacy_model and legacy_model != DEFAULT_MODEL:
            explicit_model = legacy_model
        return cls(
            profile=str(getattr(config, "asr_profile", "balanced") or "balanced"),  # type: ignore[arg-type]
            model=explicit_model,
            device=str(getattr(config, "asr_device", "") or "").strip(),
            compute_type=str(getattr(config, "asr_compute_type", "") or "").strip(),
            task=str(getattr(config, "asr_task", "transcribe") or "transcribe").strip(),
            logprob_threshold=float(getattr(config, "asr_logprob_threshold", -1.0)),
            compression_ratio_threshold=float(getattr(config, "asr_compression_ratio_threshold", 2.4)),
            no_speech_threshold=float(getattr(config, "asr_no_speech_threshold", 0.6)),
            language_probability_threshold=float(
                getattr(config, "asr_language_probability_threshold", 0.5)
            ),
            low_confidence_ratio_threshold=float(
                getattr(config, "asr_low_confidence_ratio_threshold", 0.2)
            ),
            gap_retry_seconds=float(getattr(config, "asr_gap_retry_seconds", 30.0)),
            max_local_retries=int(getattr(config, "asr_max_local_retries", 8)),
            fallback_enabled=bool(getattr(config, "asr_fallback_enabled", True)),
            gpu_detect_timeout_seconds=float(
                getattr(config, "asr_gpu_detect_timeout_seconds", DEFAULT_GPU_DETECT_TIMEOUT_SECONDS)
            ),
            gpu_model_load_timeout_seconds=float(
                getattr(config, "asr_gpu_model_load_timeout_seconds", DEFAULT_GPU_MODEL_LOAD_TIMEOUT_SECONDS)
            ),
            gpu_first_batch_timeout_seconds=float(
                getattr(config, "asr_gpu_first_batch_timeout_seconds", DEFAULT_GPU_FIRST_BATCH_TIMEOUT_SECONDS)
            ),
            transcribe_stall_timeout_seconds=float(
                getattr(config, "asr_transcribe_stall_timeout_seconds", DEFAULT_TRANSCRIBE_STALL_TIMEOUT_SECONDS)
            ),
            resource_wait_timeout_seconds=float(
                getattr(config, "asr_resource_wait_timeout_seconds", DEFAULT_RESOURCE_WAIT_TIMEOUT_SECONDS)
            ),
        )


@dataclass(frozen=True)
class CudaProbe:
    device_count: int = 0
    compute_types: frozenset[str] = frozenset()
    device_index: int = 0
    device_name: str = ""
    total_memory_gb: float | None = None
    free_memory_gb: float | None = None
    memory_source: str = ""
    error: str = ""

    @property
    def available(self) -> bool:
        return self.device_count > self.device_index


@dataclass(frozen=True)
class ASRCandidate:
    model: str
    device: Literal["cuda", "cpu"]
    compute_type: str
    batch_size: int
    beam_size: int
    device_index: int = 0
    vad_filter: bool = True
    word_timestamps: bool = False
    explicit: bool = False

    @property
    def device_label(self) -> str:
        return f"cuda:{self.device_index}" if self.device == "cuda" else "cpu"

    @property
    def short_label(self) -> str:
        return f"{self.model} {self.device.upper()} {self.compute_type.upper()}"


@dataclass
class ASRTelemetry:
    profile: str
    model: str = ""
    device: str = ""
    compute_type: str = ""
    batch_size: int = 1
    beam_size: int = 1
    audio_duration_seconds: float = 0.0
    model_load_seconds: float = 0.0
    transcription_seconds: float = 0.0
    rtf: float = 0.0
    low_confidence_segments: int = 0
    local_retries: int = 0
    unresolved_gaps: int = 0
    fallback_messages: list[str] = field(default_factory=list)


@dataclass
class ASROutcome:
    segments: list[TranscriptSegment]
    telemetry: ASRTelemetry


def asr_cache_dimensions(config: object | None) -> dict[str, Any]:
    settings = ASRSettings.from_config(config)
    return {
        "asr_profile": settings.profile,
        "asr_model_override": settings.model,
        "asr_device_override": settings.device,
        "asr_compute_type_override": settings.compute_type,
        "asr_task": settings.task,
        "quality_thresholds": {
            "logprob": settings.logprob_threshold,
            "compression_ratio": settings.compression_ratio_threshold,
            "no_speech": settings.no_speech_threshold,
            "language_probability": settings.language_probability_threshold,
            "low_confidence_ratio": settings.low_confidence_ratio_threshold,
            "gap_retry_seconds": settings.gap_retry_seconds,
            "max_local_retries": settings.max_local_retries,
        },
    }


def has_local_asr_model(
    config: object | None = None,
    *,
    project_root: Path = PROJECT_ROOT,
) -> bool:
    settings = ASRSettings.from_config(config)
    names = [settings.model] if settings.model else [DEFAULT_MODEL, "turbo", "large-v3"]
    for name in names:
        try:
            _model_reference(name, project_root)
        except UserFacingError:
            continue
        return True
    return False


def probe_cuda() -> CudaProbe:
    try:
        import ctranslate2

        count = int(ctranslate2.get_cuda_device_count())
        compute_types = (
            frozenset(str(item) for item in ctranslate2.get_supported_compute_types("cuda"))
            if count
            else frozenset()
        )
    except Exception as exc:
        return CudaProbe(error=_safe_error(exc))
    if count <= 0:
        return CudaProbe(device_count=0, compute_types=compute_types)

    memory = _query_nvidia_smi_memory(0)
    return CudaProbe(
        device_count=count,
        compute_types=compute_types,
        device_index=0,
        device_name=memory[0],
        total_memory_gb=memory[1],
        free_memory_gb=memory[2],
        memory_source=memory[3],
        error=memory[4],
    )


def _probe_cuda_worker(results: Any) -> None:
    try:
        results.put(("ok", probe_cuda()))
    except BaseException as exc:
        results.put(("error", _safe_error(exc)))


def _probe_cuda_bounded(timeout_seconds: float) -> CudaProbe:
    context = multiprocessing.get_context("spawn")
    results = context.Queue(maxsize=1)
    process = context.Process(target=_probe_cuda_worker, args=(results,))
    process.start()
    process.join(timeout_seconds)
    try:
        if process.is_alive():
            process.terminate()
            process.join(2)
            if process.is_alive():
                process.kill()
                process.join(2)
            return CudaProbe(error=f"CUDA 检测超过 {timeout_seconds:.0f} 秒，已终止")
        try:
            status, value = results.get(timeout=1)
        except queue.Empty:
            return CudaProbe(error=f"CUDA 检测进程异常退出（code={process.exitcode}）")
        if status == "ok" and isinstance(value, CudaProbe):
            return value
        return CudaProbe(error=str(value))
    finally:
        results.close()
        results.join_thread()


def build_asr_candidates(settings: ASRSettings, probe: CudaProbe) -> list[ASRCandidate]:
    defaults = _profile_candidates(settings, probe)
    candidates: list[ASRCandidate] = []
    if settings.model or settings.device or settings.compute_type:
        base = defaults[0]
        model = settings.model or base.model
        if settings.task == "translate" and _is_turbo(model):
            model = DEFAULT_MODEL
        device, device_index = _parse_device(settings.device or base.device_label)
        if device == "cuda" and not probe.available and settings.fallback_enabled:
            device = "cpu"
            device_index = 0
        compute_type = settings.compute_type or (
            base.compute_type if device == base.device else ("int8" if device == "cpu" else "float16")
        )
        candidates.append(
            ASRCandidate(
                model=model,
                device=device,
                device_index=device_index,
                compute_type=compute_type,
                batch_size=_batch_size(settings.profile, probe.free_memory_gb, device),
                beam_size=_beam_size(settings.profile),
                explicit=True,
            )
        )
    if settings.fallback_enabled or not candidates:
        candidates.extend(defaults)
    return _deduplicate_candidates(candidates, probe)


def _profile_candidates(settings: ASRSettings, probe: CudaProbe) -> list[ASRCandidate]:
    result: list[ASRCandidate] = []
    memory = probe.free_memory_gb
    if probe.available:
        if settings.profile == "fast":
            result.append(
                ASRCandidate(
                    DEFAULT_MODEL,
                    "cuda",
                    "float16",
                    _batch_size("fast", memory, "cuda"),
                    1,
                    probe.device_index,
                )
            )
            result.append(
                ASRCandidate(DEFAULT_MODEL, "cuda", "int8_float16", 4, 1, probe.device_index)
            )
        elif settings.profile == "quality":
            if memory is None or memory >= 8:
                result.append(
                    ASRCandidate(
                        "large-v3",
                        "cuda",
                        "float16",
                        _batch_size("quality", memory, "cuda"),
                        5,
                        probe.device_index,
                    )
                )
            if settings.task != "translate":
                result.append(
                    ASRCandidate(
                        "turbo",
                        "cuda",
                        "float16",
                        _batch_size("quality", memory, "cuda"),
                        5,
                        probe.device_index,
                    )
                )
            result.append(
                ASRCandidate(
                    DEFAULT_MODEL,
                    "cuda",
                    "float16",
                    _batch_size("quality", memory, "cuda"),
                    5,
                    probe.device_index,
                )
            )
            result.append(
                ASRCandidate(DEFAULT_MODEL, "cuda", "int8_float16", 2, 5, probe.device_index)
            )
        else:
            if (memory is None or memory >= 8) and settings.task != "translate":
                result.append(
                    ASRCandidate("turbo", "cuda", "float16", 8, 3, probe.device_index)
                )
            if memory is None or memory >= 4:
                result.append(
                    ASRCandidate(DEFAULT_MODEL, "cuda", "float16", 8, 3, probe.device_index)
                )
            result.append(
                ASRCandidate(DEFAULT_MODEL, "cuda", "int8_float16", 4, 2, probe.device_index)
            )
    result.append(
        ASRCandidate(
            DEFAULT_MODEL,
            "cpu",
            "int8",
            1,
            1 if settings.profile != "quality" else 5,
        )
    )
    return result


def _deduplicate_candidates(
    candidates: list[ASRCandidate],
    probe: CudaProbe,
) -> list[ASRCandidate]:
    result: list[ASRCandidate] = []
    seen: set[tuple[str, str, str, int]] = set()
    for candidate in candidates:
        if candidate.device == "cuda":
            if not probe.available:
                continue
            if probe.compute_types and candidate.compute_type not in probe.compute_types:
                continue
        key = (
            candidate.model.lower(),
            candidate.device,
            candidate.compute_type.lower(),
            candidate.device_index,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    if not any(item.device == "cpu" for item in result):
        result.append(ASRCandidate(DEFAULT_MODEL, "cpu", "int8", 1, 1))
    return result


def _parse_device(value: str) -> tuple[Literal["cuda", "cpu"], int]:
    normalized = value.strip().lower()
    if normalized.startswith("cuda"):
        _, _, suffix = normalized.partition(":")
        return "cuda", int(suffix) if suffix.isdigit() else 0
    return "cpu", 0


def _batch_size(profile: str, free_memory_gb: float | None, device: str) -> int:
    if device == "cpu":
        return 1
    if profile == "fast":
        if free_memory_gb is None or free_memory_gb >= 12:
            return 16
        if free_memory_gb >= 8:
            return 8
        if free_memory_gb >= 6:
            return 4
        return 2
    if profile == "quality":
        if free_memory_gb is None or free_memory_gb >= 12:
            return 8
        if free_memory_gb >= 6:
            return 4
        return 2
    return 8 if free_memory_gb is None or free_memory_gb >= 4 else 4


def _beam_size(profile: str) -> int:
    if profile == "quality":
        return 5
    if profile == "balanced":
        return 3
    return 1


class LocalASREngine:
    def __init__(self, *, project_root: Path = PROJECT_ROOT) -> None:
        self.project_root = project_root
        self._model_key: tuple[str, str, int, str] | None = None
        self._model: Any | None = None
        self._model_lock = threading.RLock()
        self._concurrency = threading.BoundedSemaphore(1)
        self._gpu_preflight_results: dict[
            tuple[str, int, str], tuple[str, int | str]
        ] = {}

    def transcribe(
        self,
        audio_path: Path,
        *,
        settings: ASRSettings,
        language: str | None,
        source: str,
        log_callback: LogCallback | None = None,
        cuda_probe: CudaProbe | None = None,
    ) -> ASROutcome:
        if not audio_path.is_file():
            raise UserFacingError(f"音频文件不存在：{audio_path}")
        explicit_cpu = settings.device.strip().lower().split(":", 1)[0] == "cpu"
        probe = cuda_probe or (
            CudaProbe()
            if explicit_cpu
            else _probe_cuda_bounded(settings.gpu_detect_timeout_seconds)
        )
        candidates = build_asr_candidates(settings, probe)
        duration = _audio_duration(audio_path)
        _log(log_callback, f"ASR Profile：{settings.profile}")
        if probe.available:
            memory = (
                f"，可用显存 {probe.free_memory_gb:.1f}GB"
                if probe.free_memory_gb is not None
                else ""
            )
            _log(
                log_callback,
                f"CUDA 探测：CTranslate2 设备 {probe.device_count} 个"
                f"（{probe.device_name or 'cuda:0'}{memory}）",
            )
        else:
            detail = f"：{probe.error}" if probe.error else ""
            _log(log_callback, f"CUDA 不可用{detail}")
            _log(log_callback, "→ 已切换 small CPU INT8")
        _log(log_callback, f"音频时长：{_format_duration(duration)}")

        errors: list[str] = []
        cuda_disabled_reason = ""
        _log(log_callback, "等待本地转写资源")
        if not self._concurrency.acquire(timeout=settings.resource_wait_timeout_seconds):
            raise TimeoutError("等待本地转写资源超时。")
        try:
            with _cross_process_asr_lock(
                self.project_root,
                timeout_seconds=settings.resource_wait_timeout_seconds,
            ):
                return self._transcribe_locked(
                    audio_path,
                    candidates=candidates,
                    settings=settings,
                    language=language,
                    source=source,
                    duration=duration,
                    log_callback=log_callback,
                )
        finally:
            self._concurrency.release()

    def _transcribe_locked(
        self,
        audio_path: Path,
        *,
        candidates: list[ASRCandidate],
        settings: ASRSettings,
        language: str | None,
        source: str,
        duration: float,
        log_callback: LogCallback | None,
    ) -> ASROutcome:
        errors: list[str] = []
        cuda_disabled_reason = ""
        try:
            for index, candidate in enumerate(candidates):
                if candidate.device == "cuda" and cuda_disabled_reason:
                    continue
                try:
                    outcome = self._run_candidate(
                        audio_path,
                        candidate,
                        settings=settings,
                        language=language,
                        source=source,
                        duration=duration,
                        log_callback=log_callback,
                    )
                    outcome.telemetry.fallback_messages.extend(errors)
                    return outcome
                except Exception as exc:
                    message = _safe_error(exc)
                    errors.append(f"{candidate.short_label}：{message}")
                    phase = "推理失败" if _is_cuda_failure(exc) else "加载失败"
                    _log(log_callback, f"{candidate.short_label} {phase}：{message}")
                    if candidate.device == "cuda":
                        self._release_model()
                        if _is_cuda_runtime_missing(exc):
                            cuda_disabled_reason = message
                    next_candidate = next(
                        (
                            item
                            for item in candidates[index + 1 :]
                            if not (cuda_disabled_reason and item.device == "cuda")
                        ),
                        None,
                    )
                    if next_candidate is not None:
                        _log(log_callback, f"→ 已切换 {next_candidate.short_label}")
        finally:
            if errors:
                self._release_model()
        raise UserFacingError("本地 faster-whisper 转写失败：" + "；".join(errors[-3:]))

    def _run_candidate(
        self,
        audio_path: Path,
        candidate: ASRCandidate,
        *,
        settings: ASRSettings,
        language: str | None,
        source: str,
        duration: float,
        log_callback: LogCallback | None,
    ) -> ASROutcome:
        initial_batch_size = candidate.batch_size
        if candidate.device == "cuda":
            initial_batch_size = self._ensure_gpu_preflight(
                audio_path,
                candidate,
                language=language,
                task=settings.task,
                timeout_seconds=settings.gpu_first_batch_timeout_seconds,
            )
            if initial_batch_size < candidate.batch_size:
                _log(
                    log_callback,
                    f"CUDA OOM 预检：批大小 {candidate.batch_size} → "
                    f"{initial_batch_size}",
                )
        model, load_seconds, reused = self._load_model(candidate)
        _log(log_callback, f"ASR 模型：{candidate.model}")
        _log(log_callback, f"ASR 设备：{candidate.device_label}")
        _log(log_callback, f"计算精度：{candidate.compute_type}")
        _log(log_callback, f"批大小：{initial_batch_size}")
        _log(log_callback, f"Beam size：{candidate.beam_size}")
        _log(
            log_callback,
            "模型复用：已复用进程内实例" if reused else f"模型加载：{load_seconds:.1f} 秒",
        )

        batch_size = max(1, initial_batch_size)
        transcription_started = time.perf_counter()
        while True:
            try:
                raw_segments, info = self._infer(
                    model,
                    audio_path,
                    candidate,
                    batch_size=batch_size,
                    language=language,
                    task=settings.task,
                    log_callback=log_callback,
                    duration=duration,
                )
                break
            except Exception as exc:
                if _is_oom(exc) and batch_size > 1:
                    next_batch = max(1, batch_size // 2)
                    _log(
                        log_callback,
                        f"CUDA OOM：批大小 {batch_size} → {next_batch}，复用同一音频重试",
                    )
                    batch_size = next_batch
                    continue
                raise

        segments = _convert_segments(
            raw_segments,
            language=language or str(getattr(info, "language", "") or ""),
            language_probability=_optional_float(
                getattr(info, "language_probability", None)
            ),
            source=source,
            settings=settings,
            duration=duration,
        )
        if not segments:
            raise UserFacingError("转写完成，但没有得到有效文本。")

        retry_count = 0
        unresolved_gaps = 0
        if settings.profile in {"balanced", "quality"}:
            segments, retry_count, unresolved_gaps = self._apply_quality_guard(
                model,
                audio_path,
                segments,
                candidate=candidate,
                settings=settings,
                language=language,
                source=source,
                duration=duration,
                log_callback=log_callback,
            )
        low_count = sum(1 for item in segments if item.low_confidence)
        low_ratio = low_count / max(1, len(segments))
        elapsed = time.perf_counter() - transcription_started
        _log(log_callback, f"低置信片段：{low_count}")
        _log(log_callback, f"局部重试：{retry_count}")
        if low_ratio > settings.low_confidence_ratio_threshold:
            _log(
                log_callback,
                f"低置信片段比例 {low_ratio:.1%} 超过阈值 "
                f"{settings.low_confidence_ratio_threshold:.1%}；建议用户显式选择 quality 模式。",
            )
        rtf = elapsed / duration if duration > 0 else 0.0
        _log(log_callback, f"转写完成：{elapsed:.1f} 秒")
        _log(log_callback, f"实时系数 RTF：{rtf:.2f}")
        telemetry = ASRTelemetry(
            profile=settings.profile,
            model=candidate.model,
            device=candidate.device_label,
            compute_type=candidate.compute_type,
            batch_size=batch_size,
            beam_size=candidate.beam_size,
            audio_duration_seconds=duration,
            model_load_seconds=load_seconds,
            transcription_seconds=elapsed,
            rtf=rtf,
            low_confidence_segments=low_count,
            local_retries=retry_count,
            unresolved_gaps=unresolved_gaps,
        )
        return ASROutcome(segments=segments, telemetry=telemetry)

    def _ensure_gpu_preflight(
        self,
        audio_path: Path,
        candidate: ASRCandidate,
        *,
        language: str | None,
        task: str,
        timeout_seconds: float = DEFAULT_GPU_FIRST_BATCH_TIMEOUT_SECONDS,
    ) -> int:
        model_ref = _model_reference(candidate.model, self.project_root)
        key = (model_ref, candidate.device_index, candidate.compute_type)
        previous = self._gpu_preflight_results.get(key)
        if previous:
            status, value = previous
            if status == "ok":
                return int(value)
            raise RuntimeError(str(value))

        batch_size = max(1, candidate.batch_size)
        while True:
            status, message = self._run_gpu_preflight_process(
                model_ref,
                candidate,
                audio_path=audio_path,
                language=language,
                task=task,
                batch_size=batch_size,
                timeout_seconds=timeout_seconds,
            )
            if status == "ok":
                self._gpu_preflight_results[key] = ("ok", batch_size)
                return batch_size
            if _is_oom_message(message) and batch_size > 1:
                batch_size = max(1, batch_size // 2)
                continue
            self._gpu_preflight_results[key] = ("error", message)
            raise RuntimeError(message)

    def _run_gpu_preflight_process(
        self,
        model_ref: str,
        candidate: ASRCandidate,
        *,
        audio_path: Path,
        language: str | None,
        task: str,
        batch_size: int,
        timeout_seconds: float,
    ) -> tuple[str, str]:
        context = multiprocessing.get_context("spawn")
        results = context.Queue(maxsize=1)
        process = context.Process(
            target=_gpu_preflight_worker,
            args=(
                model_ref,
                candidate.device_index,
                candidate.compute_type,
                str(audio_path),
                language,
                task,
                batch_size,
                results,
            ),
        )
        process.start()
        process.join(timeout_seconds)
        if process.is_alive():
            process.terminate()
            process.join(5)
            if process.is_alive():
                process.kill()
                process.join(2)
            status = "error"
            message = (
                f"GPU 首批推理超过 {timeout_seconds:.0f} 秒，"
                "已终止预检进程"
            )
        else:
            try:
                status, message = results.get(timeout=1)
            except queue.Empty:
                status = "error"
                message = f"GPU 首批推理预检异常退出（code={process.exitcode}）"
        results.close()
        results.join_thread()
        return str(status), str(message)

    def _load_model(self, candidate: ASRCandidate) -> tuple[Any, float, bool]:
        key = (
            _model_reference(candidate.model, self.project_root),
            candidate.device,
            candidate.device_index,
            candidate.compute_type,
        )
        with self._model_lock:
            if self._model is not None and self._model_key == key:
                return self._model, 0.0, True
            self._release_model()
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise UserFacingError(
                    "未安装 faster-whisper。请先运行 pip install -r requirements.txt。"
                ) from exc
            started = time.perf_counter()
            model = WhisperModel(
                key[0],
                device=candidate.device,
                device_index=candidate.device_index,
                compute_type=candidate.compute_type,
                local_files_only=True,
            )
            elapsed = time.perf_counter() - started
            self._model = model
            self._model_key = key
            return model, elapsed, False

    def _release_model(self) -> None:
        with self._model_lock:
            model = self._model
            self._model = None
            self._model_key = None
            if model is not None:
                backend = getattr(model, "model", None)
                unload = getattr(backend, "unload_model", None)
                if callable(unload):
                    try:
                        unload()
                    except Exception:
                        pass
                del model
                gc.collect()

    def _infer(
        self,
        model: Any,
        audio_path: Path,
        candidate: ASRCandidate,
        *,
        batch_size: int,
        language: str | None,
        task: str,
        log_callback: LogCallback | None,
        duration: float,
    ) -> tuple[list[Any], Any]:
        if candidate.device == "cuda":
            from faster_whisper import BatchedInferencePipeline

            pipeline = BatchedInferencePipeline(model=model)
            iterable, info = pipeline.transcribe(
                str(audio_path),
                language=language or None,
                task=task,
                beam_size=candidate.beam_size,
                temperature=0.0,
                vad_filter=candidate.vad_filter,
                word_timestamps=candidate.word_timestamps,
                without_timestamps=False,
                batch_size=batch_size,
            )
        else:
            iterable, info = model.transcribe(
                str(audio_path),
                language=language or None,
                task=task,
                beam_size=candidate.beam_size,
                temperature=0.0,
                vad_filter=candidate.vad_filter,
                word_timestamps=candidate.word_timestamps,
            )
        return _collect_with_progress(iterable, duration, log_callback), info

    def _apply_quality_guard(
        self,
        model: Any,
        audio_path: Path,
        segments: list[TranscriptSegment],
        *,
        candidate: ASRCandidate,
        settings: ASRSettings,
        language: str | None,
        source: str,
        duration: float,
        log_callback: LogCallback | None,
    ) -> tuple[list[TranscriptSegment], int, int]:
        windows = _retry_windows(segments, duration, settings)
        if not windows:
            return _mark_low_confidence(segments, settings), 0, 0
        retries = 0
        unresolved_gaps = 0
        current = list(segments)
        for start, end, reason in windows[: settings.max_local_retries]:
            retries += 1
            _log(
                log_callback,
                f"局部重试：{_format_duration(start)}–{_format_duration(end)}（{reason}）",
            )
            try:
                iterable, info = model.transcribe(
                    str(audio_path),
                    language=language or None,
                    task=settings.task,
                    beam_size=5,
                    temperature=DEFAULT_TEMPERATURE_FALLBACK,
                    vad_filter=True,
                    word_timestamps=False,
                    condition_on_previous_text=False,
                    clip_timestamps=[start, end],
                )
                retried = _convert_segments(
                    list(iterable),
                    language=language or str(getattr(info, "language", "") or ""),
                    language_probability=_optional_float(
                        getattr(info, "language_probability", None)
                    ),
                    source=source,
                    settings=settings,
                    duration=duration,
                )
            except Exception as exc:
                _log(log_callback, f"局部重试失败：{_safe_error(exc)}")
                continue
            original = [
                item for item in current if item.end > start and item.start < end
            ]
            if not retried:
                unresolved_gaps += int(reason == "大段音频无有效输出")
                continue
            if _segments_quality_score(retried) > _segments_quality_score(original):
                current = [
                    item
                    for item in current
                    if not (item.end > start and item.start < end)
                ]
                current.extend(retried)
                current.sort(key=lambda item: (item.start, item.end))
        return _mark_low_confidence(current, settings), retries, unresolved_gaps


def _gpu_preflight_worker(
    model_ref: str,
    device_index: int,
    compute_type: str,
    audio_path: str,
    language: str | None,
    task: str,
    batch_size: int,
    results: Any,
) -> None:
    try:
        from faster_whisper import BatchedInferencePipeline, WhisperModel
        from faster_whisper.audio import decode_audio

        audio = decode_audio(audio_path, sampling_rate=16000)[: 30 * 16000]
        if len(audio) == 0:
            raise RuntimeError("GPU 预检音频为空")
        model = WhisperModel(
            model_ref,
            device="cuda",
            device_index=device_index,
            compute_type=compute_type,
            local_files_only=True,
        )
        pipeline = BatchedInferencePipeline(model=model)
        iterable, _info = pipeline.transcribe(
            audio,
            language=language or None,
            task=task,
            beam_size=1,
            temperature=0.0,
            vad_filter=True,
            word_timestamps=False,
            without_timestamps=False,
            batch_size=max(1, batch_size),
        )
        next(iter(iterable), None)
        results.put(("ok", ""))
    except BaseException as exc:
        results.put(("error", _safe_error(exc)))


def _collect_with_progress(
    iterable: Any,
    duration: float,
    log_callback: LogCallback | None,
) -> list[Any]:
    result: list[Any] = []
    next_progress = 30.0
    for item in iterable:
        result.append(item)
        end = float(getattr(item, "end", 0.0) or 0.0)
        if duration > 0 and end >= next_progress:
            _log(
                log_callback,
                f"转写进度：{_format_duration(min(end, duration))} / {_format_duration(duration)}",
            )
            next_progress += max(30.0, duration / 10.0)
    return result


def _convert_segments(
    items: list[Any],
    *,
    language: str,
    language_probability: float | None,
    source: str,
    settings: ASRSettings,
    duration: float | None = None,
) -> list[TranscriptSegment]:
    result: list[TranscriptSegment] = []
    for item in items:
        text = str(getattr(item, "text", "") or "").strip()
        if not text:
            continue
        start = max(0.0, float(getattr(item, "start", 0.0) or 0.0))
        end = max(start, float(getattr(item, "end", 0.0) or 0.0))
        if duration is not None and duration > 0:
            start = min(start, duration)
            end = min(max(start, end), duration)
        segment = TranscriptSegment(
            index=len(result),
            start=start,
            end=end,
            text=text,
            language=language,
            source=source,
            avg_logprob=_optional_float(getattr(item, "avg_logprob", None)),
            compression_ratio=_optional_float(
                getattr(item, "compression_ratio", None)
            ),
            no_speech_prob=_optional_float(getattr(item, "no_speech_prob", None)),
            language_probability=language_probability,
        )
        flags = segment_quality_flags(segment, settings)
        result.append(
            segment.model_copy(
                update={
                    "quality_flags": flags,
                    "low_confidence": bool(flags),
                }
            )
        )
    return result


def segment_quality_flags(
    segment: TranscriptSegment,
    settings: ASRSettings,
) -> list[str]:
    flags: list[str] = []
    if (
        segment.avg_logprob is not None
        and segment.avg_logprob < settings.logprob_threshold
    ):
        flags.append("avg_logprob")
    if (
        segment.compression_ratio is not None
        and segment.compression_ratio > settings.compression_ratio_threshold
    ):
        flags.append("compression_ratio")
    if (
        segment.no_speech_prob is not None
        and segment.no_speech_prob > settings.no_speech_threshold
        and (segment.avg_logprob is None or segment.avg_logprob < -0.5)
    ):
        flags.append("no_speech_prob")
    if (
        segment.language_probability is not None
        and segment.language_probability < settings.language_probability_threshold
    ):
        flags.append("language_probability")
    if looks_repetitive(segment.text):
        flags.append("repetition")
    return flags


def looks_repetitive(text: str) -> bool:
    normalized = re.sub(r"\s+", "", text).lower()
    if len(normalized) < 12:
        return False
    for size in range(2, min(12, len(normalized) // 3 + 1)):
        chunk = normalized[:size]
        repeats = 0
        cursor = 0
        while normalized[cursor : cursor + size] == chunk:
            repeats += 1
            cursor += size
        if repeats >= 3 and cursor >= len(normalized) * 0.7:
            return True
    tokens = re.findall(r"[\w\u4e00-\u9fff]+", text.lower())
    if len(tokens) >= 8:
        most_common = max(tokens.count(token) for token in set(tokens))
        if most_common / len(tokens) >= 0.5:
            return True
    return bool(re.search(r"(.{2,12})\1\1", normalized))


def _retry_windows(
    segments: list[TranscriptSegment],
    duration: float,
    settings: ASRSettings,
) -> list[tuple[float, float, str]]:
    windows: list[tuple[float, float, str]] = []
    for item in segments:
        if segment_quality_flags(item, settings):
            windows.append(
                (
                    max(0.0, item.start - 0.5),
                    min(duration or item.end + 0.5, item.end + 0.5),
                    "低置信片段",
                )
            )
    ordered = sorted(segments, key=lambda item: item.start)
    for previous, current in zip(ordered, ordered[1:]):
        gap = current.start - previous.end
        if gap >= settings.gap_retry_seconds:
            windows.append(
                (previous.end, current.start, "大段音频无有效输出")
            )
    return _merge_windows(windows)


def _merge_windows(
    windows: list[tuple[float, float, str]],
) -> list[tuple[float, float, str]]:
    result: list[tuple[float, float, str]] = []
    for start, end, reason in sorted(windows, key=lambda item: item[0]):
        if end <= start:
            continue
        if result and start <= result[-1][1]:
            old_start, old_end, old_reason = result[-1]
            merged_reason = (
                old_reason if old_reason == reason else f"{old_reason}、{reason}"
            )
            result[-1] = (old_start, max(old_end, end), merged_reason)
        else:
            result.append((start, end, reason))
    return result


def _mark_low_confidence(
    segments: list[TranscriptSegment],
    settings: ASRSettings,
) -> list[TranscriptSegment]:
    result: list[TranscriptSegment] = []
    for index, item in enumerate(sorted(segments, key=lambda value: value.start)):
        flags = segment_quality_flags(item, settings)
        result.append(
            item.model_copy(
                update={
                    "index": index,
                    "quality_flags": flags,
                    "low_confidence": bool(flags),
                }
            )
        )
    return result


def _segments_quality_score(segments: list[TranscriptSegment]) -> float:
    if not segments:
        return -1000.0
    score = 0.0
    for item in segments:
        score += min(len(item.text), 120) / 120.0
        score += item.avg_logprob if item.avg_logprob is not None else -1.0
        score -= len(item.quality_flags) * 3.0
        if item.compression_ratio is not None:
            score -= max(0.0, item.compression_ratio - 2.0)
    return score


def _model_reference(model: str, project_root: Path) -> str:
    value = Path(model).expanduser()
    if value.is_absolute() or any(separator in model for separator in ("/", "\\")):
        resolved = value.resolve()
        missing = _missing_model_files(resolved)
        if missing:
            raise ConfigRequiredError(
                "未安装本地 ASR 模型（config_required）："
                + "、".join(missing)
            )
        return str(resolved)
    candidates = (
        project_root / "models" / f"faster-whisper-{model}",
        project_root / "models" / model,
    )
    for candidate in candidates:
        if not _missing_model_files(candidate):
            return str(candidate.resolve())
    raise ConfigRequiredError(
        f"未安装本地 ASR 模型（config_required）：faster-whisper-{model}；"
        "已禁止自动下载。"
    )


def _missing_model_files(path: Path) -> list[str]:
    return [name for name in REQUIRED_MODEL_FILES if not (path / name).is_file()]


def _query_nvidia_smi_memory(
    device_index: int,
) -> tuple[str, float | None, float | None, str, str]:
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                f"--id={device_index}",
                "--query-gpu=name,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        line = completed.stdout.strip().splitlines()[0]
        name, total, free = [item.strip() for item in line.split(",", 2)]
        return (
            name,
            float(total) / 1024.0,
            float(free) / 1024.0,
            "nvidia-smi",
            "",
        )
    except Exception as exc:
        return "", None, None, "", _safe_error(exc)


@contextmanager
def _cross_process_asr_lock(
    project_root: Path,
    *,
    timeout_seconds: float = DEFAULT_RESOURCE_WAIT_TIMEOUT_SECONDS,
):
    lock_path = project_root / ".local" / "asr.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            deadline = time.monotonic() + timeout_seconds
            while True:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("等待本地 ASR 文件锁超时。")
                    time.sleep(0.1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            deadline = time.monotonic() + timeout_seconds
            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("等待本地 ASR 文件锁超时。")
                    time.sleep(0.1)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _audio_duration(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as handle:
            rate = handle.getframerate()
            return handle.getnframes() / rate if rate else 0.0
    except (OSError, wave.Error):
        return 0.0


def _is_turbo(model: str) -> bool:
    return "turbo" in model.lower()


def _is_oom(exc: Exception) -> bool:
    return _is_oom_message(str(exc))


def _is_oom_message(message: str) -> bool:
    normalized = message.lower()
    return any(marker in normalized for marker in _CUDA_OOM_MARKERS)


def _is_cuda_failure(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in _CUDA_FAILURE_MARKERS)


def _is_cuda_runtime_missing(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in _CUDA_RUNTIME_MISSING_MARKERS)


def _optional_float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _safe_error(exc: Exception) -> str:
    return re.sub(r"\s+", " ", str(exc)).strip()[:300] or type(exc).__name__


def _format_duration(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def _log(callback: LogCallback | None, message: str) -> None:
    if callback:
        callback(message)


_DEFAULT_ENGINE = LocalASREngine()


def transcribe_with_local_asr(
    audio_path: Path,
    *,
    config: object | None = None,
    language: str | None = "zh",
    source: str = "asr",
    log_callback: LogCallback | None = None,
) -> ASROutcome:
    return _DEFAULT_ENGINE.transcribe(
        audio_path,
        settings=ASRSettings.from_config(config),
        language=language,
        source=source,
        log_callback=log_callback,
    )
