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


if __name__ == "__main__":
    unittest.main()
