# Security And Privacy

- API Keys, cookies, Authorization headers, and credentials must never enter Git, frontend code, localStorage, task records, knowledge packages, Markdown exports, or logs.
- v1.3 development compatibility may read ignored environment configuration, but CLI JSON/config/doctor output never returns complete Keys.
- Media and transcript content is local unless an explicitly selected Provider operation sends required content to that Provider.
- No paid-content, DRM, access-control, or platform-permission bypass is implemented.
- Diagnostic exports must be sanitized before v1.5 release.

## v1.5 local-product decision

v1.5 has no registration, login, or email verification. First Web launch creates a default local workspace and offers a skippable API configuration wizard.

Text, visual, and ASR Providers are configured independently through one Provider Catalog shared by Web, CLI, and Worker. Ordinary users enter only an API Key; Base URL, recommended model, capabilities, and OpenAI-compatible custom Provider settings are advanced options.

Secrets must use Windows Credential Manager or the system Keyring when available. The frontend may receive only configured state and the last four characters. It must provide explicit test, update, and delete actions; connection tests are user-triggered and warn that a small API call may occur.
