# v1.4 Data Contracts

Status: v1.4.0-v1.4.3 contracts implemented; later-unit contracts remain design

Last updated: 2026-07-26

## Compatibility Rules

- Existing packages and task records without new v1.4 fields remain readable.
- New fields are optional within schema major version 1 unless a future migration explicitly bumps the major version.
- Readers must tolerate missing v1.4 artifacts.
- Writers must not rewrite historical packages just to add defaults.
- CLI JSONL event meanings from contract version `1.0` remain stable.

## processing_profile

Purpose: decide how work is executed.

Values:

- `fast`.
- `complete`.

Default mapping:

- Missing field in old CLI task, Web job, or manifest: treat as `complete` to preserve current behavior.
- New Web task default can be `fast` only after the UI and CLI explicitly display the choice. Until then, keep `complete`.
- `--no-frames` remains compatible and can override visual stages inside `complete`.

Must stay separate from `analysis_profile`.

## Job

Suggested fields:

```json
{
  "schema_version": "1.0",
  "job_id": "string",
  "idempotency_key": "string",
  "source_type": "url|file",
  "source": "string",
  "source_fingerprint": "string",
  "analysis_profile": "summary",
  "processing_profile": "fast|complete",
  "analysis_requested": true,
  "analysis_status": "pending|completed|failed|timeout|skipped",
  "analysis_skip_reason": "",
  "analysis_provider": "deepseek",
  "analysis_model": "string",
  "transcript_only": false,
  "status": "queued|running|partial_success|completed|failed|cancelled|interrupted",
  "priority": 0,
  "created_at": "iso8601",
  "updated_at": "iso8601",
  "started_at": "iso8601",
  "completed_at": "iso8601",
  "knowledge_id": "string",
  "output_dir": "string",
  "error_code": "string",
  "error_message": "string"
}
```

Relationship to current code:

- Replaces or wraps `src/cli_tasks.py:CliTaskRecord` and `src/job_store.py:Job`.
- Must preserve `task_id` returned by `src.main.run_pipeline()` during transition.

## Stage

Suggested stages:

- `metadata`.
- `subtitle_fetch`.
- `media_download`.
- `audio_extract`.
- `transcription`.
- `normalize_transcript`.
- `group_transcript`.
- `text_analysis`.
- `keyframe_extract`.
- `visual_analysis`.
- `highlight_snapshot`.
- `comments_fetch`.
- `comments_analysis`.
- `package_build`.
- `export`.

Fields:

```json
{
  "stage_id": "string",
  "job_id": "string",
  "name": "text_analysis",
  "status": "pending|ready|running|completed|skipped|warning|failed|cancelled",
  "started_at": "iso8601",
  "completed_at": "iso8601",
  "duration_ms": 0,
  "attempt": 1,
  "max_attempts": 3,
  "error_code": "string",
  "error_message": "string",
  "input_artifacts": ["artifact_id"],
  "output_artifacts": ["artifact_id"],
  "cache_hit": false,
  "cache_key": "string"
}
```

## Artifact

Artifacts describe reusable outputs without exposing secrets.

```json
{
  "artifact_id": "string",
  "job_id": "string",
  "stage": "subtitle_fetch",
  "type": "metadata|subtitle|audio|transcript|analysis|frame|tutorial_image|comments|comment_insight|export",
  "path": "relative/or/safe/local/path",
  "sha256": "string",
  "size_bytes": 0,
  "created_at": "iso8601",
  "cache_key": "string",
  "source": "generated|cache|external",
  "status": "available|missing|invalid"
}
```

Frontend payloads should use package-relative paths or API URLs, not absolute local paths.

## Highlight

Current baseline: `src/domain/models.py:HighlightItem` has `title`, `explanation`, `tags`, `start`, `end`, and `icon`.

v1.4 compatible extension:

```json
{
  "timestamp": 120.5,
  "title": "string",
  "summary": "string",
  "tags": ["string"],
  "image": "",
  "image_source_timestamp": 121.0,
  "image_generation_status": "generated|reused|skipped|failed"
}
```

Compatibility:

- Existing `start` maps to `timestamp`.
- Existing `explanation` maps to `summary`.
- Missing `image` means text-only highlight. Legacy packages may contain `assets/highlights/*.webp`, but new main-report screenshot export is restricted to tutorial steps.

## Analysis Result

Current analysis files use a common envelope and restored flat base fields. `tutorial`, `viral`, and `close-reading` may additionally use mode-specific `content`.

Envelope:

```json
{
  "schema_version": "2",
  "status": "success|failed|timeout|skipped",
  "analysis_profile": "summary|tutorial|viral|close-reading",
  "processing_profile": "fast|complete",
  "source": {"platform": "string", "url": "string", "title": "string", "source_id": "string"},
  "generation": {"visual_context_used": false, "comments_included": false},
  "segmentation": {
    "policy_version": "adaptive-v2",
    "duration_seconds": 4270,
    "duration_bucket": "60m_plus",
    "policy": "long_tutorial",
    "strategy": "hierarchical_semantic_map_reduce",
    "window_seconds": 360,
    "overlap_seconds": 60,
    "chapter_target_range": [12, 20],
    "highlight_target_range": [10, 18],
    "actual_chapter_count": 10,
    "actual_highlight_count": 9,
    "actual_tutorial_step_count": 24,
    "coverage_ratio": 0.94,
    "largest_uncovered_gap_seconds": 420,
    "reanalysis_count": 1
  },
  "warnings": [],
  "summary": "string",
  "terminology": [{"term": "string", "definition": "string"}],
  "highlights": [],
  "thoughts": [],
  "chapters": [],
  "content": {}
}
```

Rules:

- All four profiles write the restored flat base fields `summary`, `terminology`, `highlights`, `thoughts`, and `chapters`.
- `summary` does not require a canonical `content` object. Historical summary `content` remains readable through compatibility normalization.
- `tutorial`, `viral`, and `close-reading` retain distinct mode-specific `content` fields, but writers return empty strings/arrays for unsupported optional facts and renderers hide empty modules.
- `terminology` is produced in the same Provider response for every profile. Renderers show 3–8 distinct terms only when each has a non-placeholder definition; fewer than 3 hides the module without placeholder text.
- Legacy fields such as `summary`, `highlights`, `chapters`, `steps`, `glossary`, and `action_items` remain readable and are synchronized where possible.
- Comment insights remain in `comment_insights.json` / `comment_insights.md`, not in `analysis.json`.
- Missing or unsupported optional modules use empty strings/arrays. “未明确说明” may appear only when it is meaningful inside an existing item, not to force a report section.
- API Keys, Cookie, Token, Authorization headers, and credentials are not valid analysis content.
- Tutorial stages use top-level `chapters`; `content.steps` links back through `chapter_id`. Historical `content.chapter_summaries` remains readable.
- Close-reading chapters use top-level `chapters`; historical `content.chapter_close_reading` remains readable.
- `SegmentationPolicyRouter` controls window use, window size/overlap, chapter/highlight density guidance, and hierarchical reduction only. It must preserve populated mode-specific content while reducing windows and must not decide report headings or optional-module visibility.

## Tutorial Image

Storage:

```text
assets/tutorial/tutorial_step_001.webp
assets/tutorial/tutorial_step_002.webp
```

Rules:

- Only `tutorial + complete` may generate or export these images.
- One image per key tutorial step maximum.
- Deduplicate by timestamp window and perceptual or hash-based similarity.
- Markdown and Obsidian exports reference relative paths only.
- `summary`, `viral`, `close-reading`, and `tutorial + fast` do not export screenshots.

## NormalizedComment

```json
{
  "comment_id": "string",
  "parent_id": "string",
  "author": "string",
  "content": "string",
  "likes": 0,
  "reply_count": 0,
  "is_pinned": false,
  "is_creator": false,
  "published_at": "iso8601",
  "source_url": "string",
  "timestamps": [120.0],
  "platform": "youtube|bilibili",
  "sync_cursor": "string",
  "fetched_at": "iso8601"
}
```

Private profile URLs, cookies, and credentials are not stored.

## Comment Insight

```json
{
  "status": "success|skipped|failed",
  "provider": "string",
  "model": "string",
  "generated_at": "iso8601",
  "hot_topics": ["string"],
  "consensus": ["string"],
  "controversies": ["string"],
  "corrections": ["string"],
  "frequent_questions": ["string"],
  "recommended_segments": [{"timestamp": 0, "reason": "string"}],
  "needs_verification": ["string"],
  "error": "string"
}
```

Comment insights must remain separate from `analysis.json` main summary facts.

## Chat

Current baseline: `src/chat_store.py:ChatStore` stores `knowledge_id`, `updated_at`, and local `messages`.

v1.4 video conversation extension:

```json
{
  "chat_id": "string",
  "knowledge_id": "string",
  "source_url": "string",
  "source_fingerprint": "string",
  "provider": "gemini",
  "model": "string",
  "route": "gemini_youtube_url|gemini_files_api|gemini_frames_text|text_only",
  "route_status": "available|degraded|failed|expired",
  "remote_session_id": "string",
  "remote_file_id": "string",
  "remote_expires_at": "iso8601",
  "messages": []
}
```

If remote state expires, the next request should try to restore through the same route planner and record the degradation path.

## Knowledge Manifest

Current baseline: `ProcessingManifest` contains `schema_version`, `task_id`, `source`, status fields, Provider fields, `analysis_profile`, errors, `output_files`, `stage_status`, and `provider_attempts`.

v1.4 compatible fields:

```json
{
  "processing_profile": "fast|complete",
  "analysis_requested": true,
  "analysis_status": "pending|completed|failed|timeout|skipped",
  "analysis_skip_reason": "",
  "analysis_provider": "deepseek",
  "analysis_model": "string",
  "transcript_only": false,
  "stage_metrics": {
    "subtitle_fetch": {
      "duration_ms": 100,
      "cache_hit": false,
      "attempt": 1
    }
  },
  "first_readable_result_at": "iso8601",
  "first_readable_result_duration_ms": 0,
  "artifact_refs": [],
  "cache_keys": {},
  "partial_success": false
}
```

Migration:

- Missing `processing_profile`: `complete`.
- Missing analysis-request fields: infer transcript-only only from an explicit
  historical `--no-summary` command or skipped manifest; new tasks default to
  `analysis_requested=true`.
- `skipped` is reserved for an explicit transcript-only request. Missing API
  configuration and request errors are `failed`; request timeouts are `timeout`.
- `transcript_ready` and `analysis_ready` are derived independently by readers.
  `analysis_ready` requires a valid structured success result with meaningful
  analysis content.
- Missing `stage_metrics`: derive only coarse status from `stage_status`.
- Missing comment/visual artifacts: treat as not generated, not failed.

## Output Files

Core existing files remain:

- `index.md`.
- `metadata.json`.
- `manifest.json`.
- `analysis.json`.
- `timeline.json`.
- `source.md`.
- `transcript.raw.jsonl`.
- `transcript.grouped.md`.
- `transcript.md`.

v1.4 optional files:

- `assets/tutorial/*.webp`.
- legacy `assets/highlights/*.webp`.
- `visual_insights.json`.
- `visual_insights.md`.
- `comments.json`.
- `comments.md`.
- `comment_insights.md`.

Deletion remains safe if all v1.4 artifacts stay inside the knowledge package directory, because `src/web.py:_remove_knowledge_directory()` recursively removes the validated package root.
