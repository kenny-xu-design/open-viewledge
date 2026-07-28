from __future__ import annotations

import importlib.util
import time
from pathlib import Path
from typing import Any

from .asr_runtime import _probe_cuda_bounded, resolve_available_local_models
from .config import AppConfig
from .provider_config import ProviderConfigResolver
from .runtime_tools import runtime_tool_statuses

CAPABILITY_STATES = {"checking", "available", "unavailable", "config_required", "error"}


class CapabilityRegistry:
    def __init__(
        self,
        config: AppConfig,
        *,
        project_root: Path,
        provider_resolver: ProviderConfigResolver | None = None,
    ) -> None:
        self.config = config
        self.project_root = project_root
        self.provider_resolver = provider_resolver or ProviderConfigResolver()

    def inspect(self) -> dict[str, Any]:
        result: dict[str, dict[str, Any]] = {}
        for provider in ("deepseek", "groq", "gemini"):
            resolved = self.provider_resolver.resolve(provider)
            result[provider] = _capability(
                "available" if resolved.configured else "config_required",
                "" if resolved.configured else f"{provider}_api_key_missing",
                f"{provider} 已配置" if resolved.configured else f"{provider} 尚未配置",
                model=resolved.model,
            )

        tools = {
            item.name: item
            for item in runtime_tool_statuses(
                ffmpeg_path=self.config.ffmpeg_path,
                ffprobe_path=self.config.ffprobe_path,
                project_root=self.project_root,
            )
        }
        for name in ("ffmpeg", "ffprobe"):
            item = tools[name]
            result[name] = _capability(
                "available" if item.available else "unavailable",
                "" if item.available else f"{name}_missing",
                f"{name} 可用" if item.available else f"{name} 不可用",
                source=item.source if item.available else "",
            )

        models = resolve_available_local_models(project_root=self.project_root)
        model_names = sorted(models)
        result["local_model"] = _capability(
            "available" if models else "config_required",
            "" if models else "local_asr_model_missing",
            "本地 ASR 模型可用：" + "、".join(model_names)
            if models
            else "未安装完整的本地 ASR 模型",
            models=model_names,
        )
        faster_whisper_ready = importlib.util.find_spec("faster_whisper") is not None
        cpu_ready = faster_whisper_ready and bool(models)
        result["local_cpu"] = _capability(
            "available" if cpu_ready else "config_required",
            "" if cpu_ready else (
                "local_asr_model_missing" if faster_whisper_ready else "faster_whisper_missing"
            ),
            "本地 CPU ASR 可用" if cpu_ready else "本地 CPU ASR 尚未就绪",
        )

        probe = _probe_cuda_bounded(self.config.asr_gpu_detect_timeout_seconds)
        gpu_ready = cpu_ready and probe.available and bool(probe.compute_types)
        result["local_gpu"] = _capability(
            "available" if gpu_ready else "unavailable",
            "" if gpu_ready else (
                "cuda_detection_timeout"
                if "超" in probe.error or "timeout" in probe.error.lower()
                else "cuda_unavailable"
            ),
            "本地 GPU ASR 可用" if gpu_ready else "本地 GPU ASR 不可用",
            deviceCount=probe.device_count,
            computeTypes=sorted(probe.compute_types),
            models=model_names,
        )
        return {"status": "available", "updatedAt": time.time(), "capabilities": result}


def _capability(
    status: str,
    reason: str,
    display_message: str,
    **details: Any,
) -> dict[str, Any]:
    assert status in CAPABILITY_STATES
    return {
        "status": status,
        "reason": reason,
        "displayMessage": display_message,
        **details,
    }
