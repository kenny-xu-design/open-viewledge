# Schema Compatibility

## Versioned objects

| Object | Current Schema |
|---|---:|
| CLI result envelope | `1.0` |
| JSONL event | `1.0` |
| CLI task record | `1.0` |
| Web task record/store | `1.0` |
| Knowledge-package manifest | `1.0` |
| Analysis result | `2` |
| Export request | `1.0` |
| Configuration file | `1.0` |

## Rules

- Missing version fields in legacy data use the documented legacy default.
- New optional fields within the same major version are ignored by older readers.
- Readers never rewrite historical packages merely to add a version.
- A newer unsupported major version fails with an explicit error.
- Schema migrations must be explicit, tested, backed up where persistent user data is changed, and documented in `MIGRATIONS.md`.
- CLI output and event fields may be added compatibly in major version 1; existing field meaning cannot change.
