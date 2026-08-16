# Viewledge Side Panel prototype

This is the v1.5.1 candidate browser client prototype. It is not a published
public repository or release package.

The MV3 Side Panel requires Chrome 114 or newer. Older Chrome versions should
be upgraded before loading this unpacked client.

Canonical behavior: each video subtitle group supports copy, clip, and
highlight; web-page groups are presented as ordered page-text blocks and
additionally support an explicit inbox action. Video groups also expose
user-triggered timestamp seeking. The latest in-group selection is remembered
until submit; clip and highlight use independent idempotency keys.
The Side Panel also has an explicit focus-reading mode with larger subtitle
cards. Only loopback Bridge bases are accepted (`localhost`, `127.0.0.1`, and
`[::1]`), and remote HTTP(S) Bridge bases are rejected before requests.
The focus-reading preference is stored as a boolean in extension-local storage;
subtitle text and page contents are not stored by the client.
Remote HTTP(S) Bridge bases are rejected before any payload is sent.
Current-page URLs with embedded credentials are rejected, and URL fragments are
removed before local lookup so fragment-only state is not copied into Bridge
requests. Search text and the optional note are cleared when the matched
knowledge record changes.

## Local verification

1. Start the private core Web service at `http://127.0.0.1:5188`.
2. In Chrome extensions, enable developer mode and load this directory as an unpacked extension.
3. Copy the extension ID shown by Chrome.
4. Restart the Web service with the exact Origin:

   ```powershell
   $env:VIEWLEDGE_BRIDGE_EXTENSION_ORIGIN = "chrome-extension://<extension-id>"
   .\.venv\Scripts\python.exe -m src.web --host 127.0.0.1 --port 5188
   ```

5. Open an HTTP(S) video page with a matching local knowledge record, then open the side panel.
   Switching tabs or navigating the active tab triggers a fresh local lookup; the
   client still sends only the active page URL to the loopback Bridge.
   The extension icon opens the Side Panel after install and after a browser
   profile startup; if Chrome keeps an older extension background handler alive, reload the
   unpacked extension once before testing.

## Boundary

- Bridge CORS is closed by default and requires one exact extension Origin.
- The client does not read cookies, execute page scripts, crawl hidden content, or discover batches.
- The client does not inject subtitle text into the host page. Focus reading is
  rendered inside the extension Side Panel and is enabled only by a user click.
- The manifest declares `activeTab`, `tabs`, `sidePanel`, `storage`, and only
  local Bridge host permissions. `tabs` is used to read the active tab URL and
  title while the Side Panel follows tab changes; it does not read page body,
  cookies, or scripts.
- This directory is produced and audited by a private-core allowlist and must not seed public Git history.
