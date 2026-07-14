from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urljoin

try:
    from dotenv import load_dotenv
except ImportError:

    def load_dotenv() -> bool:  # type: ignore[no-redef]
        return False


from .utils import UserFacingError, read_text, write_text

NO_KEY_MESSAGE = "未检测到 OPENAI_API_KEY，已生成 transcript.md，暂未生成 summary.md。"
OLLAMA_SERVICE_MESSAGE = "未检测到 Ollama 服务，请先运行 ollama serve 或打开 Ollama。"
OLLAMA_MODEL = "auto"
OLLAMA_MODEL_CANDIDATES = ("qwen3.5:9b", "llama3.1:8b", "qwen3:4b", "gemma4:e4b")


def generate_summary(
    transcript_path: Path,
    summary_path: Path,
    prompt_path: Path,
    backend: str = "openai",
    model: str = "gpt-4o-mini",
    ollama_model: str = OLLAMA_MODEL,
    ollama_base_url: str = "http://localhost:11434",
) -> Path | None:
    return generate_report(
        transcript_path,
        summary_path,
        prompt_path,
        backend=backend,
        model=model,
        ollama_model=ollama_model,
        ollama_base_url=ollama_base_url,
        report_name="摘要",
    )


def generate_report(
    transcript_path: Path,
    output_path: Path,
    prompt_path: Path,
    backend: str = "openai",
    model: str = "gpt-4o-mini",
    ollama_model: str = OLLAMA_MODEL,
    ollama_base_url: str = "http://localhost:11434",
    report_name: str = "报告",
) -> Path | None:
    load_dotenv()

    normalized_backend = backend.lower().strip()
    if normalized_backend == "ollama":
        return _generate_ollama_report(
            transcript_path,
            output_path,
            prompt_path,
            model=ollama_model,
            base_url=ollama_base_url,
            report_name=report_name,
        )
    if normalized_backend != "openai":
        raise UserFacingError(f"暂不支持的摘要后端：{backend}")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise UserFacingError("未安装 openai。请先运行 pip install -r requirements.txt。") from exc

    base_url = os.getenv("OPENAI_BASE_URL") or None
    client = OpenAI(api_key=api_key, base_url=base_url)
    system_prompt = read_text(prompt_path)
    transcript = read_text(transcript_path)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": transcript},
            ],
            temperature=0.2,
        )
    except Exception as exc:
        raise UserFacingError(f"OpenAI {report_name}生成失败：{exc}") from exc

    content = response.choices[0].message.content or ""
    if not content.strip():
        raise UserFacingError(f"OpenAI 返回了空{report_name}。")
    write_text(output_path, content.strip() + "\n")
    return output_path


def _generate_ollama_report(
    transcript_path: Path,
    output_path: Path,
    prompt_path: Path,
    model: str,
    base_url: str,
    report_name: str,
) -> Path:
    model = resolve_ollama_model(base_url, model)

    system_prompt = read_text(prompt_path)
    transcript = read_text(transcript_path)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": transcript},
        ],
        "stream": False,
        "options": {"temperature": 0.2},
    }
    response_data = _post_ollama_chat(base_url, payload)
    message = response_data.get("message") or {}
    content = str(message.get("content") or "").strip()
    if not content:
        raise UserFacingError(f"Ollama 返回了空{report_name}。")

    write_text(output_path, content + "\n")
    return output_path


def discover_ollama_models(base_url: str) -> list[str]:
    endpoint = urljoin(base_url.rstrip("/") + "/", "api/tags")
    request = urllib.request.Request(endpoint, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise UserFacingError(f"Ollama 模型列表读取失败：HTTP {exc.code} {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise UserFacingError(OLLAMA_SERVICE_MESSAGE) from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise UserFacingError(f"Ollama /api/tags 返回了无法解析的内容：{raw[:200]}") from exc
    models = payload.get("models") if isinstance(payload, dict) else []
    if not isinstance(models, list):
        return []
    names = []
    for item in models:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("model") or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def choose_ollama_model(installed_models: list[str], requested_model: str = OLLAMA_MODEL) -> str:
    installed = [name.strip() for name in installed_models if name and name.strip()]
    requested = (requested_model or OLLAMA_MODEL).strip()
    if requested.lower() != "auto" and requested in installed:
        return requested
    for candidate in OLLAMA_MODEL_CANDIDATES:
        if candidate in installed:
            return candidate
    if installed:
        return installed[0]
    candidates = "、".join(OLLAMA_MODEL_CANDIDATES)
    raise UserFacingError(f"Ollama 服务可访问，但未检测到已安装模型。候选优先级：{candidates}。")


def resolve_ollama_model(base_url: str, requested_model: str = OLLAMA_MODEL) -> str:
    return choose_ollama_model(discover_ollama_models(base_url), requested_model)


def _post_ollama_chat(base_url: str, payload: dict[str, object]) -> dict[str, object]:
    endpoint = urljoin(base_url.rstrip("/") + "/", "api/chat")
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if exc.code == 404 or "not found" in detail.lower():
            model = str(payload.get("model") or "未知模型")
            raise UserFacingError(f"Ollama 模型 {model} 当前不可用，请刷新本机模型列表后重试。") from exc
        raise UserFacingError(f"Ollama 摘要生成失败：HTTP {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise UserFacingError(OLLAMA_SERVICE_MESSAGE) from exc
    except TimeoutError as exc:
        raise UserFacingError("Ollama 响应超时，请确认本地模型正在运行后重试。") from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise UserFacingError(f"Ollama 返回了无法解析的内容：{raw[:200]}") from exc
