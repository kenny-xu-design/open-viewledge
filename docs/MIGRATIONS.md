# Migrations

No destructive migration is performed in v1.3.

- Legacy objects without a Schema version are read using safe defaults.
- Unknown same-major fields are ignored.
- Unsupported newer major versions fail explicitly.
- Historical knowledge packages are never silently rewritten.

Future migrations must define source and target versions, backup behavior, rollback behavior, idempotency, failure handling, and automated fixtures before implementation.
