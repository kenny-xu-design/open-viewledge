---
name: video-summary
description: Use the video-summary-skill public CLI to analyze user-provided public video URLs or local audio/video files, inspect knowledge packages, export Markdown, diagnose configuration, or resume a failed CLI task.
---

# Video Summary Skill

Use this Skill when the user asks to process an explicitly provided public video URL or local media file, inspect an existing knowledge package, export existing results, diagnose the local installation, or resume a failed task.

Run only the public CLI from the active repository or approved worktree:

```powershell
.\.venv\Scripts\python.exe -m src.main <command>
```

Do not import or invoke internal pipeline classes from the Skill. Do not duplicate prompts or media-processing logic.

## Analyze

Exactly one input is required:

```powershell
.\.venv\Scripts\python.exe -m src.main analyze --url "<public-url>" --mode summary --jsonl
.\.venv\Scripts\python.exe -m src.main analyze --file "<absolute-media-path>" --mode summary --jsonl
```

Useful optional arguments:

```text
--lang <language>
--backend deepseek
--mode <summary|tutorial|viral|close-reading>
--no-summary
--no-frames
--sample-seconds <positive-integer>
--export obsidian
--config <path>
```

Use `--jsonl` for long runs. Read one JSON object per stdout line. Treat stderr as diagnostics only.

Required lifecycle events:

```text
task_created
stage_started
progress
artifact_created
warning
stage_completed
task_failed
task_completed
```

On `task_completed`, read `result.task_id`, `result.knowledge_id`, `result.output_dir`, analysis Provider/model/status, and artifact paths.

## Inspect

Always inspect a generated package before claiming success:

```powershell
.\.venv\Scripts\python.exe -m src.main inspect "<package-directory>" --json
```

Read `data.valid`, `data.level`, analysis/manifest status, transcript count, and issues. Inspection never modifies the package.

## Export

```powershell
.\.venv\Scripts\python.exe -m src.main export --knowledge-id "<id>" --format markdown --preset full --json
```

Read the exported `data.file_path` and included sections. Export uses existing artifacts and never invokes a model.

## Resume

If analyze returns a failed task with a `task_id`, preserve that ID and run:

```powershell
.\.venv\Scripts\python.exe -m src.main resume "<task-id>" --jsonl
```

Resume reuses the original secret-free source and options. Do not resume completed tasks.

## Diagnose and read configuration

```powershell
.\.venv\Scripts\python.exe -m src.main doctor --json
.\.venv\Scripts\python.exe -m src.main config --json
```

These commands report status without returning complete API Keys.

## Exit codes

```text
0 success
1 general failure or inspection warning
2 usage/configuration error
3 inaccessible input or task record
4 required Provider not configured
5 required external tool/model missing
6 damaged or unsupported knowledge package/Schema
7 cancelled
8 retryable temporary failure
```

Retry automatically only for exit code `8`, or use `resume` after the underlying issue is corrected. For exit codes `2` through `6`, report the specific JSON error and required user action.

## Output handling

Report the knowledge-package directory and key artifacts returned by the CLI. Never infer success from file existence alone. Never expose or store API Keys, cookies, Authorization headers, local `.env` contents, or credentials in messages, logs, task records, knowledge packages, or exports.
