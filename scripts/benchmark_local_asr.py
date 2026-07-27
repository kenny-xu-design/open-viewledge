from __future__ import annotations

import argparse
import json
import subprocess
import threading
import time
import wave
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.asr_runtime import (
    ASRCandidate,
    ASRSettings,
    LocalASREngine,
    _safe_error,
)


CONFIGURATIONS = {
    "small-cpu-int8-original": ASRCandidate("small", "cpu", "int8", 1, 5),
    "small-cpu-int8": ASRCandidate("small", "cpu", "int8", 1, 1),
    "small-cuda-fp16": ASRCandidate("small", "cuda", "float16", 8, 3),
    "turbo-cuda-fp16": ASRCandidate("turbo", "cuda", "float16", 8, 3),
}


class GpuMemorySampler:
    def __init__(self, interval_seconds: float = 0.1) -> None:
        self.interval_seconds = interval_seconds
        self.peak_used_mb: float | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "GpuMemorySampler":
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                completed = subprocess.run(
                    [
                        "nvidia-smi",
                        "--id=0",
                        "--query-gpu=memory.used",
                        "--format=csv,noheader,nounits",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=True,
                )
                used = float(completed.stdout.strip().splitlines()[0])
                self.peak_used_mb = max(self.peak_used_mb or 0.0, used)
            except Exception:
                pass
            self._stop.wait(self.interval_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark exact local faster-whisper configurations.")
    parser.add_argument(
        "--sample",
        action="append",
        required=True,
        metavar="LABEL|LANGUAGE|PATH",
    )
    parser.add_argument(
        "--configuration",
        action="append",
        choices=tuple(CONFIGURATIONS),
        default=[],
    )
    args = parser.parse_args()
    configurations = args.configuration or list(CONFIGURATIONS)
    samples = [_parse_sample(value) for value in args.sample]
    results: list[dict[str, Any]] = []
    for configuration_name in configurations:
        for label, language, audio_path in samples:
            results.append(
                benchmark_one(
                    configuration_name,
                    CONFIGURATIONS[configuration_name],
                    label,
                    language,
                    audio_path,
                )
            )
    print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
    return 0


def benchmark_one(
    configuration_name: str,
    candidate: ASRCandidate,
    sample_label: str,
    language: str,
    audio_path: Path,
) -> dict[str, Any]:
    duration = _duration(audio_path)
    settings = ASRSettings(
        profile="balanced",
        model=candidate.model,
        device=candidate.device_label,
        compute_type=candidate.compute_type,
        max_local_retries=0,
    )
    engine = LocalASREngine()
    logs: list[str] = []
    started = time.perf_counter()
    with GpuMemorySampler() as memory:
        try:
            outcome = engine._run_candidate(
                audio_path,
                candidate,
                settings=settings,
                language=language,
                source="benchmark",
                duration=duration,
                log_callback=logs.append,
            )
        except Exception as exc:
            elapsed = time.perf_counter() - started
            engine._release_model()
            return {
                "configuration": configuration_name,
                "candidate": asdict(candidate),
                "sample": sample_label,
                "language": language,
                "audio_duration_seconds": duration,
                "status": "failed",
                "error": _safe_error(exc),
                "total_seconds": elapsed,
                "rtf": elapsed / duration if duration else None,
                "peak_gpu_memory_used_mb": memory.peak_used_mb,
                "logs": logs,
            }
    elapsed = time.perf_counter() - started
    engine._release_model()
    segments = outcome.segments
    return {
        "configuration": configuration_name,
        "candidate": asdict(candidate),
        "sample": sample_label,
        "language": language,
        "audio_duration_seconds": duration,
        "status": "success",
        "total_seconds": elapsed,
        "rtf": elapsed / duration if duration else None,
        "peak_gpu_memory_used_mb": memory.peak_used_mb,
        "model_load_seconds": outcome.telemetry.model_load_seconds,
        "transcription_seconds": outcome.telemetry.transcription_seconds,
        "segment_count": len(segments),
        "low_confidence_segments": outcome.telemetry.low_confidence_segments,
        "local_retries": outcome.telemetry.local_retries,
        "repetition_segments": sum(
            "repetition" in segment.quality_flags for segment in segments
        ),
        "transcript": " ".join(segment.text for segment in segments),
        "segments": [segment.model_dump(mode="json") for segment in segments],
        "logs": logs,
    }


def _parse_sample(value: str) -> tuple[str, str, Path]:
    parts = value.split("|", 2)
    if len(parts) != 3:
        raise SystemExit("--sample 必须使用 LABEL|LANGUAGE|PATH 格式。")
    path = Path(parts[2]).expanduser().resolve()
    if not path.is_file():
        raise SystemExit(f"样本不存在：{path}")
    return parts[0], parts[1], path


def _duration(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / handle.getframerate()


if __name__ == "__main__":
    raise SystemExit(main())
