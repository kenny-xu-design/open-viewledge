from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.public_boundary import BoundaryError, build_staging, scan_tree, verify_staging


class PublicBoundaryTests(unittest.TestCase):
    def test_allowlist_build_copies_only_reviewed_files_and_hashes_them(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp) / "private"
            root.mkdir()
            (root / "public_boundary" / "schemas").mkdir(parents=True)
            (root / "public_boundary" / "schemas" / "bridge.json").write_text(
                '{"schema_version":"1.0"}\n', encoding="utf-8"
            )
            (root / "secret.txt").write_text("not allowlisted", encoding="utf-8")
            allowlist = root / "public_boundary" / "allowlist.json"
            allowlist.write_text(
                json.dumps(
                    {
                        "manifest_version": "1",
                        "public_repository": "example-client",
                        "schema_versions": {"bridge_api": "1.0"},
                        "fresh_history_required": True,
                        "private_history_reuse_forbidden": True,
                        "sensitive_scan_required": True,
                        "entries": [
                            {
                                "source": "public_boundary/schemas/bridge.json",
                                "destination": "schemas/bridge.json",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            output = Path(temp) / "staging"

            publication = build_staging(root, allowlist, output)

            self.assertTrue((output / "schemas" / "bridge.json").is_file())
            self.assertFalse((output / "secret.txt").exists())
            self.assertEqual(publication["files"][0]["path"], "schemas/bridge.json")
            generated = json.loads((output / "publication-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(generated["schema_versions"]["bridge_api"], "1.0")
            self.assertEqual(len(generated["files"][0]["sha256"]), 64)

    def test_allowlist_build_never_copies_git_metadata(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp) / "private"
            root.mkdir()
            (root / ".git").mkdir()
            (root / ".git" / "config").write_text("private history", encoding="utf-8")
            (root / "public.txt").write_text("public contract", encoding="utf-8")
            allowlist = root / "allowlist.json"
            allowlist.write_text(
                json.dumps(
                    {
                        "manifest_version": "1",
                        "public_repository": "example-client",
                        "fresh_history_required": True,
                        "private_history_reuse_forbidden": True,
                        "entries": [{"source": "public.txt", "destination": "public.txt"}],
                    }
                ),
                encoding="utf-8",
            )
            output = Path(temp) / "staging"

            build_staging(root, allowlist, output)

            self.assertFalse((output / ".git").exists())
            self.assertFalse(any(path.name == "config" for path in output.rglob("*")))

    def test_build_rejects_staging_inside_private_root(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            allowlist = root / "allowlist.json"
            allowlist.write_text(
                json.dumps(
                    {
                        "manifest_version": "1",
                        "public_repository": "example-client",
                        "fresh_history_required": True,
                        "private_history_reuse_forbidden": True,
                        "entries": [{"source": "safe.txt", "destination": "safe.txt"}],
                    }
                ),
                encoding="utf-8",
            )
            (root / "safe.txt").write_text("safe", encoding="utf-8")

            with self.assertRaises(BoundaryError):
                build_staging(root, allowlist, root / "staging")

    def test_scan_rejects_sensitive_content_and_private_paths(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "safe.md").write_text("A public contract.\n", encoding="utf-8")
            (root / "notes").mkdir()
            (root / "notes" / "debug.log").write_text("debug", encoding="utf-8")
            (root / "safe.json").write_text(
                '{"authorization": "Bearer fake-token-value"}\n', encoding="utf-8"
            )

            findings = scan_tree(root)
            rules = {finding["rule"] for finding in findings}

            self.assertIn("denied_filename", rules)
            self.assertIn("bearer_token", rules)

    def test_scan_accepts_public_schema_fixture(self) -> None:
        findings = scan_tree(Path("public_boundary") / "schemas")
        self.assertEqual(findings, [])

    def test_generated_manifest_can_be_verified_and_tampering_is_rejected(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp) / "private"
            root.mkdir()
            (root / "public_boundary" / "schemas").mkdir(parents=True)
            (root / "public_boundary" / "schemas" / "bridge.json").write_text(
                '{"schema_version":"1.0"}\n', encoding="utf-8"
            )
            allowlist = root / "public_boundary" / "allowlist.json"
            allowlist.write_text(
                json.dumps(
                    {
                        "manifest_version": "1",
                        "public_repository": "example-client",
                        "fresh_history_required": True,
                        "private_history_reuse_forbidden": True,
                        "entries": [
                            {
                                "source": "public_boundary/schemas/bridge.json",
                                "destination": "schemas/bridge.json",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            output = Path(temp) / "staging"
            build_staging(root, allowlist, output)

            verified = verify_staging(output)
            self.assertEqual(verified["files"][0]["path"], "schemas/bridge.json")
            (output / "schemas" / "bridge.json").write_text("tampered\n", encoding="utf-8")
            with self.assertRaises(BoundaryError):
                verify_staging(output)

    def test_public_schema_examples_are_independent_of_private_modules(self) -> None:
        schema_path = Path("public_boundary/schemas/bridge_api_v1.schema.json")
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        serialized = json.dumps(schema, ensure_ascii=False).casefold()
        for forbidden in ("src/", "src\\", "provider", "prompt", "worker", "filesystem"):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(schema["$id"], "https://schemas.viewledge.example/bridge/1.0/envelope.json")
        self.assertEqual(schema["properties"]["schema_version"]["const"], "1.0")
        valid_data = {"schema_version": "1.0", "request_id": "r1", "data": {"state": "queued"}}
        valid_error = {
            "schema_version": "1.0",
            "request_id": "r2",
            "error": {"code": "duplicate_intake", "message": "Already queued", "retryable": False},
        }
        for payload in (valid_data, valid_error):
            self.assertEqual(payload["schema_version"], "1.0")
            self.assertEqual("data" in payload, "error" not in payload)

    def test_side_panel_schema_covers_source_resolution_matches(self) -> None:
        schema = json.loads(Path("public_boundary/schemas/side_panel_v1.schema.json").read_text(encoding="utf-8"))
        serialized = json.dumps(schema, ensure_ascii=False).casefold()
        for forbidden in ("src/", "src\\", "provider", "prompt", "filesystem"):
            self.assertNotIn(forbidden, serialized)
        self.assertIn("source_url", schema["properties"])
        self.assertIn("matches", schema["properties"])
        self.assertEqual(schema["properties"]["groups"]["items"]["properties"]["start"]["type"], ["number", "null"])
        self.assertEqual(schema["properties"]["groups"]["items"]["properties"]["end"]["type"], ["number", "null"])
        self.assertEqual(schema["properties"]["groups"]["items"]["properties"]["contentKind"]["enum"], ["video_subtitle", "web_page"])
        self.assertEqual(schema["properties"]["matches"]["items"]["required"], ["knowledge_id", "title", "source"])
        self.assertEqual(schema["properties"]["source"]["properties"]["url"]["type"], ["string", "null"])
        groups = schema["properties"]["groups"]["items"]
        self.assertEqual(groups["required"], ["index", "text", "start", "end", "contentKind"])
        self.assertFalse(groups["additionalProperties"])
        self.assertEqual(groups["oneOf"][0]["properties"]["contentKind"]["const"], "video_subtitle")
        self.assertEqual(groups["oneOf"][1]["properties"]["contentKind"]["const"], "web_page")
        self.assertIn("position", groups["oneOf"][1]["required"])

    def test_side_panel_client_is_allowlisted_and_does_not_contain_private_pipeline(self) -> None:
        allowlist = json.loads(Path("public_boundary/allowlist.json").read_text(encoding="utf-8"))
        destinations = {entry["destination"] for entry in allowlist["entries"]}
        expected = {
            "client/manifest.json",
            "client/service_worker.js",
            "client/bridge_client.js",
            "client/side_panel.html",
            "client/side_panel.css",
            "client/side_panel.js",
            "client/README.md",
        }
        self.assertTrue(expected <= destinations)
        manifest = json.loads(Path("public_boundary/client/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["manifest_version"], 3)
        self.assertEqual(manifest["minimum_chrome_version"], "114")
        self.assertIn("activeTab", manifest["permissions"])
        self.assertIn("tabs", manifest["permissions"])
        self.assertNotIn("<all_urls>", manifest.get("host_permissions", []))
        self.assertIn("http://127.0.0.1:5188/*", manifest["host_permissions"])
        self.assertIn("http://localhost:5188/*", manifest["host_permissions"])
        self.assertIn("http://[::1]:5188/*", manifest["host_permissions"])
        client_root = Path("public_boundary/client")
        self.assertTrue((client_root / manifest["background"]["service_worker"]).is_file())
        self.assertTrue((client_root / manifest["side_panel"]["default_path"]).is_file())
        self.assertEqual(manifest["background"]["type"], "module")
        self.assertEqual(manifest["side_panel"]["default_path"], "side_panel.html")
        client_text = "\n".join(path.read_text(encoding="utf-8") for path in Path("public_boundary/client").glob("*"))
        service_worker = (client_root / "service_worker.js").read_text(encoding="utf-8")
        self.assertIn("function configureSidePanel()", service_worker)
        self.assertIn("chrome.runtime.onInstalled.addListener(configureSidePanel)", service_worker)
        self.assertIn("chrome.runtime.onStartup.addListener(configureSidePanel)", service_worker)
        self.assertIn("openPanelOnActionClick: true", service_worker)
        for forbidden in ("DEEPSEEK", "GROQ", "GEMINI", "api_key", "Authorization", "src/"):
            self.assertNotIn(forbidden.casefold(), client_text.casefold())
        self.assertIn("credentials: \"omit\"", client_text)
        self.assertIn("export function validateBridgeEnvelope(payload)", client_text)
        self.assertIn('payload.schema_version !== "1.0"', client_text)
        self.assertIn("hasData === hasError", client_text)
        self.assertIn("return payload.data", client_text)
        self.assertTrue(Path("scripts/test_bridge_client.mjs").is_file())
        self.assertIn("validateBridgeBase", client_text)
        self.assertIn("127.0.0.1", client_text)
        self.assertIn("localhost", client_text)
        self.assertIn("[::1]", client_text)
        self.assertIn("Remote HTTP(S)", Path("public_boundary/client/README.md").read_text(encoding="utf-8"))
        side_panel_markup = Path("public_boundary/client/side_panel.html").read_text(encoding="utf-8")
        self.assertIn("&#23383;&#24149;&#20391;&#26639;", side_panel_markup)
        self.assertNotIn("瀛楀箷", side_panel_markup)
        side_panel_code = Path("public_boundary/client/side_panel.js").read_text(encoding="utf-8")
        self.assertIn("selections", side_panel_code)
        self.assertIn("rememberSelection", side_panel_code)
        self.assertIn("requestIds", side_panel_code)
        self.assertIn("requestIdFor", side_panel_code)
        self.assertIn("fingerprint = \"\"", side_panel_code)
        self.assertIn("existing.fingerprint !== fingerprint", side_panel_code)
        self.assertIn('requestIdFor(group, "intake", text)', side_panel_code)
        self.assertIn("state.requestIds.clear()", side_panel_code)
        self.assertNotIn("姝ｅ湪璇诲彇", side_panel_code)
        self.assertIn("/v1/knowledge/resolve", client_text)
        self.assertIn("/v1/knowledge/${encodeURIComponent(id)}/transcript", client_text)
        self.assertIn("/v1/clips", client_text)
        self.assertIn('...options,\n    // Keep the public client credential-free', client_text)
        self.assertIn('credentials: "omit",', client_text)
        self.assertIn("for (const [name, value] of new Headers(options.headers || {}))", client_text)
        self.assertIn('normalized === "content-type"', client_text)
        self.assertIn('normalized === "idempotency-key"', client_text)
        self.assertIn('kind, target', client_text)
        self.assertIn('"highlight"', client_text)
        self.assertIn("highlight", side_panel_markup)
        self.assertIn("class=\"seek\"", side_panel_markup)
        self.assertIn('id="note"', side_panel_markup)
        self.assertIn('maxlength="500"', side_panel_markup)
        self.assertIn('id="retry"', side_panel_markup)
        self.assertIn('id="readingMode"', side_panel_markup)
        self.assertIn('id="search-label"', side_panel_markup)
        self.assertIn('id="note-label"', side_panel_markup)
        self.assertIn('slice(0, 500)', side_panel_code)
        self.assertIn("/v1/intakes", client_text)
        self.assertIn("createIntake", client_text)
        self.assertIn("content_upload_allowed: false", client_text)
        self.assertIn("intakeGroup", client_text)
        self.assertIn("publicError", side_panel_code)
        self.assertIn("fallback = message.readFailed", side_panel_code)
        self.assertIn('code === "bridge_invalid"', side_panel_code)
        self.assertIn("回环主机", side_panel_code)
        self.assertIn("publicError(error, message.clipFailed)", side_panel_code)
        self.assertIn("publicError(error, message.inboxFailed)", side_panel_code)
        self.assertIn("classList.toggle(\"hidden\", !error)", side_panel_code)
        self.assertIn('addEventListener("click", load)', side_panel_code)
        self.assertIn("chrome.tabs.onActivated?.addListener(scheduleLoad)", side_panel_code)
        self.assertIn("chrome.tabs.onUpdated?.addListener", side_panel_code)
        self.assertIn("async (tabId, changeInfo)", side_panel_code)
        self.assertIn("tabs?.[0]?.id === tabId", side_panel_code)
        self.assertIn("reloadTimer: 0", side_panel_code)
        self.assertIn("function scheduleLoad()", side_panel_code)
        self.assertIn('window.addEventListener("pagehide"', side_panel_code)
        self.assertIn("state.loadSequence += 1", side_panel_code)
        self.assertIn('toggleAttribute("disabled", value === message.loading)', side_panel_code)
        self.assertIn("chrome.tabs.onActivated?.addListener(scheduleLoad)", side_panel_code)
        self.assertIn("function setReadingMode(enabled)", side_panel_code)
        self.assertIn("focus-reading", side_panel_code)
        self.assertIn("chrome.storage.local.set({ readingMode: state.readingMode })", side_panel_code)
        self.assertIn("async function restoreReadingMode()", side_panel_code)
        self.assertIn("async function seekGroup(group)", side_panel_code)
        self.assertIn("function pageIdentityUrl(value)", side_panel_code)
        self.assertIn('loadedRecordKey: ""', side_panel_code)
        self.assertIn("state.loadedRecordKey !== recordKey", side_panel_code)
        self.assertIn('$("#search").value = ""', side_panel_code)
        self.assertIn('$("#note").value = ""', side_panel_code)
        self.assertIn("loadSequence: 0", side_panel_code)
        self.assertIn("const sequence = ++state.loadSequence", side_panel_code)
        self.assertIn("if (sequence !== state.loadSequence) return", side_panel_code)
        self.assertIn('url.searchParams.delete("t")', side_panel_code)
        self.assertIn('pageIdentityUrl(activeUrl) !== pageIdentityUrl(state.pageUrl)', side_panel_code)
        self.assertIn("Refresh subtitles before seeking.", side_panel_code)
        self.assertIn("chrome.tabs.update({ url: url.toString() })", side_panel_code)
        self.assertIn("seek.classList.toggle(\"hidden\", !video)", side_panel_code)
        self.assertIn("intake.classList.toggle(\"hidden\", video)", side_panel_code)
        self.assertIn('source.kind !== "web_page"', side_panel_code)
        self.assertIn("Inbox capture is available only for page text blocks.", side_panel_code)
        self.assertIn("No matching page text blocks.", side_panel_code)
        self.assertIn('"Search page text"', side_panel_code)
        self.assertIn('"page text blocks"', side_panel_code)
        self.assertIn("resolveSource(state.bridgeBase, pageIdentityUrl(pageUrl))", side_panel_code)
        self.assertIn("web-page groups are presented as ordered page-text blocks", Path("public_boundary/client/README.md").read_text(encoding="utf-8"))
        self.assertIn("Could not copy text.", side_panel_code)
        self.assertNotIn("setStatus(error?.message", side_panel_code)
        self.assertIn("parsed.username || parsed.password", client_text)
        self.assertIn('parsed.hash = ""', client_text)

    def test_side_panel_client_build_is_allowlist_only(self) -> None:
        with TemporaryDirectory() as temp:
            output = Path(temp) / "staging"
            publication = build_staging(Path("."), Path("public_boundary/allowlist.json"), output)
            paths = {item["path"] for item in publication["files"]}
            self.assertEqual(paths, {
                "schemas/README.md",
                "schemas/bridge_api_v1.schema.json",
                "schemas/side_panel_v1.schema.json",
                "client/manifest.json",
                "client/service_worker.js",
                "client/bridge_client.js",
                "client/side_panel.html",
                "client/side_panel.css",
                "client/side_panel.js",
                "client/README.md",
            })
            self.assertFalse((output / "src").exists())
            self.assertFalse((output / "tests").exists())


if __name__ == "__main__":
    unittest.main()
