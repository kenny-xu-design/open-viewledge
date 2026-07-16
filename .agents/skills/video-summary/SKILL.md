---
name: video-summary
description: Process user-provided public video URLs or local audio/video files with the video-summary-skill CLI, producing transcripts, structured DeepSeek analysis, and knowledge-package Markdown. Use for Bilibili, YouTube, other yt-dlp-supported public videos, and local media when the user asks for transcription, summaries, tutorial analysis, viral content analysis, close reading, or Obsidian-compatible notes.
---

# Video Summary Skill

Use the existing project CLI. Do not reimplement downloading, subtitle parsing, ASR, analysis, or export logic inside the Skill.

## Project

The formal project directory is:

```text
E:\AGT\git\video-summary-skill
```

Run commands from the active repository or approved worktree. Prefer the project virtual environment:

```powershell
.\.venv\Scripts\python.exe
```

## Supported Inputs

- Public YouTube URLs.
- Public Bilibili URLs or BV identifiers accepted by the CLI.
- Other public video URLs supported by `yt-dlp`.
- Local video and audio files supported by `LocalMediaSource`.

Only process links or files the user explicitly provides.

## Current Processing Path

```text
input
-> LocalMediaSource or YtdlpSource
-> platform subtitles when available
-> FFmpeg plus local faster-whisper when subtitles are unavailable
-> normalized and grouped transcript
-> timeline and optional local-video frames
-> DeepSeek structured analysis
-> knowledge package
```

Important:

- Online video handling uses the project's `yt-dlp` path.
- Do not install, require, or invoke `bilibili-cli`.
- Do not use `--backend ollama`.
- CLI structured analysis currently uses `deepseek`.
- Local ASR uses the existing local `faster-whisper-small` model.
- Comment retrieval and comment analysis are not current features.
- Gemini text chat exists in the Web UI, but Gemini image or video understanding is not complete.

## Before Running

Check the project environment without exposing secret values:

```powershell
.\.venv\Scripts\python.exe -c "import sys; print(sys.executable)"
.\.venv\Scripts\python.exe -c "import yt_dlp; print('yt-dlp OK')"
.\.venv\Scripts\python.exe -c "import faster_whisper; print('faster-whisper OK')"
```

When ASR, media conversion, or frame extraction is needed, also check:

```powershell
ffmpeg -version
ffprobe -version
```

Do not print `.env` contents or API Keys.

## Commands

Show help:

```powershell
.\.venv\Scripts\python.exe -m src.main --help
```

Public URL summary:

```powershell
.\.venv\Scripts\python.exe -m src.main `
  --url "<public-video-url>" `
  --backend deepseek `
  --mode summary
```

Tutorial analysis:

```powershell
.\.venv\Scripts\python.exe -m src.main `
  --url "<public-video-url>" `
  --backend deepseek `
  --mode tutorial
```

Viral content analysis:

```powershell
.\.venv\Scripts\python.exe -m src.main `
  --url "<public-video-url>" `
  --backend deepseek `
  --mode viral
```

Close reading:

```powershell
.\.venv\Scripts\python.exe -m src.main `
  --url "<public-video-url>" `
  --backend deepseek `
  --mode close-reading
```

Local media:

```powershell
.\.venv\Scripts\python.exe -m src.main `
  --file "<absolute-local-media-path>" `
  --backend deepseek `
  --mode summary
```

Transcript only:

```powershell
.\.venv\Scripts\python.exe -m src.main `
  --file "<absolute-local-media-path>" `
  --no-summary
```

Short local validation:

```powershell
.\.venv\Scripts\python.exe -m src.main `
  --file "<absolute-local-media-path>" `
  --no-summary `
  --sample-seconds 30
```

Obsidian-compatible Markdown copy:

```powershell
.\.venv\Scripts\python.exe -m src.main `
  --url "<public-video-url>" `
  --backend deepseek `
  --mode summary `
  --export obsidian
```

This export creates `export_note.md`. It does not synchronize an Obsidian Vault.

## Web UI

Start with:

```powershell
.\start_web.ps1
```

or:

```bat
start_web.bat
```

Default URL:

```text
http://127.0.0.1:5188/
```

The Web UI starts processing through `src.main` using the Web process `sys.executable`. It also provides knowledge-package browsing and grounded text chat.

## Outputs

Report the created knowledge-package directory and the most relevant result files.

Core outputs:

```text
output/<knowledge-id>/index.md
output/<knowledge-id>/metadata.json
output/<knowledge-id>/manifest.json
output/<knowledge-id>/analysis.json
output/<knowledge-id>/timeline.json
output/<knowledge-id>/transcript.raw.jsonl
output/<knowledge-id>/transcript.grouped.md
output/<knowledge-id>/transcript.md
```

Conditional outputs:

```text
summary.md
chapter_summary.md
highlight_notes.md
export_note.md
chat.json
frames/*.jpg
```

When responding to the user:

1. State whether transcript acquisition used platform subtitles or local ASR when known.
2. State whether AI analysis succeeded, failed, or was skipped.
3. Include the actual provider and model recorded in `analysis.json` or `manifest.json`.
4. Provide the knowledge-package path.
5. Link or name the key result files.
6. Do not claim success based only on file existence; inspect status and meaningful content.

## Failure Handling

### Project virtual environment is not active

Run commands through:

```powershell
.\.venv\Scripts\python.exe
```

Do not fall back to a global `python` without telling the user.

### yt-dlp or faster-whisper is missing

Report the current `sys.executable` and working directory, then suggest:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### FFmpeg or FFprobe is unavailable

Explain which executable is missing. Do not silently download binaries or change the system PATH.

### Local Whisper model is incomplete

Report:

```text
未找到完整的本地 faster-whisper 模型，请先执行：
hf download Systran/faster-whisper-small --local-dir models/faster-whisper-small
```

Do not allow an implicit Hugging Face download.

### DeepSeek is not configured

Tell the user to set `DEEPSEEK_API_KEY` in the ignored project `.env`. Never request that the Key be committed or pasted into tracked files.

### Online video preview fails

The platform may prohibit embedding or require login. Processing results can still be used. Bilibili iframe playback does not provide reliable programmatic time synchronization; use source timestamp links when available.

### Gemini visual request

State that Gemini image input is not currently complete or real-API verified. Do not simulate visual understanding from subtitles.

## Safety

- Do not expose API Keys, cookies, Authorization headers, or credentials.
- Do not add `.env`, media, models, or `output/` to Git.
- Do not bypass paid content, access controls, DRM, or platform restrictions.
- Do not encourage reposting, plagiarism, or copyright infringement.
- Do not claim comment analysis, Gemini visual analysis, Vault synchronization, or Bilibili time synchronization are complete.
