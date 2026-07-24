# v1.4 Risks

Status: design phase only

Last updated: 2026-07-24

## Platform Subtitles

Risk: YouTube and Bilibili subtitle metadata, language names, and download behavior can change.

Mitigation:

- Keep subtitle fetch isolated in Source adapters.
- Cache successful subtitles by platform/source/language/part.
- Fall back to audio-only download and ASR when subtitles are unavailable.

## Comment Interfaces

Risk: YouTube and Bilibili public comment APIs may rate-limit, paginate differently, hide replies, or require anti-abuse handling.

Mitigation:

- Use bounded sync by default.
- Store cursors and partial results.
- Treat comment failure as a non-blocking stage warning.
- Do not mix comment claims into main summary facts.

## Gemini Capability Changes

Risk: Gemini preview video capabilities, Files API behavior, model names, quotas, and accepted YouTube URLs can change.

Mitigation:

- Determine capability only from backend request results.
- Record route status and degradation reason.
- Keep fallback routes available.
- Do not rely on Gemini Web, YouTube Ask, cookies, or browser login state.

## API Limits And Cost

Risk: Complete mode may call text, image, video, and comment services in one job.

Mitigation:

- Add Provider capability and cost metadata before enabling default complete behavior.
- Limit highlight image count.
- Limit comment pages, replies, and time range.
- Record usage and stage cost estimates when Provider data exists.

## Downloads And Rate Limits

Risk: Repeated video/audio downloads are slow and may trigger platform throttling.

Mitigation:

- Use subtitle-first and audio-only fallback.
- Add content-addressed cache keys.
- Deduplicate duplicate job submissions with idempotency keys.

## Local Model Resources

Risk: Faster-whisper can overload CPU, memory, or thermally throttle laptops.

Mitigation:

- Benchmark before defaulting thread and batch settings.
- Keep fast and complete ASR profiles separate.
- Add worker concurrency limits.
- Report model load and transcription time separately.

## Windows File Handles

Risk: Player, editor, antivirus, sync tools, or logs may hold files open.

Mitigation:

- Keep current delete error classification from `src/web.py:KnowledgeDeletionError`.
- Store v1.4 assets under the package root so recursive delete covers them.
- Avoid long-lived open handles in media and worker code.

## Cache Invalidation

Risk: Stale cache can create mismatched subtitles, frames, or analyses.

Mitigation:

- Include source identity, part, language, sample range, ASR config, Provider, model, and prompt version in cache keys.
- Store input artifact hashes on stages.
- Rerun downstream dependents when an upstream artifact changes.

## Task Recovery

Risk: Partial success may leave manifest, artifact records, and package files inconsistent.

Mitigation:

- Make stages idempotent.
- Write artifacts atomically.
- Validate output before marking a stage completed.
- Do not mark the job completed until required stages pass.

## Privacy And Keys

Risk: Video URLs, transcripts, comments, local paths, and API Keys can leak through logs or exports.

Mitigation:

- Keep secrets out of frontend storage, task records, packages, exports, and logs.
- Redact Provider errors with existing `sanitize_message()` behavior.
- Use package-relative paths for frontend/export payloads.

## Comment Safety

Risk: Comments can contain spam, harassment, false claims, prompt injection, personal data, or illegal content.

Mitigation:

- Treat comments as untrusted data.
- Filter obvious spam/duplicates.
- Keep comment insight prompts fact-separating.
- Mark claims that need verification.

## External Service Outages

Risk: yt-dlp-supported platforms, DeepSeek, Gemini, or comment endpoints may be unavailable.

Mitigation:

- Preserve completed local artifacts.
- Let each optional stage fail independently.
- Expose retryable error codes and stage-level retry.
