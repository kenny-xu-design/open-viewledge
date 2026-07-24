# CLI Contract

Contract version: `1.0`

The only public command entry point is:

```powershell
python -m src.main <command> [options]
```

Public commands:

```text
analyze
inspect
export
resume
doctor
config
```

## Output modes

Every public command supports `--json`. `analyze` and `resume` additionally support `--jsonl`.

- stdout contains only the requested result representation.
- stderr contains diagnostics, progress text, warnings, and deprecation messages.
- `--json` writes one envelope with `schema_version`, `command`, `success`, `timestamp`, and `data` or `error`.
- `--jsonl` writes one event object per line and never mixes human log lines into stdout.
- `--json` and `--jsonl` are mutually exclusive.

## analyze

Exactly one input is required:

```powershell
python -m src.main analyze --url <public-url> [options]
python -m src.main analyze --file <local-media-path> [options]
```

Stable options:

```text
--url
--file
--lang
--backend
--mode
--processing-profile
--export
--no-summary
--no-frames
--sample-seconds
--config
--json
--jsonl
```

`--processing-profile` accepts `fast` or `complete`. Missing values default to `complete`, so v1.3 commands keep their existing execution behavior. The field is independent from `--mode`: mode selects the analysis shape, while processing profile selects how the pipeline executes. `fast` requests audio-only media when subtitles are unavailable and skips keyframe extraction; `complete` retains the existing full plan. `--no-frames` continues to disable frame generation independently.

The deprecated root-level form remains accepted and mirrors `--processing-profile` during its compatibility window. `--comments` remains accepted only as a deprecated no-op and is never silent.

Successful data includes `task_id`, `knowledge_id`, `output_dir`, task status, `analysis_profile`, `processing_profile`, analysis status, Provider/model, and artifact paths.

## inspect

```powershell
python -m src.main inspect <package-directory> --json
```

Inspection is read-only. Valid packages exit `0`, packages with compatibility warnings exit `1`, and damaged packages exit `6`.

## export

```powershell
python -m src.main export --knowledge-id <id> --format markdown --preset full --json
```

Export reads existing artifacts only. It never invokes a model or extracts frames.

## resume

```powershell
python -m src.main resume <task-id> --jsonl
```

`analyze` stores a secret-free task record below `.local/cli_tasks/`. `resume` reuses its original source and options. Completed tasks are not rerun through `resume`.

## doctor

```powershell
python -m src.main doctor --json
```

Checks Python, package and Schema versions, FFmpeg/FFprobe, yt-dlp, faster-whisper, the local Whisper model, Provider configuration, output storage, optional Obsidian Vault configuration, and Web local storage. It never returns complete API Keys.

## config

```powershell
python -m src.main config --config config.example.json --json
```

Returns the effective non-secret configuration. Secrets remain environment or credential-service concerns and are not part of this output.

## JSONL events

The event vocabulary is stable within CLI contract major version 1:

```text
task_created
stage_started
progress
artifact_created
warning
first_readable_result
stage_completed
task_failed
task_completed
```

Every event contains `schema_version`, `event`, `task_id`, and `timestamp`. `task_created` includes separate `analysis_profile` and `processing_profile` fields. Stage events include `stage`; completion events may also include `duration_ms`, `attempt`, and `cache_hit`. Progress events include a number from `0` through `1`. Existing v1.3 consumers remain compatible because the event names and required fields are unchanged.
