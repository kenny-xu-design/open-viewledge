from __future__ import annotations

import multiprocessing
import queue
import threading
import time
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Callable, Literal

from .asr_runtime import (
    ASRCandidate,
    ASROutcome,
    ASRSettings,
    ASRTelemetry,
    CudaProbe,
    LocalASREngine,
    _audio_duration,
    _model_reference,
    build_asr_candidates,
    probe_cuda,
)
from .config import AppConfig
from .domain.models import TranscriptSegment
from .resource_governor import resource_guard, set_process_below_normal
from .utils import UserFacingError


WorkerDevice = Literal["cuda", "cpu"]
WorkerEventCallback = Callable[[dict[str, Any]], None]
_LOCAL_ASR_SEMAPHORE = threading.BoundedSemaphore(1)


class LocalASRWorkerError(UserFacingError):
    def __init__(
        self,
        message: str,
        *,
        reason: str,
        timed_out: bool = False,
        worker_exitcode: int | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.timed_out = timed_out
        self.worker_exitcode = worker_exitcode


def _worker_main(
    messages: Any,
    result_sender: Any,
    control_receiver: Any,
    config_data: dict[str, Any],
    audio_path: str,
    device: WorkerDevice,
    language: str | None,
    project_root: str,
) -> None:
    stop_heartbeat = threading.Event()
    phase = {"value": "starting"}

    def send(message_type: str, **payload: Any) -> None:
        messages.put(
            {
                "type": message_type,
                "phase": phase["value"],
                "at": time.time(),
                **payload,
            }
        )

    def heartbeat() -> None:
        while not stop_heartbeat.wait(1.0):
            send(
                "heartbeat",
                stage=phase["value"],
                segment_start=None,
                attempt=None,
            )

    heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
    heartbeat_thread.start()
    engine = LocalASREngine(project_root=Path(project_root))
    messages_closed = False
    try:
        if device == "cpu":
            set_process_below_normal()
        config = AppConfig.model_validate(config_data).model_copy(
            update={
                "asr_device": device,
                "asr_compute_type": "int8" if device == "cpu" else "",
            }
        )
        settings = ASRSettings.from_config(config)
        phase["value"] = "detecting" if device == "cuda" else "waiting"
        probe = probe_cuda() if device == "cuda" else CudaProbe()
        if device == "cuda" and not probe.available:
            raise LocalASRWorkerError(
                f"CUDA 不可用：{probe.error or 'device count 为 0'}",
                reason="cuda_unavailable",
            )
        candidate_settings = (
            replace(settings, fallback_enabled=True)
            if device == "cuda" and not settings.model
            else settings
        )
        candidates = build_asr_candidates(candidate_settings, probe)
        candidate = None
        for item in candidates:
            if item.device != device:
                continue
            try:
                _model_reference(item.model, Path(project_root))
            except UserFacingError:
                continue
            candidate = item
            break
        if candidate is None:
            raise LocalASRWorkerError(
                "本地 ASR 没有可用的执行配置。",
                reason="cuda_unavailable" if device == "cuda" else "cpu_transcription_failed",
            )
        if device == "cpu":
            candidate = ASRCandidate(
                model=candidate.model,
                device="cpu",
                compute_type="int8",
                batch_size=1,
                beam_size=1,
                vad_filter=True,
                word_timestamps=False,
                explicit=True,
            )

        def log(message: str) -> None:
            send("log", message=message)

        def activity(event: str, payload: dict[str, Any]) -> None:
            phase["value"] = event
            send(event, **payload)

        phase["value"] = "waiting"
        with resource_guard(
            "gpu" if device == "cuda" else "cpu",
            timeout_seconds=settings.resource_wait_timeout_seconds,
            profile=settings.compute_profile,
            configured_threads=settings.cpu_thread_limit,
        ):
            phase["value"] = "model_loading"
            send("model_loading", device=device)
            outcome = engine._run_candidate(
                Path(audio_path),
                candidate,
                settings=settings,
                language=language,
                source="asr",
                duration=_audio_duration(Path(audio_path)),
                log_callback=log,
                activity_callback=activity,
                run_gpu_preflight=False,
        )
        phase["value"] = "finalizing"
        send("finalizing")
        stop_heartbeat.set()
        heartbeat_thread.join(timeout=2)
        messages.close()
        messages.join_thread()
        messages_closed = True
        result_sender.send(
            {
                "type": "result",
                "segments": [
                    item.model_dump(mode="json") for item in outcome.segments
                ],
                "telemetry": asdict(outcome.telemetry),
            }
        )
        if not control_receiver.poll(30) or control_receiver.recv() != "ack":
            raise RuntimeError("父进程未确认本地 ASR 结果。")
    except BaseException as exc:
        try:
            result_sender.send(
                {
                    "type": "error",
                    "error_type": type(exc).__name__,
                    "message": str(exc)[:500],
                    "reason": getattr(exc, "reason", _failure_reason(device, exc)),
                }
            )
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        engine._release_model()
        if not messages_closed:
            stop_heartbeat.set()
            heartbeat_thread.join(timeout=2)
            try:
                messages.close()
            except (AttributeError, OSError):
                pass
        for connection in (result_sender, control_receiver):
            try:
                connection.close()
            except (AttributeError, OSError):
                pass


class LocalASRWorkerRunner:
    def __init__(
        self,
        *,
        project_root: Path,
        process_context: Any | None = None,
        worker_target: Callable[..., None] = _worker_main,
    ) -> None:
        self.project_root = project_root
        self.process_context = process_context or multiprocessing.get_context("spawn")
        self.worker_target = worker_target

    def run(
        self,
        audio_path: Path,
        *,
        config: AppConfig,
        device: WorkerDevice,
        language: str | None,
        event_callback: WorkerEventCallback | None = None,
    ) -> ASROutcome:
        if event_callback:
            event_callback({"type": "waiting_resource", "at": time.time()})
        if not _LOCAL_ASR_SEMAPHORE.acquire(
            timeout=float(config.asr_resource_wait_timeout_seconds)
        ):
            raise LocalASRWorkerError(
                "等待本地转写资源超时。",
                reason="asr_resource_wait_timeout",
                timed_out=True,
            )
        try:
            return self._run_acquired(
                audio_path,
                config=config,
                device=device,
                language=language,
                event_callback=event_callback,
            )
        finally:
            _LOCAL_ASR_SEMAPHORE.release()

    def _run_acquired(
        self,
        audio_path: Path,
        *,
        config: AppConfig,
        device: WorkerDevice,
        language: str | None,
        event_callback: WorkerEventCallback | None = None,
    ) -> ASROutcome:
        messages = self.process_context.Queue()
        result_receiver, result_sender = self.process_context.Pipe(duplex=False)
        control_receiver, control_sender = self.process_context.Pipe(duplex=False)
        process = self.process_context.Process(
            target=self.worker_target,
            args=(
                messages,
                result_sender,
                control_receiver,
                config.model_dump(mode="json"),
                str(audio_path),
                device,
                language,
                str(self.project_root),
            ),
        )
        model_timeout = float(
            config.asr_gpu_model_load_timeout_seconds
            if device == "cuda"
            else config.asr_cpu_model_load_timeout_seconds
        )
        first_batch_timeout = float(config.asr_gpu_first_batch_timeout_seconds)
        stall_timeout = float(config.asr_transcribe_stall_timeout_seconds)
        heartbeat_timeout = float(config.asr_worker_heartbeat_timeout_seconds)
        quality_timeout = float(config.asr_quality_guard_timeout_seconds)
        process.start()
        result_sender.close()
        control_receiver.close()
        model_deadline = time.monotonic() + model_timeout
        model_loaded = False
        transcription_started_at: float | None = None
        last_segment_at: float | None = None
        last_message_at = time.monotonic()
        quality_started_at: float | None = None
        result: ASROutcome | None = None
        worker_error: LocalASRWorkerError | None = None
        forced = False
        try:
            while True:
                now = time.monotonic()
                if not model_loaded and now >= model_deadline:
                    reason = (
                        "gpu_model_load_timeout"
                        if device == "cuda"
                        else "cpu_model_load_timeout"
                    )
                    raise LocalASRWorkerError(
                        f"{'GPU' if device == 'cuda' else 'CPU'} 模型加载超时，"
                        "已终止本地 ASR Worker。",
                        reason=reason,
                        timed_out=True,
                    )
                if now - last_message_at >= heartbeat_timeout:
                    reason = (
                        "gpu_transcription_stalled"
                        if device == "cuda"
                        else "cpu_transcription_stalled"
                    )
                    raise LocalASRWorkerError(
                        "本地 ASR Worker 心跳超时，已终止。",
                        reason=reason,
                        timed_out=True,
                    )
                if quality_started_at is not None and now - quality_started_at >= quality_timeout:
                    reason = (
                        "gpu_transcription_stalled"
                        if device == "cuda"
                        else "cpu_transcription_stalled"
                    )
                    raise LocalASRWorkerError(
                        "本地 ASR 质量检查超时，已终止 Worker。",
                        reason=reason,
                        timed_out=True,
                    )
                if (
                    device == "cuda"
                    and transcription_started_at is not None
                    and last_segment_at is None
                    and now - transcription_started_at >= first_batch_timeout
                ):
                    raise LocalASRWorkerError(
                        "GPU 首批推理超时，已终止 GPU Worker。",
                        reason="gpu_first_batch_timeout",
                        timed_out=True,
                    )
                if (
                    quality_started_at is None
                    and
                    transcription_started_at is not None
                    and now - (last_segment_at or transcription_started_at) >= stall_timeout
                ):
                    reason = (
                        "gpu_transcription_stalled"
                        if device == "cuda"
                        else "cpu_transcription_stalled"
                    )
                    raise LocalASRWorkerError(
                        "本地 GPU 转写长时间无进展，已终止 GPU Worker。"
                        if device == "cuda"
                        else "本地 CPU 转写长时间无进展，任务已终止。",
                        reason=reason,
                        timed_out=True,
                    )
                try:
                    message = messages.get(timeout=0.05)
                except queue.Empty:
                    if not process.is_alive():
                        if not result_receiver.poll():
                            break
                    message = None
                if isinstance(message, dict):
                    last_message_at = time.monotonic()
                    message_type = str(message.get("type") or "")
                    if event_callback:
                        event_callback(message)
                    if message_type == "model_loaded":
                        model_loaded = True
                    elif message_type == "transcribing":
                        transcription_started_at = time.monotonic()
                    elif message_type == "segment":
                        last_segment_at = time.monotonic()
                    elif message_type == "quality_guard":
                        state = str(message.get("state") or "")
                        if state == "started":
                            quality_started_at = time.monotonic()
                        elif state == "completed":
                            quality_started_at = None
                if message is None and result_receiver.poll():
                    terminal = result_receiver.recv()
                    last_message_at = time.monotonic()
                    if not isinstance(terminal, dict):
                        continue
                    if terminal.get("type") == "result":
                        result = ASROutcome(
                            segments=[
                                TranscriptSegment.model_validate(item)
                                for item in terminal.get("segments", [])
                            ],
                            telemetry=ASRTelemetry(
                                **dict(terminal.get("telemetry") or {})
                            ),
                        )
                        control_sender.send("ack")
                        break
                    if terminal.get("type") == "error":
                        worker_error = LocalASRWorkerError(
                            str(terminal.get("message") or "本地 ASR Worker 失败。"),
                            reason=str(
                                terminal.get("reason")
                                or (
                                    "gpu_transcription_failed"
                                    if device == "cuda"
                                    else "cpu_transcription_failed"
                                )
                            ),
                        )
                        break
            if result is not None:
                return result
            if worker_error is not None:
                raise worker_error
            raise LocalASRWorkerError(
                "本地 ASR Worker 异常退出。",
                reason=(
                    "gpu_worker_crashed"
                    if device == "cuda"
                    else "cpu_worker_crashed"
                ),
                worker_exitcode=process.exitcode,
            )
        except BaseException:
            forced = process.is_alive()
            raise
        finally:
            self._stop_process(process, force=forced)
            if forced:
                cancel_join = getattr(messages, "cancel_join_thread", None)
                if callable(cancel_join):
                    cancel_join()
            messages.close()
            if not forced:
                messages.join_thread()
            for connection in (result_receiver, control_sender):
                try:
                    connection.close()
                except (AttributeError, OSError):
                    pass

    @staticmethod
    def _stop_process(process: Any, *, force: bool = False) -> None:
        if not force and process.is_alive():
            process.join(3)
        if process.is_alive():
            process.terminate()
            process.join(3)
        if process.is_alive():
            process.kill()
            process.join(2)
        else:
            process.join(timeout=0.2)
        close = getattr(process, "close", None)
        if callable(close):
            close()


def _failure_reason(device: WorkerDevice, exc: BaseException) -> str:
    if device == "cpu":
        return "cpu_transcription_failed"
    text = str(exc).lower()
    if "out of memory" in text or "cublas_status_alloc_failed" in text:
        return "gpu_out_of_memory"
    if "cublas" in text or "cudnn" in text or "dll" in text:
        return "gpu_model_load_failed"
    if "first" in text or "首批" in text:
        return "gpu_first_batch_failed"
    if "model" in text or "模型" in text:
        return "gpu_model_load_failed"
    return "gpu_transcription_failed"
