from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

try:
    import typer
except ImportError:
    typer = None  # type: ignore[assignment]

from . import __version__
from .cli_contract import CliEmitter, ExitCode, classify_error, error_object, sanitize_message
from .cli_tasks import CliTaskRecord, CliTaskStore
from .config import load_config
from .diagnostics import run_doctor
from .exporters import export_directory_to_vault, render_directory_export, selection_for_request
from .exporters.obsidian_exporter import safe_export_filename
from .knowledge_validation import inspect_knowledge_package
from .pipeline import PipelineOrchestrator
from .processing_profiles import DEFAULT_PROCESSING_PROFILE, normalize_processing_profile
from .utils import UserFacingError


DEFAULT_MODE = "summary"
SUPPORTED_MODES = ("auto", "summary", "tutorial", "interview", "lecture", "review", "viral", "close-reading")
SUPPORTED_EXPORTS = ("none", "obsidian")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = Path("config.example.json")
CLI_TASK_ROOT = PROJECT_ROOT / ".local" / "cli_tasks"

if typer:
    app = typer.Typer(add_completion=False, help="把视频链接或本地视频文件转换成结构化内容摘要。")
else:
    app = None

def _version_callback(value: bool) -> None:
    if value:
        print(f"video-summary-skill {__version__}")
        raise typer.Exit()  # type: ignore[union-attr]


def normalize_mode(mode: str | None) -> str:
    normalized = (mode or DEFAULT_MODE).strip().lower()
    if normalized not in SUPPORTED_MODES:
        supported = " / ".join(SUPPORTED_MODES)
        raise UserFacingError(f"mode 参数不合法：{mode}。支持的模式：{supported}。")
    return normalized


def normalize_export(export: str | None) -> str:
    normalized = (export or "none").strip().lower()
    if normalized not in SUPPORTED_EXPORTS:
        supported = " / ".join(SUPPORTED_EXPORTS)
        raise UserFacingError(f"export 参数不合法：{export}。支持的导出方式：{supported}。")
    return normalized


def normalize_backend(backend: str | None) -> str:
    normalized = (backend or "deepseek").strip().lower()
    if normalized != "deepseek":
        raise UserFacingError(
            f"后端 {backend} 已停用。当前仅支持 deepseek，请改用 --backend deepseek。"
        )
    return normalized


def run_pipeline(
    url: Optional[str] = None,
    file: Optional[Path] = None,
    lang: Optional[str] = None,
    backend: Optional[str] = None,
    mode: str = DEFAULT_MODE,
    processing_profile: str = DEFAULT_PROCESSING_PROFILE,
    comments: bool = False,
    export: str = "none",
    no_summary: bool = False,
    config: Path = Path("config.example.json"),
    generate_frames: bool = True,
    sample_seconds: int | None = None,
    *,
    task_id: str | None = None,
    emitter: CliEmitter | None = None,
) -> dict[str, Any]:
    emitter = emitter or CliEmitter("analyze")
    if not url and not file:
        raise ExitWithCode(ExitCode.USAGE_OR_CONFIG, "请提供 --url 或 --file。使用 --help 查看示例。")
    if url and file:
        raise ExitWithCode(ExitCode.USAGE_OR_CONFIG, "--url 和 --file 只能二选一。")
    if sample_seconds is not None and sample_seconds <= 0:
        raise ExitWithCode(ExitCode.USAGE_OR_CONFIG, "--sample-seconds 必须是大于 0 的整数。")
    if file and not file.expanduser().is_file():
        raise ExitWithCode(ExitCode.INPUT_INACCESSIBLE, f"本地输入文件不存在：{file}")

    try:
        cfg = load_config(config)
    except UserFacingError as exc:
        raise ExitWithCode(ExitCode.USAGE_OR_CONFIG, str(exc)) from exc
    language = lang or cfg.language
    if language != cfg.language:
        cfg = cfg.model_copy(update={"language": language})
    try:
        summary_backend = normalize_backend(backend or cfg.summary_backend)
        analysis_mode = normalize_mode(mode)
        resolved_processing_profile = normalize_processing_profile(processing_profile)
        export_mode = normalize_export(export)
    except (UserFacingError, ValueError) as exc:
        raise ExitWithCode(ExitCode.USAGE_OR_CONFIG, str(exc)) from exc

    if comments:
        emitter.diagnostic("警告：--comments 已停用；本次不会获取或分析评论。")
    try:
        package = PipelineOrchestrator(
            cfg,
            backend=summary_backend,
            analysis_profile=analysis_mode,
            processing_profile=resolved_processing_profile,
            no_analysis=no_summary,
            generate_frames=generate_frames,
            sample_seconds=sample_seconds,
            export_legacy_note=export_mode == "obsidian",
            log_callback=emitter.diagnostic,
            event_callback=lambda event, **payload: emitter.event(event, **payload),
            task_id=task_id,
        ).run(str(url or file), is_url=bool(url))
    except UserFacingError as exc:
        message = str(exc)
        raise ExitWithCode(classify_error(message), message) from exc
    except Exception as exc:
        message = f"处理失败：{exc}"
        raise ExitWithCode(ExitCode.EXECUTION_FAILED, message) from exc

    return {
        "task_id": package.manifest.task_id,
        "knowledge_id": package.output_dir.name,
        "output_dir": str(package.output_dir),
        "status": package.manifest.status,
        "analysis_profile": package.manifest.analysis_profile,
        "processing_profile": package.manifest.processing_profile,
        "first_readable_result_duration_ms": package.manifest.first_readable_result_duration_ms,
        "full_completion_duration_ms": package.manifest.full_completion_duration_ms,
        "analysis": {
            "status": package.analysis.status if package.analysis else "skipped",
            "provider": package.analysis.provider if package.analysis else "",
            "model": package.analysis.model if package.analysis else "",
        },
        "artifacts": {
            "index": str(package.output_dir / "index.md"),
            "transcript_grouped": str(package.output_dir / "transcript.grouped.md"),
            "transcript": str(package.output_dir / "transcript.md"),
            **({"compatible_export": str(package.output_dir / "export_note.md")} if export_mode == "obsidian" else {}),
        },
    }


def execute_analyze(
    *,
    url: str | None = None,
    file: Path | None = None,
    lang: str | None = None,
    backend: str | None = None,
    mode: str = DEFAULT_MODE,
    processing_profile: str = DEFAULT_PROCESSING_PROFILE,
    comments: bool = False,
    export: str = "none",
    no_summary: bool = False,
    config: Path = DEFAULT_CONFIG,
    generate_frames: bool = True,
    sample_seconds: int | None = None,
    json_output: bool = False,
    jsonl_output: bool = False,
    task_id: str | None = None,
    task_store: CliTaskStore | None = None,
    resumed: bool = False,
) -> int:
    try:
        emitter = CliEmitter("resume" if resumed else "analyze", json_output=json_output, jsonl_output=jsonl_output)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return int(ExitCode.USAGE_OR_CONFIG)

    store = task_store or CliTaskStore(CLI_TASK_ROOT)
    resolved_task_id = task_id or uuid.uuid4().hex[:12]
    source_type = "url" if url else "file"
    source = str(url or file or "")
    try:
        resolved_processing_profile = normalize_processing_profile(processing_profile)
    except ValueError as exc:
        emitter.failure(ExitCode.USAGE_OR_CONFIG, str(exc), task_id=resolved_task_id)
        return int(ExitCode.USAGE_OR_CONFIG)
    options = {
        "lang": lang,
        "backend": backend,
        "mode": mode,
        "processing_profile": resolved_processing_profile,
        "comments": comments,
        "export": export,
        "no_summary": no_summary,
        "config": str(config),
        "generate_frames": generate_frames,
        "sample_seconds": sample_seconds,
    }
    try:
        if resumed:
            record = store.load(resolved_task_id)
            record.status = "running"
            record.exit_code = None
            record.error_code = ""
            record.error_message = ""
        else:
            record = CliTaskRecord(
                task_id=resolved_task_id,
                source_type=source_type,
                source=source,
                processing_profile=resolved_processing_profile,
                options=options,
                status="running",
            )
        store.save(record)
    except (OSError, UserFacingError, ValueError) as exc:
        emitter.failure(ExitCode.USAGE_OR_CONFIG, str(exc), task_id=resolved_task_id)
        return int(ExitCode.USAGE_OR_CONFIG)

    emitter.event(
        "task_created",
        task_id=resolved_task_id,
        resumed=resumed,
        source_type=source_type,
        analysis_profile=mode,
        processing_profile=resolved_processing_profile,
    )
    try:
        data = run_pipeline(
            url=url,
            file=file,
            lang=lang,
            backend=backend,
            mode=mode,
            processing_profile=resolved_processing_profile,
            comments=comments,
            export=export,
            no_summary=no_summary,
            config=config,
            generate_frames=generate_frames,
            sample_seconds=sample_seconds,
            task_id=resolved_task_id,
            emitter=emitter,
        )
    except ExitWithCode as exc:
        code = ExitCode(exc.code)
        record.status = "failed"
        record.exit_code = int(code)
        record.error_code = code.name.lower()
        record.error_message = sanitize_message(exc.message)
        try:
            store.save(record)
        except OSError as store_error:
            emitter.diagnostic(f"任务记录保存失败：{store_error}")
        emitter.failure(code, exc.message, task_id=resolved_task_id)
        return int(code)

    record.status = "completed"
    record.output_dir = str(data["output_dir"])
    record.knowledge_id = str(data["knowledge_id"])
    record.exit_code = int(ExitCode.SUCCESS)
    try:
        store.save(record)
    except OSError as exc:
        message = f"任务已完成，但任务记录保存失败：{exc}"
        emitter.diagnostic(message)
        emitter.event("warning", task_id=resolved_task_id, stage="task_record", message=message)
    emitter.event("task_completed", task_id=resolved_task_id, result=data)
    emitter.result(data)
    return int(ExitCode.SUCCESS)


def execute_resume(
    task_id: str,
    *,
    json_output: bool = False,
    jsonl_output: bool = False,
    task_store: CliTaskStore | None = None,
) -> int:
    store = task_store or CliTaskStore(CLI_TASK_ROOT)
    try:
        record = store.load(task_id)
    except UserFacingError as exc:
        emitter = CliEmitter("resume", json_output=json_output, jsonl_output=jsonl_output)
        code = classify_error(str(exc)) if "损坏" in str(exc) or "Schema" in str(exc) else ExitCode.INPUT_INACCESSIBLE
        emitter.failure(code, str(exc), task_id=task_id)
        return int(code)
    if record.status == "completed":
        emitter = CliEmitter("resume", json_output=json_output, jsonl_output=jsonl_output)
        emitter.failure(ExitCode.USAGE_OR_CONFIG, "已完成任务不需要恢复。", task_id=task_id)
        return int(ExitCode.USAGE_OR_CONFIG)
    options = record.options
    return execute_analyze(
        url=record.source if record.source_type == "url" else None,
        file=Path(record.source) if record.source_type == "file" else None,
        lang=_optional_string(options.get("lang")),
        backend=_optional_string(options.get("backend")),
        mode=str(options.get("mode") or DEFAULT_MODE),
        processing_profile=record.processing_profile,
        comments=bool(options.get("comments", False)),
        export=str(options.get("export") or "none"),
        no_summary=bool(options.get("no_summary", False)),
        config=Path(str(options.get("config") or DEFAULT_CONFIG)),
        generate_frames=bool(options.get("generate_frames", True)),
        sample_seconds=_optional_int(options.get("sample_seconds")),
        json_output=json_output,
        jsonl_output=jsonl_output,
        task_id=task_id,
        task_store=store,
        resumed=True,
    )


def _optional_string(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def export_existing_knowledge(
    knowledge_id: str,
    *,
    format_name: str = "markdown",
    preset: str = "full",
    sections: str = "",
    order: str = "",
    overwrite: bool = False,
    config: Path = Path("config.example.json"),
) -> dict[str, object]:
    cfg = load_config(config)
    root = (Path(cfg.output_dir) if Path(cfg.output_dir).is_absolute() else Path.cwd() / cfg.output_dir).resolve()
    directory = (root / knowledge_id).resolve()
    if directory.parent != root or not (directory / "metadata.json").is_file():
        raise UserFacingError("知识包不存在。")
    payload: dict[str, object] = {"preset": preset, "overwrite": overwrite}
    if sections:
        payload["sections"] = [value.strip() for value in sections.split(",") if value.strip()]
    if order:
        payload["order"] = [value.strip() for value in order.split(",") if value.strip()]
    selection = selection_for_request(knowledge_id, payload)
    if format_name == "obsidian":
        result = export_directory_to_vault(
            directory,
            selection,
            vault_path=cfg.obsidian_vault_path,
            vault_name=cfg.obsidian_vault_name,
            subdir=cfg.obsidian_export_subdir,
        )
    elif format_name == "markdown":
        markdown, filename = render_directory_export(directory, selection)
        target = directory / (Path(filename).stem + ".export.md")
        if target.exists() and not overwrite:
            counter = 2
            while target.exists():
                target = directory / (Path(filename).stem + f".export ({counter}).md")
                counter += 1
        target.write_text(markdown, encoding="utf-8")
        result = {"success": True, "knowledge_id": knowledge_id, "format": "markdown", "file_path": str(target), "included_sections": selection.normalized_sections()}
    else:
        raise UserFacingError("format 只能是 markdown 或 obsidian。")
    return result


class ExitWithCode(Exception):
    def __init__(self, code: int | ExitCode, message: str = "") -> None:
        super().__init__(message)
        self.code = int(code)
        self.message = message


def _run_argparse() -> None:
    import argparse

    if len(sys.argv) > 1 and sys.argv[1] == "inspect":
        inspect_parser = argparse.ArgumentParser(prog="python -m src.main inspect")
        inspect_parser.add_argument("package", type=Path, help="知识包目录。")
        inspect_parser.add_argument("--json", action="store_true", dest="json_output", help="输出 JSON。")
        args = inspect_parser.parse_args(sys.argv[2:])
        raise SystemExit(_print_inspection(args.package, args.json_output))
    if len(sys.argv) > 1 and sys.argv[1] == "export":
        export_parser = argparse.ArgumentParser(prog="python -m src.main export")
        export_parser.add_argument("--knowledge-id", required=True)
        export_parser.add_argument("--format", choices=("markdown", "obsidian"), default="markdown", dest="format_name")
        export_parser.add_argument("--preset", choices=("light", "summary-chat", "full"), default="full")
        export_parser.add_argument("--sections", default="")
        export_parser.add_argument("--order", default="")
        export_parser.add_argument("--overwrite", action="store_true")
        export_parser.add_argument("--json", action="store_true", dest="json_output")
        export_parser.add_argument("--config", type=Path, default=Path("config.example.json"))
        args = export_parser.parse_args(sys.argv[2:])
        try:
            result = export_existing_knowledge(args.knowledge_id, format_name=args.format_name, preset=args.preset, sections=args.sections, order=args.order, overwrite=args.overwrite, config=args.config)
            print(json.dumps(result, ensure_ascii=False, indent=2) if args.json_output else result["file_path"])
            raise SystemExit(0)
        except UserFacingError as exc:
            print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False) if args.json_output else str(exc))
            raise SystemExit(2) from exc

    parser = argparse.ArgumentParser(
        prog="python -m src.main",
        description="把视频链接或本地视频文件转换成结构化内容摘要。",
    )
    parser.add_argument("--version", action="version", version=f"video-summary-skill {__version__}")
    parser.add_argument("--url", help="公开视频链接，例如 B站 / YouTube。")
    parser.add_argument("--file", type=Path, help="本地视频文件路径。")
    parser.add_argument("--lang", help="字幕或转写语言，例如 zh / en。")
    parser.add_argument("--backend", help="AI 分析后端：仅支持 deepseek。")
    parser.add_argument(
        "--mode",
        choices=SUPPORTED_MODES,
        default=DEFAULT_MODE,
        help="分析模式：summary / tutorial / viral / close-reading。",
    )
    parser.add_argument(
        "--processing-profile",
        choices=("fast", "complete"),
        default=DEFAULT_PROCESSING_PROFILE,
        help="处理模式：fast / complete。fast 优先文本并跳过关键帧；默认 complete。",
    )
    parser.add_argument("--comments", action="store_true", help="已停用；保留此参数仅用于旧命令兼容。")
    parser.add_argument("--export", choices=SUPPORTED_EXPORTS, default="none", help="导出方式：none / obsidian。")
    parser.add_argument("--no-summary", action="store_true", help="只生成 transcript.md，不调用 LLM。")
    parser.add_argument("--no-frames", action="store_true", help="跳过关键帧生成。")
    parser.add_argument("--sample-seconds", type=int, help="仅处理开头指定秒数，用于快速链路验证。")
    parser.add_argument("--config", type=Path, default=Path("config.example.json"), help="配置文件路径。")
    args = parser.parse_args()
    try:
        run_pipeline(
            url=args.url,
            file=args.file,
            lang=args.lang,
            backend=args.backend,
            mode=args.mode,
            processing_profile=args.processing_profile,
            comments=args.comments,
            export=args.export,
            no_summary=args.no_summary,
            config=args.config,
            generate_frames=not args.no_frames,
            sample_seconds=args.sample_seconds,
        )
    except ExitWithCode as exc:
        raise SystemExit(exc.code) from exc


if typer:
    @app.command("analyze")  # type: ignore[union-attr]
    def analyze_command(
        url: Optional[str] = typer.Option(None, "--url", help="公开视频链接。"),
        file: Optional[Path] = typer.Option(None, "--file", help="本地音视频文件。"),
        lang: Optional[str] = typer.Option(None, "--lang"),
        backend: Optional[str] = typer.Option(None, "--backend"),
        mode: str = typer.Option(DEFAULT_MODE, "--mode"),
        processing_profile: str = typer.Option(
            DEFAULT_PROCESSING_PROFILE,
            "--processing-profile",
            help="处理模式：fast / complete。fast 优先文本并跳过关键帧。",
        ),
        comments: bool = typer.Option(False, "--comments", help="已停用的兼容参数。"),
        export: str = typer.Option("none", "--export"),
        no_summary: bool = typer.Option(False, "--no-summary"),
        config: Path = typer.Option(DEFAULT_CONFIG, "--config"),
        no_frames: bool = typer.Option(False, "--no-frames"),
        sample_seconds: Optional[int] = typer.Option(None, "--sample-seconds"),
        json_output: bool = typer.Option(False, "--json", help="输出单个 JSON 结果。"),
        jsonl_output: bool = typer.Option(False, "--jsonl", help="逐行输出 JSON 事件。"),
    ) -> None:
        code = execute_analyze(
            url=url,
            file=file,
            lang=lang,
            backend=backend,
            mode=mode,
            processing_profile=processing_profile,
            comments=comments,
            export=export,
            no_summary=no_summary,
            config=config,
            generate_frames=not no_frames,
            sample_seconds=sample_seconds,
            json_output=json_output,
            jsonl_output=jsonl_output,
        )
        raise typer.Exit(code=code)


    @app.command("inspect")  # type: ignore[union-attr]
    def inspect_command(
        package: Path = typer.Argument(..., help="知识包目录。"),
        json_output: bool = typer.Option(False, "--json", help="输出机器可读 JSON。"),
    ) -> None:
        raise typer.Exit(code=_print_inspection(package, json_output))


    @app.command("export")  # type: ignore[union-attr]
    def export_command(
        knowledge_id: str = typer.Option(..., "--knowledge-id"),
        format_name: str = typer.Option("markdown", "--format"),
        preset: str = typer.Option("full", "--preset"),
        sections: str = typer.Option("", "--sections"),
        order: str = typer.Option("", "--order"),
        overwrite: bool = typer.Option(False, "--overwrite"),
        json_output: bool = typer.Option(False, "--json"),
        config: Path = typer.Option(DEFAULT_CONFIG, "--config"),
    ) -> None:
        emitter = CliEmitter("export", json_output=json_output)
        try:
            result = export_existing_knowledge(
                knowledge_id,
                format_name=format_name,
                preset=preset,
                sections=sections,
                order=order,
                overwrite=overwrite,
                config=config,
            )
            emitter.result(result)
        except UserFacingError as exc:
            code = classify_error(str(exc))
            emitter.failure(code, str(exc))
            raise typer.Exit(code=int(code)) from exc


    @app.command("resume")  # type: ignore[union-attr]
    def resume_command(
        task_id: str = typer.Argument(..., help="由 analyze 返回的 task_id。"),
        json_output: bool = typer.Option(False, "--json"),
        jsonl_output: bool = typer.Option(False, "--jsonl"),
    ) -> None:
        raise typer.Exit(code=execute_resume(task_id, json_output=json_output, jsonl_output=jsonl_output))


    @app.command("doctor")  # type: ignore[union-attr]
    def doctor_command(
        config: Path = typer.Option(DEFAULT_CONFIG, "--config"),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        emitter = CliEmitter("doctor", json_output=json_output)
        try:
            result = run_doctor(load_config(config), project_root=PROJECT_ROOT)
        except UserFacingError as exc:
            emitter.failure(ExitCode.USAGE_OR_CONFIG, str(exc))
            raise typer.Exit(code=int(ExitCode.USAGE_OR_CONFIG)) from exc
        healthy = bool(result["healthy"])
        emitter.result(
            result,
            success=healthy,
            error=None if healthy else error_object(ExitCode.EXTERNAL_TOOL_MISSING, "环境诊断发现必需依赖缺失。"),
        )
        raise typer.Exit(code=int(ExitCode.SUCCESS if healthy else ExitCode.EXTERNAL_TOOL_MISSING))


    @app.command("config")  # type: ignore[union-attr]
    def config_command(
        config: Path = typer.Option(DEFAULT_CONFIG, "--config"),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        emitter = CliEmitter("config", json_output=json_output)
        try:
            resolved = config.expanduser().resolve()
            cfg = load_config(config)
        except UserFacingError as exc:
            emitter.failure(ExitCode.USAGE_OR_CONFIG, str(exc))
            raise typer.Exit(code=int(ExitCode.USAGE_OR_CONFIG)) from exc
        emitter.result({"config_path": str(resolved), "exists": resolved.is_file(), "values": cfg.model_dump(mode="json")})


    @app.callback(invoke_without_command=True)  # type: ignore[union-attr]
    def run(
        ctx: typer.Context,
        version: bool = typer.Option(False, "--version", callback=_version_callback, is_eager=True, help="显示版本并退出。"),
        url: Optional[str] = typer.Option(None, "--url", help="旧用法兼容；请改用 analyze --url。"),
        file: Optional[Path] = typer.Option(None, "--file", help="旧用法兼容；请改用 analyze --file。"),
        lang: Optional[str] = typer.Option(None, "--lang"),
        backend: Optional[str] = typer.Option(None, "--backend"),
        mode: str = typer.Option(DEFAULT_MODE, "--mode"),
        processing_profile: str = typer.Option(
            DEFAULT_PROCESSING_PROFILE,
            "--processing-profile",
            help="旧根级用法兼容；处理模式 fast / complete。",
        ),
        comments: bool = typer.Option(False, "--comments", help="已停用的兼容参数。"),
        export: str = typer.Option("none", "--export"),
        no_summary: bool = typer.Option(False, "--no-summary"),
        config: Path = typer.Option(DEFAULT_CONFIG, "--config"),
        no_frames: bool = typer.Option(False, "--no-frames"),
        sample_seconds: Optional[int] = typer.Option(None, "--sample-seconds"),
        json_output: bool = typer.Option(False, "--json"),
        jsonl_output: bool = typer.Option(False, "--jsonl"),
    ) -> None:
        if ctx.invoked_subcommand:
            return
        if not url and not file:
            typer.echo(ctx.get_help())
            return
        print("警告：根级 analyze 参数已废弃；请使用 `python -m src.main analyze ...`。", file=sys.stderr)
        code = execute_analyze(
            url=url,
            file=file,
            lang=lang,
            backend=backend,
            mode=mode,
            processing_profile=processing_profile,
            comments=comments,
            export=export,
            no_summary=no_summary,
            config=config,
            generate_frames=not no_frames,
            sample_seconds=sample_seconds,
            json_output=json_output,
            jsonl_output=jsonl_output,
        )
        raise typer.Exit(code=code)


def _print_inspection(package: Path, json_output: bool) -> int:
    report = inspect_knowledge_package(package)
    emitter = CliEmitter("inspect", json_output=json_output)
    if json_output:
        invalid = report.level == "invalid"
        emitter.result(
            report.to_dict(),
            success=not invalid,
            error=error_object(ExitCode.KNOWLEDGE_PACKAGE_DAMAGED, "知识包检查未通过。") if invalid else None,
        )
    else:
        print(f"package_path: {report.package_path}")
        print(f"level: {report.level}")
        print(f"manifest_status: {report.manifest_status or 'unknown'}")
        print(f"analysis_status: {report.analysis_status or 'unknown'}")
        print(f"transcript_segments: {report.transcript_segments}")
        for issue in report.issues:
            print(f"[{issue.severity}] {issue.code}: {issue.message}", file=sys.stderr)
    return int(ExitCode.SUCCESS if report.level == "valid" else ExitCode.EXECUTION_FAILED if report.level == "warning" else ExitCode.KNOWLEDGE_PACKAGE_DAMAGED)


if __name__ == "__main__":
    if typer:
        app()  # type: ignore[operator]
    else:
        _run_argparse()
