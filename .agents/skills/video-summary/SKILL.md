---
name: video-summary
description: Summarize or analyze user-provided public video URLs and local audio/video files with the local video-summary-skill CLI. Use for Bilibili, YouTube, yt-dlp-supported public videos, or local mp4/mp3/wav/m4a files when the user asks for transcripts, summaries, tutorial analysis, viral analysis, close reading, comment insights, or Obsidian-ready video notes.
---

# Video Summary

Use this skill to turn a user-provided video URL or local media file into Markdown outputs through the project CLI.

Run commands from the project root:

```bash
cd video-summary-skill
python -m src.main
```

If `python` is unavailable, use an available Python 3.10+ executable with the same `-m src.main` command.

## Core Workflow

1. Confirm the user provided either one public video URL or one local file path.
2. Choose the CLI command from the examples below.
3. Run the CLI and let it create a timestamped directory under `output/`.
4. Identify the newest matching `output/<name>_<timestamp>/` directory.
5. Inspect generated files before reporting completion.
6. If the CLI skipped LLM output because no API key or Ollama service is available, use Codex to read the generated transcript and write the requested Markdown report into the same output directory.

Do not bypass the CLI for transcript generation. The CLI owns platform handling, subtitle cleanup, FFmpeg audio extraction, and faster-whisper transcription.

## Platform Handling

- Bilibili URLs: the CLI uses `src/adapters/bilibili_adapter.py`, calls external `bili` / `bilibili-cli`, and falls back to yt-dlp plus FFmpeg/faster-whisper if needed.
- YouTube and other public URLs: the CLI uses yt-dlp for metadata and subtitles, then falls back to FFmpeg/faster-whisper when subtitles are unavailable.
- Local files: the CLI accepts local mp4, mp3, wav, m4a, and similar files, then uses FFmpeg plus faster-whisper.

If `bilibili-cli` is missing, tell the user in Chinese:

```bash
uv tool install bilibili-cli
```

or:

```bash
pipx install bilibili-cli
```

For Bilibili audio support, mention:

```bash
uv tool install "bilibili-cli[audio]"
```

## Command Examples

Summary for Bilibili:

```bash
python -m src.main --url "<B站链接>" --backend ollama --mode summary
```

Tutorial analysis:

```bash
python -m src.main --url "<视频链接>" --backend ollama --mode tutorial
```

Viral analysis with Bilibili comments:

```bash
python -m src.main --url "<B站链接>" --backend ollama --mode viral --comments
```

Close reading:

```bash
python -m src.main --url "<视频链接>" --backend ollama --mode close-reading
```

Local file summary:

```bash
python -m src.main --file "<本地视频或音频路径>" --backend ollama --mode summary
```

Transcript only:

```bash
python -m src.main --url "<视频链接>" --no-summary
python -m src.main --file "<本地视频或音频路径>" --no-summary
```

Obsidian merged note:

```bash
python -m src.main --url "<视频链接>" --backend ollama --mode tutorial --export obsidian
```

Use `--lang zh` or `--lang en` when the user specifies a subtitle/transcription language.

## Expected Outputs

Always expect:

- `metadata.json`
- `transcript.md`

When summary generation succeeds, expect some of:

- `summary.md`
- `chapter_summary.md`
- `highlight_notes.md`
- `tutorial_report.md`
- `viral_analysis.md`
- `close_reading.md`
- `export_note.md`

When Bilibili comments are requested and available, expect:

- `comments.json`
- `comments.md`
- `comment_insights.md`

Tell the user which output directory was produced and list the important files.

## Codex Fallback Reports

If the CLI generated `transcript.md` but did not generate the requested report because the LLM backend is unavailable:

1. Read `metadata.json`.
2. Read `transcript.md`.
3. Read the matching prompt from `prompts/`:
   - `summary_prompt.md`
   - `chapter_prompt.md`
   - `highlight_prompt.md`
   - `tutorial_prompt.md`
   - `viral_prompt.md`
   - `close_reading_prompt.md`
   - `comment_insights_prompt.md`
4. Generate the requested Chinese Markdown report with Codex.
5. Write it to the expected output filename.

Only use `comments.json` / `comments.md` for `comment_insights.md`. Do not invent comment-section information.

When writing summaries or analysis, do not invent details absent from the transcript. Use `视频中未明确说明` for uncertain or missing information.

## Compliance

Only process user-provided public video links or content the user owns, collected, or saved locally. Do not help bypass paid access, crack protections, remove watermarks, leak cookies, save credentials, mass-download videos, or prepare infringing reposts.

Do not print or save sensitive cookies or account credentials. Cookie usage, if any, must stay within the user's local authorized tool state.

For viral analysis and comment insights, focus on original topic migration and content learning. Do not encourage copying, washing, or reposting others' work.

## Error Handling

Give short Chinese explanations for:

- invalid or inaccessible links;
- unsupported local paths;
- missing FFmpeg;
- missing Python dependencies;
- missing `bili` / `bilibili-cli`;
- yt-dlp subtitle failure followed by transcription fallback;
- faster-whisper transcription failure;
- no `transcript.md` produced.

Preserve generated intermediate files whenever possible and tell the user where they are.
