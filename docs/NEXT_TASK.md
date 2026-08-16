# Next Task

Complete the remaining user-facing v1.5.1 Chrome unpacked-extension smoke,
including the Side Panel focus-reading mode.
The disposable private-core portion is automated in `scripts/smoke_v15.py`,
and `scripts/smoke_side_panel_dom.html` now executes the actual Side Panel UI
against mocked local Bridge responses; neither substitutes for Chrome's real
MV3 permission, extension-origin CORS, and service-worker lifecycle behavior.
Load the allowlisted
`public_boundary/client` directory as an unpacked MV3 extension, set the exact
`VIEWLEDGE_BRIDGE_EXTENSION_ORIGIN` shown by Chrome, restart the local Web
service, and verify that a known HTTP video page resolves to the newest opaque
knowledge record and renders ordered subtitle groups. Select part of a group,
click “剪藏”, retry the same action after a simulated lost response, and verify
that the Bridge idempotency key produces one clip only. Verify that unmatched
pages show a sanitized Retry state, no cookies or local paths are exposed, and
arbitrary extension origins remain blocked. Keep the v1.4.6 duplicate
contract, reject remote Bridge bases, accept only loopback bases
(`localhost`, `127.0.0.1`, `[::1]`), and do not create a public repository,
stage, commit, push, merge, rebase, or tag.
