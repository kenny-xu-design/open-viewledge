# Exit Codes

The CLI uses one centralized exit-code table.

| Code | Name | Meaning |
|---:|---|---|
| 0 | `SUCCESS` | Command completed successfully. |
| 1 | `EXECUTION_FAILED` | General execution failure, or an `inspect` compatibility warning. |
| 2 | `USAGE_OR_CONFIG` | Invalid arguments or invalid configuration. |
| 3 | `INPUT_INACCESSIBLE` | Input or requested local record cannot be accessed. |
| 4 | `PROVIDER_NOT_CONFIGURED` | Required Provider credentials/configuration are missing. |
| 5 | `EXTERNAL_TOOL_MISSING` | FFmpeg, FFprobe, yt-dlp, faster-whisper, or a required local model is unavailable. |
| 6 | `KNOWLEDGE_PACKAGE_DAMAGED` | A package or persisted Schema is invalid or unsupported. |
| 7 | `CANCELLED` | The task was cancelled. Reserved in v1.3 for the stable contract. |
| 8 | `RETRYABLE_FAILURE` | A temporary failure may succeed on retry. |

JSON errors contain the symbolic name, numeric exit code, message, and `retryable` boolean. Tests lock the numeric mapping.
