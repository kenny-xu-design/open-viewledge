# Task Lifecycle

## v1.3 synchronous CLI task

```text
created -> running -> completed
                   -> failed -> running (resume)
                   -> cancelled
```

The v1.3 task record is a small local invocation record, not a Scale queue. It stores source, non-secret options, result location, exit code, and sanitized error information below `.local/cli_tasks/`.

The processing manifest separately records pipeline stages:

```text
resolve_source
collect_metadata
acquire_transcript
normalize_transcript
group_transcript
build_timeline
extract_frames
run_analysis
export_knowledge_package
```

v1.4 may introduce queued/leased execution, but it must preserve the v1.3 public CLI and event contract.
