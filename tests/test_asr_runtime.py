from __future__ import annotations

import sys
import tempfile
import types
import unittest
import wave
import ctypes
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.asr_runtime import (
    ASRCandidate,
    ASROutcome,
    ASRSettings,
    ASRTelemetry,
    CudaProbe,
    LocalASREngine,
    _configure_windows_cuda_dll_directories,
    _convert_segments,
    _retry_windows,
    build_asr_candidates,
    looks_repetitive,
    segment_quality_flags,
)
from src.config import AppConfig
from src.domain.models import TranscriptSegment


CUDA_16_GB = CudaProbe(
    device_count=1,
    compute_types=frozenset({"float16", "int8_float16", "int8"}),
    device_name="RTX 5060 Ti",
    total_memory_gb=16,
    free_memory_gb=13,
)


def _segment(**updates: object) -> TranscriptSegment:
    values = {
        "index": 0,
        "start": 0.0,
        "end": 3.0,
        "text": "正常转写文本",
        "language": "zh",
        "source": "asr",
        "avg_logprob": -0.2,
        "compression_ratio": 1.2,
        "no_speech_prob": 0.1,
        "language_probability": 0.95,
    }
    values.update(updates)
    return TranscriptSegment(**values)


class ASRRoutingTests(unittest.TestCase):
    def test_windows_cuda_runtime_directories_are_registered_and_preloaded(self) -> None:
        with (
            patch("src.asr_runtime.os.name", "nt"),
            patch("src.asr_runtime.Path.is_dir", return_value=True),
            patch("src.asr_runtime.os.add_dll_directory", return_value=object()) as add_dir,
            patch.object(ctypes, "WinDLL", return_value=object(), create=True) as load_dll,
        ):
            _configure_windows_cuda_dll_directories()
        self.assertEqual(add_dir.call_count, 3)
        self.assertEqual(load_dll.call_count, 4)

    def test_balanced_prefers_turbo_on_16gb_cuda(self) -> None:
        candidates = build_asr_candidates(ASRSettings(profile="balanced"), CUDA_16_GB)
        first = candidates[0]
        self.assertEqual(
            (first.model, first.device, first.compute_type, first.batch_size, first.beam_size),
            ("turbo", "cuda", "float16", 8, 3),
        )
        self.assertEqual(candidates[-1].device, "cpu")

    def test_fast_and_quality_profiles_have_distinct_routes(self) -> None:
        fast = build_asr_candidates(ASRSettings(profile="fast"), CUDA_16_GB)
        quality = build_asr_candidates(ASRSettings(profile="quality"), CUDA_16_GB)
        self.assertEqual(
            (fast[0].model, fast[0].batch_size, fast[0].beam_size),
            ("small", 16, 1),
        )
        self.assertEqual(
            (quality[0].model, quality[0].batch_size, quality[0].beam_size),
            ("large-v3", 8, 5),
        )

    def test_translate_never_uses_turbo(self) -> None:
        candidates = build_asr_candidates(
            ASRSettings(profile="balanced", task="translate"),
            CUDA_16_GB,
        )
        self.assertNotIn("turbo", [item.model for item in candidates])
        self.assertEqual(candidates[0].model, "small")

    def test_cpu_is_safe_fallback_when_cuda_is_unavailable(self) -> None:
        candidates = build_asr_candidates(
            ASRSettings(profile="balanced"),
            CudaProbe(),
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(
            (candidates[0].model, candidates[0].device, candidates[0].compute_type),
            ("small", "cpu", "int8"),
        )

    def test_explicit_overrides_are_first_but_keep_safe_fallback(self) -> None:
        candidates = build_asr_candidates(
            ASRSettings(
                profile="balanced",
                model="small",
                device="cuda:0",
                compute_type="int8_float16",
            ),
            CUDA_16_GB,
        )
        self.assertTrue(candidates[0].explicit)
        self.assertEqual(candidates[0].compute_type, "int8_float16")
        self.assertTrue(any(item.device == "cpu" for item in candidates))


class ASRQualityGuardTests(unittest.TestCase):
    def test_metrics_and_repetition_mark_low_quality(self) -> None:
        settings = ASRSettings()
        item = _segment(
            text="测试测试测试测试测试测试",
            avg_logprob=-1.5,
            compression_ratio=3.0,
            no_speech_prob=0.9,
            language_probability=0.2,
        )
        flags = segment_quality_flags(item, settings)
        self.assertEqual(
            set(flags),
            {
                "avg_logprob",
                "compression_ratio",
                "no_speech_prob",
                "language_probability",
                "repetition",
            },
        )
        self.assertTrue(looks_repetitive(item.text))

    def test_retry_windows_merge_low_quality_and_large_gap(self) -> None:
        settings = ASRSettings(gap_retry_seconds=20)
        segments = [
            _segment(end=2, avg_logprob=-2),
            _segment(index=1, start=40, end=43),
        ]
        windows = _retry_windows(segments, 60, settings)
        self.assertEqual(len(windows), 1)
        self.assertIn("低置信片段", windows[0][2])
        self.assertIn("大段音频无有效输出", windows[0][2])

    def test_local_retry_keeps_better_result_and_is_bounded(self) -> None:
        engine = LocalASREngine()
        bad = _segment(avg_logprob=-2.0, quality_flags=["avg_logprob"], low_confidence=True)
        retried = SimpleNamespace(
            start=0.0,
            end=3.0,
            text="重试后的可靠文本",
            avg_logprob=-0.1,
            compression_ratio=1.1,
            no_speech_prob=0.05,
        )
        model = SimpleNamespace(
            transcribe=Mock(
                return_value=(
                    iter([retried]),
                    SimpleNamespace(language="zh", language_probability=0.95),
                )
            )
        )
        logs: list[str] = []
        segments, retries, unresolved = engine._apply_quality_guard(
            model,
            Path("sample.wav"),
            [bad],
            candidate=ASRCandidate("small", "cpu", "int8", 1, 1),
            settings=ASRSettings(max_local_retries=1),
            language="zh",
            source="asr",
            duration=3.0,
            log_callback=logs.append,
        )
        self.assertEqual(retries, 1)
        self.assertEqual(unresolved, 0)
        self.assertEqual(segments[0].text, "重试后的可靠文本")
        self.assertFalse(segments[0].low_confidence)
        model.transcribe.assert_called_once()

    def test_segment_end_is_clamped_to_audio_duration(self) -> None:
        raw = SimpleNamespace(
            start=29.5,
            end=30.4,
            text="末尾文本",
            avg_logprob=-0.2,
            compression_ratio=1.0,
            no_speech_prob=0.1,
        )
        converted = _convert_segments(
            [raw],
            language="zh",
            language_probability=0.9,
            source="asr",
            settings=ASRSettings(),
            duration=30.0,
        )
        self.assertEqual(converted[0].end, 30.0)


class ASRFallbackAndCacheTests(unittest.TestCase):
    def _wav(self, root: Path) -> Path:
        path = root / "sample.wav"
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(16000)
            handle.writeframes(b"\0\0" * 16000)
        return path

    def test_missing_cuda_runtime_skips_remaining_gpu_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            audio = self._wav(Path(temp))
            engine = LocalASREngine(project_root=Path(temp))
            cpu_outcome = ASROutcome(
                segments=[_segment()],
                telemetry=ASRTelemetry(profile="balanced", model="small", device="cpu"),
            )
            engine._run_candidate = Mock(  # type: ignore[method-assign]
                side_effect=[
                    RuntimeError("Library cublas64_12.dll is not found or cannot be loaded"),
                    cpu_outcome,
                ]
            )
            logs: list[str] = []
            outcome = engine.transcribe(
                audio,
                settings=ASRSettings(profile="balanced"),
                language="zh",
                source="asr",
                log_callback=logs.append,
                cuda_probe=CUDA_16_GB,
            )
        self.assertIs(outcome, cpu_outcome)
        self.assertEqual(engine._run_candidate.call_count, 2)  # type: ignore[attr-defined]
        self.assertTrue(any("→ 已切换 small CPU INT8" in item for item in logs))

    def test_gpu_preflight_halves_batch_after_oom(self) -> None:
        engine = LocalASREngine()
        candidate = ASRCandidate("small", "cuda", "float16", 8, 3)
        engine._run_gpu_preflight_process = Mock(  # type: ignore[method-assign]
            side_effect=[("error", "CUDA out of memory"), ("ok", "")]
        )
        batch = engine._ensure_gpu_preflight(
            Path("sample.wav"),
            candidate,
            language="zh",
            task="transcribe",
        )
        self.assertEqual(batch, 4)
        self.assertEqual(engine._run_gpu_preflight_process.call_count, 2)  # type: ignore[attr-defined]

    def test_same_model_configuration_reuses_cached_instance(self) -> None:
        engine = LocalASREngine()
        backend = Mock()
        first_model = types.SimpleNamespace(model=backend)
        factory = Mock(return_value=first_model)
        module = types.ModuleType("faster_whisper")
        module.WhisperModel = factory  # type: ignore[attr-defined]
        candidate = ASRCandidate("small", "cpu", "int8", 1, 1)
        with (
            patch.dict(sys.modules, {"faster_whisper": module}),
            patch("src.asr_runtime._model_reference", return_value="local-small"),
        ):
            first, _elapsed, reused_first = engine._load_model(candidate)
            second, _elapsed, reused_second = engine._load_model(candidate)
        self.assertIs(first, second)
        self.assertFalse(reused_first)
        self.assertTrue(reused_second)
        factory.assert_called_once()


class ASRConfigTests(unittest.TestCase):
    def test_default_profile_is_balanced(self) -> None:
        config = AppConfig()
        self.assertEqual(config.asr_profile, "balanced")

    def test_invalid_profile_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            AppConfig(asr_profile="extreme")


if __name__ == "__main__":
    unittest.main()
