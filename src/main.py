from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

try:
    import typer
except ImportError:
    typer = None  # type: ignore[assignment]

try:
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn
except ImportError:
    from .utils import console as _fallback_console

    Console = None  # type: ignore[assignment]
    Progress = None  # type: ignore[assignment]
    SpinnerColumn = None  # type: ignore[assignment]
    TextColumn = None  # type: ignore[assignment]

from .audio import extract_audio
from .adapters import BilibiliAdapter, LocalFileAdapter, YtdlpAdapter, is_bilibili_url
from .config import AppConfig, load_config
from .pipeline import PipelineOrchestrator
from .subtitle import subtitle_to_transcript
from .summarizer import NO_KEY_MESSAGE, generate_report, generate_summary
from .transcriber import transcribe_audio
from .utils import UserFacingError, ensure_dir, load_json, now_iso, now_stamp, read_text, sanitize_filename, write_text

DEFAULT_MODE = "summary"
SUPPORTED_MODES = ("summary", "tutorial", "viral", "close-reading")
IMPLEMENTED_MODES = ("summary", "tutorial", "viral", "close-reading")
SUPPORTED_EXPORTS = ("none", "obsidian")
PENDING_MODE_MESSAGE = (
    "{mode} 模式的报告生成将在后续任务实现；当前已支持 --mode 参数校验，"
    "请先使用 --mode summary，或配合 --no-summary 只生成 transcript.md。"
)

if typer:
    app = typer.Typer(add_completion=False, help="把视频链接或本地视频文件转换成结构化内容摘要。")
else:
    app = None

console = Console() if Console else _fallback_console  # type: ignore[misc]


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
    privacy_mode: bool = False,
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
    summary_backend = backend or cfg.summary_backend
    try:
        analysis_mode = normalize_mode(mode)
        export_mode = normalize_export(export)
        if analysis_mode not in IMPLEMENTED_MODES and not no_summary:
            raise UserFacingError(PENDING_MODE_MESSAGE.format(mode=analysis_mode))
    except UserFacingError as exc:
        console.print(f"[red]{exc}[/red]")
        raise ExitWithCode(1) from exc

    if comments:
        console.print("[yellow]--comments 已停用，评论功能不再进入默认处理管线。[/yellow]")
    try:
        package = PipelineOrchestrator(
            cfg,
            backend=summary_backend,
            privacy_mode=privacy_mode or cfg.privacy_mode,
            analysis_profile=analysis_mode,
            no_analysis=no_summary,
            generate_frames=generate_frames,
            sample_seconds=sample_seconds,
            export_legacy_note=export_mode == "obsidian",
            log_callback=lambda message: console.print(f"[cyan]{message}[/cyan]"),
        ).run(str(url or file), is_url=bool(url))
        console.print(f"[green]处理完成：{package.output_dir}[/green]")
        console.print(f"index.md: {package.output_dir / 'index.md'}")
        console.print(f"transcript.grouped.md: {package.output_dir / 'transcript.grouped.md'}")
        console.print(f"transcript.md: {package.output_dir / 'transcript.md'}")
        return
    except UserFacingError as exc:
        console.print(f"[red]{exc}[/red]")
        raise ExitWithCode(1) from exc

    try:
        output_root = ensure_dir(Path(cfg.output_dir))
        label = sanitize_filename(url or file.stem if file else "video")
        run_dir = ensure_dir(output_root / f"{label}_{now_stamp()}")
        temp_dir = ensure_dir(run_dir / "_temp")
        metadata_path = run_dir / "metadata.json"
        transcript_path = run_dir / "transcript.md"
        summary_path = run_dir / "summary.md"
        chapter_summary_path = run_dir / "chapter_summary.md"
        highlight_notes_path = run_dir / "highlight_notes.md"
        tutorial_report_path = run_dir / "tutorial_report.md"
        viral_analysis_path = run_dir / "viral_analysis.md"
        close_reading_path = run_dir / "close_reading.md"
        comments_json_path = run_dir / "comments.json"
        comments_md_path = run_dir / "comments.md"
        comment_insights_path = run_dir / "comment_insights.md"
        export_note_path = run_dir / "export_note.md"
        prompt_path = Path("prompts") / "summary_prompt.md"
        chapter_prompt_path = Path("prompts") / "chapter_prompt.md"
        highlight_prompt_path = Path("prompts") / "highlight_prompt.md"
        tutorial_prompt_path = Path("prompts") / "tutorial_prompt.md"
        viral_prompt_path = Path("prompts") / "viral_prompt.md"
        close_reading_prompt_path = Path("prompts") / "close_reading_prompt.md"
        comment_insights_prompt_path = Path("prompts") / "comment_insights_prompt.md"
        console.print(f"[cyan]分析模式：{analysis_mode}[/cyan]")

        progress_context = _progress_context()
        with progress_context as progress:
            if url:
                task = progress.add_task("读取视频信息并尝试提取字幕...", total=None)
                resources = _fetch_url_with_adapter(
                    url,
                    temp_dir,
                    metadata_path,
                    transcript_path,
                    comments_json_path,
                    comments_md_path,
                    language,
                    comments,
                )
                progress.update(task, description="处理字幕或准备音频转写...")
            else:
                progress.add_task("读取本地视频文件...", total=None)
                resources = LocalFileAdapter().fetch(file, metadata_path)  # type: ignore[arg-type]

            for warning in resources.warnings:
                console.print(f"[yellow]{warning}[/yellow]")

            if resources.has_transcript:
                console.print("[cyan]已从平台适配器获得 transcript.md。[/cyan]")
            elif resources.subtitle_path:
                subtitle_to_transcript(
                    resources.subtitle_path,
                    transcript_path,
                    source_url=_transcript_source_url(resources.metadata),
                )
            else:
                console.print("[yellow]未提取到可用字幕，自动进入 FFmpeg + faster-whisper 转写流程。[/yellow]")
                if not resources.media_path:
                    raise UserFacingError("没有可用字幕，也没有可用于转写的音视频文件。")
                audio_path = extract_audio(resources.media_path, temp_dir / "audio_16k.wav")
                transcribe_audio(
                    audio_path,
                    transcript_path,
                    cfg.whisper_model,
                    language,
                    source_url=_transcript_source_url(resources.metadata),
                )

            if no_summary:
                console.print("[cyan]已按 --no-summary 跳过摘要生成。[/cyan]")
            else:
                result = generate_summary(
                    transcript_path,
                    summary_path,
                    prompt_path,
                    backend=summary_backend,
                    model=cfg.openai_model,
                    ollama_model=cfg.ollama_model,
                    ollama_base_url=cfg.ollama_base_url,
                )
                if result is None:
                    console.print(f"[yellow]{NO_KEY_MESSAGE}[/yellow]")
                else:
                    generate_report(
                        transcript_path,
                        chapter_summary_path,
                        chapter_prompt_path,
                        backend=summary_backend,
                        model=cfg.openai_model,
                        ollama_model=cfg.ollama_model,
                        ollama_base_url=cfg.ollama_base_url,
                        report_name="章节总结",
                    )
                    generate_report(
                        transcript_path,
                        highlight_notes_path,
                        highlight_prompt_path,
                        backend=summary_backend,
                        model=cfg.openai_model,
                        ollama_model=cfg.ollama_model,
                        ollama_base_url=cfg.ollama_base_url,
                        report_name="高光笔记",
                    )

                if result is not None and analysis_mode == "tutorial":
                    generate_report(
                        transcript_path,
                        tutorial_report_path,
                        tutorial_prompt_path,
                        backend=summary_backend,
                        model=cfg.openai_model,
                        ollama_model=cfg.ollama_model,
                        ollama_base_url=cfg.ollama_base_url,
                        report_name="教程解析报告",
                    )
                elif result is not None and analysis_mode == "viral":
                    generate_report(
                        transcript_path,
                        viral_analysis_path,
                        viral_prompt_path,
                        backend=summary_backend,
                        model=cfg.openai_model,
                        ollama_model=cfg.ollama_model,
                        ollama_base_url=cfg.ollama_base_url,
                        report_name="爆款视频内容拆解",
                    )
                elif result is not None and analysis_mode == "close-reading":
                    generate_report(
                        transcript_path,
                        close_reading_path,
                        close_reading_prompt_path,
                        backend=summary_backend,
                        model=cfg.openai_model,
                        ollama_model=cfg.ollama_model,
                        ollama_base_url=cfg.ollama_base_url,
                        report_name="原文细读",
                    )

                if comments and resources.comments_md_path and resources.comments_md_path.exists():
                    generate_report(
                        resources.comments_md_path,
                        comment_insights_path,
                        comment_insights_prompt_path,
                        backend=summary_backend,
                        model=cfg.openai_model,
                        ollama_model=cfg.ollama_model,
                        ollama_base_url=cfg.ollama_base_url,
                        report_name="评论区有效信息分析",
                    )

            if export_mode == "obsidian":
                _write_export_note(
                    export_note_path=export_note_path,
                    metadata_path=metadata_path,
                    transcript_path=transcript_path,
                    summary_path=summary_path,
                    chapter_summary_path=chapter_summary_path,
                    highlight_notes_path=highlight_notes_path,
                    tutorial_report_path=tutorial_report_path,
                    viral_analysis_path=viral_analysis_path,
                    close_reading_path=close_reading_path,
                    comments_md_path=comments_md_path,
                    comment_insights_path=comment_insights_path,
                    analysis_mode=analysis_mode,
                )

        if not cfg.keep_temp_files and temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)

        console.print(f"[green]处理完成：{run_dir}[/green]")
        console.print(f"metadata.json: {metadata_path}")
        console.print(f"transcript.md: {transcript_path}")
        if summary_path.exists():
            console.print(f"summary.md: {summary_path}")
        if chapter_summary_path.exists():
            console.print(f"chapter_summary.md: {chapter_summary_path}")
        if highlight_notes_path.exists():
            console.print(f"highlight_notes.md: {highlight_notes_path}")
        if tutorial_report_path.exists():
            console.print(f"tutorial_report.md: {tutorial_report_path}")
        if viral_analysis_path.exists():
            console.print(f"viral_analysis.md: {viral_analysis_path}")
        if close_reading_path.exists():
            console.print(f"close_reading.md: {close_reading_path}")
        if comments_json_path.exists():
            console.print(f"comments.json: {comments_json_path}")
        if comments_md_path.exists():
            console.print(f"comments.md: {comments_md_path}")
        if comment_insights_path.exists():
            console.print(f"comment_insights.md: {comment_insights_path}")
        if export_note_path.exists():
            console.print(f"export_note.md: {export_note_path}")
    except UserFacingError as exc:
        console.print(f"[red]{exc}[/red]")
        raise ExitWithCode(1) from exc
    except Exception as exc:
        console.print(f"[red]处理失败：{exc}[/red]")
        raise ExitWithCode(1) from exc


class ExitWithCode(Exception):
    def __init__(self, code: int) -> None:
        self.code = code


class PlainProgress:
    def __enter__(self) -> "PlainProgress":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def add_task(self, description: str, total: object = None) -> int:
        console.print(description)
        return 0

    def update(self, _task: int, description: str) -> None:
        console.print(description)


def _progress_context():
    if Progress and SpinnerColumn and TextColumn:
        return Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        )
    return PlainProgress()


def _fetch_url_with_adapter(
    url: str,
    temp_dir: Path,
    metadata_path: Path,
    transcript_path: Path,
    comments_json_path: Path,
    comments_md_path: Path,
    language: str,
    comments: bool,
):
    ytdlp_adapter = YtdlpAdapter()
    if not is_bilibili_url(url):
        return ytdlp_adapter.fetch(url, temp_dir, metadata_path, language, comments)

    bilibili_adapter = BilibiliAdapter()
    try:
        result = bilibili_adapter.fetch(
            url,
            temp_dir,
            metadata_path,
            transcript_path,
            comments_json_path,
            comments_md_path,
            comments=comments,
        )
    except UserFacingError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        console.print("[yellow]将回退到 yt-dlp + FFmpeg/faster-whisper 流程。[/yellow]")
        return ytdlp_adapter.fetch(url, temp_dir, metadata_path, language, comments)

    if result.has_transcript:
        return result

    console.print("[yellow]B站未获取到可用字幕，将进入 yt-dlp audio-only + FFmpeg/faster-whisper 流程。[/yellow]")
    fallback = ytdlp_adapter.fetch(url, temp_dir, metadata_path, language, comments)
    fallback.comments_json_path = result.comments_json_path
    fallback.comments_md_path = result.comments_md_path
    fallback.warnings = result.warnings + fallback.warnings
    return fallback


def _transcript_source_url(metadata: dict[str, object]) -> str:
    return str(metadata.get("source_url") or metadata.get("url") or "")


def _write_export_note(
    *,
    export_note_path: Path,
    metadata_path: Path,
    transcript_path: Path,
    summary_path: Path,
    chapter_summary_path: Path,
    highlight_notes_path: Path,
    tutorial_report_path: Path,
    viral_analysis_path: Path,
    close_reading_path: Path,
    comments_md_path: Path,
    comment_insights_path: Path,
    analysis_mode: str,
) -> Path:
    metadata = load_json(metadata_path)
    title = str(metadata.get("title") or "未命名视频")
    source = str(metadata.get("source") or "未知")
    source_url = str(metadata.get("source_url") or metadata.get("url") or metadata.get("source_path") or "")
    author = str(metadata.get("author") or "未知")
    duration = str(metadata.get("duration") or "未知")

    lines = [
        "---",
        f'title: "{_yaml_escape(title)}"',
        f'source: "{_yaml_escape(source)}"',
        f'url: "{_yaml_escape(source_url)}"',
        f'author: "{_yaml_escape(author)}"',
        f'duration: "{_yaml_escape(duration)}"',
        f'created: "{_yaml_escape(now_iso())}"',
        "tags:",
        "  - video-note",
        "  - ai-summary",
        "---",
        "",
        f"# {title}",
        "",
        "## 一、原始信息",
        "",
        f"- 标题：{title}",
        f"- 作者：{author}",
        f"- 来源：{source}",
        f"- 时长：{duration}",
        f"- 原链接：{source_url or '视频中未明确说明'}",
        "",
        "## 二、视频简介 / Show notes",
        "",
        str(metadata.get("description") or "视频中未明确说明"),
        "",
    ]

    _append_section(lines, "三、全文总结", summary_path)
    _append_section(lines, "四、章节总结", chapter_summary_path)
    _append_section(lines, "五、高光笔记", highlight_notes_path)

    mode_file = {
        "tutorial": ("六、教程解析", tutorial_report_path),
        "viral": ("六、爆款拆解", viral_analysis_path),
        "close-reading": ("六、原文细读", close_reading_path),
    }.get(analysis_mode)
    if mode_file:
        _append_section(lines, mode_file[0], mode_file[1])

    if comments_md_path.exists() or comment_insights_path.exists():
        _append_section(lines, "七、评论区摘录", comments_md_path)
        _append_section(lines, "八、评论区有效信息分析", comment_insights_path)

    _append_section(lines, "九、字幕脚本", transcript_path)
    lines.extend(["", "## 十、我的随手笔记", "", "- "])
    write_text(export_note_path, "\n".join(lines).rstrip() + "\n")
    return export_note_path


def _append_section(lines: list[str], title: str, path: Path) -> None:
    lines.extend([f"## {title}", ""])
    if path.exists():
        lines.append(_strip_top_heading(read_text(path)).strip() or "视频中未明确说明")
    else:
        lines.append("本次运行未生成该文件。")
    lines.append("")


def _strip_top_heading(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].startswith("# "):
        return "\n".join(lines[1:]).lstrip()
    return text


def _yaml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _run_argparse() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m src.main",
        description="把视频链接或本地视频文件转换成结构化内容摘要。",
    )
    parser.add_argument("--url", help="公开视频链接，例如 B站 / YouTube。")
    parser.add_argument("--file", type=Path, help="本地视频文件路径。")
    parser.add_argument("--lang", help="字幕或转写语言，例如 zh / en。")
    parser.add_argument("--backend", help="摘要后端：ollama 或 openai。")
    parser.add_argument(
        "--mode",
        choices=SUPPORTED_MODES,
        default=DEFAULT_MODE,
        help="分析模式：summary / tutorial / viral / close-reading。",
    )
    parser.add_argument("--comments", action="store_true", help="已停用，仅为旧命令兼容保留。")
    parser.add_argument("--export", choices=SUPPORTED_EXPORTS, default="none", help="导出方式：none / obsidian。")
    parser.add_argument("--no-summary", action="store_true", help="只生成 transcript.md，不调用 LLM。")
    parser.add_argument("--privacy-mode", action="store_true", help="隐私模式：禁止调用云端 Provider。")
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
            privacy_mode=args.privacy_mode,
            generate_frames=not args.no_frames,
            sample_seconds=args.sample_seconds,
        )
    except ExitWithCode as exc:
        raise SystemExit(exc.code) from exc


if typer:
    @app.callback(invoke_without_command=True)  # type: ignore[union-attr]
    def run(
        url: Optional[str] = typer.Option(None, "--url", help="公开视频链接，例如 B站 / YouTube。"),
        file: Optional[Path] = typer.Option(None, "--file", help="本地视频文件路径。"),
        lang: Optional[str] = typer.Option(None, "--lang", help="字幕或转写语言，例如 zh / en。"),
        backend: Optional[str] = typer.Option(None, "--backend", help="摘要后端：ollama 或 openai。"),
        mode: str = typer.Option(
            DEFAULT_MODE,
            "--mode",
            help="分析模式：summary / tutorial / viral / close-reading。",
        ),
        comments: bool = typer.Option(False, "--comments", help="已停用，仅为旧命令兼容保留。"),
        export: str = typer.Option("none", "--export", help="导出方式：none / obsidian。"),
        no_summary: bool = typer.Option(False, "--no-summary", help="只生成 transcript.md，不调用 LLM。"),
        config: Path = typer.Option(Path("config.example.json"), "--config", help="配置文件路径。"),
        privacy_mode: bool = typer.Option(False, "--privacy-mode", help="隐私模式：禁止调用云端 Provider。"),
        no_frames: bool = typer.Option(False, "--no-frames", help="跳过关键帧生成。"),
        sample_seconds: Optional[int] = typer.Option(None, "--sample-seconds", help="仅处理开头指定秒数，用于快速链路验证。"),
    ) -> None:
        try:
            run_pipeline(url, file, lang, backend, mode, comments, export, no_summary, config, privacy_mode, not no_frames, sample_seconds)
        except ExitWithCode as exc:
            raise typer.Exit(code=exc.code) from exc


if __name__ == "__main__":
    if typer:
        app()  # type: ignore[operator]
    else:
        _run_argparse()
