from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

try:
    import typer
except ImportError:
    typer = None  # type: ignore[assignment]

try:
    from rich.console import Console
except ImportError:
    from .utils import console as _fallback_console

    Console = None  # type: ignore[assignment]

from . import __version__
from .config import load_config
from .exporters import export_directory_to_vault, render_directory_export, selection_for_request
from .exporters.obsidian_exporter import safe_export_filename
from .knowledge_validation import inspect_knowledge_package
from .pipeline import PipelineOrchestrator
from .utils import UserFacingError


DEFAULT_MODE = "summary"
SUPPORTED_MODES = ("auto", "summary", "tutorial", "interview", "lecture", "review", "viral", "close-reading")
SUPPORTED_EXPORTS = ("none", "obsidian")

if typer:
    app = typer.Typer(add_completion=False, help="把视频链接或本地视频文件转换成结构化内容摘要。")
else:
    app = None

console = Console() if Console else _fallback_console  # type: ignore[misc]


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
    comments: bool = False,
    export: str = "none",
    no_summary: bool = False,
    config: Path = Path("config.example.json"),
    generate_frames: bool = True,
    sample_seconds: int | None = None,
) -> None:
    if not url and not file:
        console.print("[yellow]请提供 --url 或 --file。使用 --help 查看示例。[/yellow]")
        raise ExitWithCode(1)
    if url and file:
        console.print("[red]--url 和 --file 只能二选一。[/red]")
        raise ExitWithCode(1)
    if sample_seconds is not None and sample_seconds <= 0:
        console.print("[red]--sample-seconds 必须是大于 0 的整数。[/red]")
        raise ExitWithCode(1)

    cfg = load_config(config)
    language = lang or cfg.language
    if language != cfg.language:
        cfg = cfg.model_copy(update={"language": language})
    try:
        summary_backend = normalize_backend(backend or cfg.summary_backend)
        analysis_mode = normalize_mode(mode)
        export_mode = normalize_export(export)
    except UserFacingError as exc:
        console.print(f"[red]{exc}[/red]")
        raise ExitWithCode(1) from exc

    if comments:
        console.print("[yellow]--comments 已停用；本次不会获取或分析评论。[/yellow]")
    try:
        package = PipelineOrchestrator(
            cfg,
            backend=summary_backend,
            analysis_profile=analysis_mode,
            no_analysis=no_summary,
            generate_frames=generate_frames,
            sample_seconds=sample_seconds,
            export_legacy_note=export_mode == "obsidian",
            log_callback=lambda message: console.print(f"[cyan]{message}[/cyan]"),
        ).run(str(url or file), is_url=bool(url))
    except UserFacingError as exc:
        console.print(f"[red]{exc}[/red]")
        raise ExitWithCode(1) from exc
    except Exception as exc:
        console.print(f"[red]处理失败：{exc}[/red]")
        raise ExitWithCode(1) from exc

    console.print(f"[green]处理完成：{package.output_dir}[/green]")
    console.print(f"index.md: {package.output_dir / 'index.md'}")
    console.print(f"transcript.grouped.md: {package.output_dir / 'transcript.grouped.md'}")
    console.print(f"transcript.md: {package.output_dir / 'transcript.md'}")
    if export_mode == "obsidian":
        console.print(f"export_note.md: {package.output_dir / 'export_note.md'}")


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
    def __init__(self, code: int) -> None:
        self.code = code


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
        config: Path = typer.Option(Path("config.example.json"), "--config"),
    ) -> None:
        try:
            result = export_existing_knowledge(knowledge_id, format_name=format_name, preset=preset, sections=sections, order=order, overwrite=overwrite, config=config)
            print(json.dumps(result, ensure_ascii=False, indent=2) if json_output else result["file_path"])
        except UserFacingError as exc:
            print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False) if json_output else str(exc))
            raise typer.Exit(code=2) from exc


    @app.callback(invoke_without_command=True)  # type: ignore[union-attr]
    def run(
        ctx: typer.Context,
        version: bool = typer.Option(
            False,
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="显示版本并退出。",
        ),
        url: Optional[str] = typer.Option(None, "--url", help="公开视频链接，例如 B站 / YouTube。"),
        file: Optional[Path] = typer.Option(None, "--file", help="本地视频文件路径。"),
        lang: Optional[str] = typer.Option(None, "--lang", help="字幕或转写语言，例如 zh / en。"),
        backend: Optional[str] = typer.Option(None, "--backend", help="AI 分析后端：仅支持 deepseek。"),
        mode: str = typer.Option(
            DEFAULT_MODE,
            "--mode",
            help="分析模式：summary / tutorial / viral / close-reading。",
        ),
        comments: bool = typer.Option(False, "--comments", help="已停用；保留此参数仅用于旧命令兼容。"),
        export: str = typer.Option("none", "--export", help="导出方式：none / obsidian。"),
        no_summary: bool = typer.Option(False, "--no-summary", help="只生成 transcript.md，不调用 LLM。"),
        config: Path = typer.Option(Path("config.example.json"), "--config", help="配置文件路径。"),
        no_frames: bool = typer.Option(False, "--no-frames", help="跳过关键帧生成。"),
        sample_seconds: Optional[int] = typer.Option(None, "--sample-seconds", help="仅处理开头指定秒数，用于快速链路验证。"),
    ) -> None:
        if ctx.invoked_subcommand:
            return
        try:
            run_pipeline(url, file, lang, backend, mode, comments, export, no_summary, config, not no_frames, sample_seconds)
        except ExitWithCode as exc:
            raise typer.Exit(code=exc.code) from exc


def _print_inspection(package: Path, json_output: bool) -> int:
    report = inspect_knowledge_package(package)
    if json_output:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        console.print(f"知识包：{report.package_path}")
        console.print(f"完整性：{report.level}")
        console.print(f"Manifest：{report.manifest_status or 'unknown'}")
        console.print(f"分析：{report.analysis_status or 'unknown'}")
        console.print(f"有效字幕段：{report.transcript_segments}")
        for issue in report.issues:
            console.print(f"[{issue.severity}] {issue.code}: {issue.message}")
    return 0 if report.level == "valid" else 1 if report.level == "warning" else 2


if __name__ == "__main__":
    if typer:
        app()  # type: ignore[operator]
    else:
        _run_argparse()
