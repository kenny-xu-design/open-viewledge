from __future__ import annotations

import unittest

from src.network import VIEWLEDGE_HTTP_PROXY_ENV, apply_network_proxy_env


class NetworkProxyTests(unittest.TestCase):
    def test_direct_network_is_unchanged_without_configuration(self) -> None:
        environ: dict[str, str] = {}

        status = apply_network_proxy_env(environ)

        self.assertFalse(status.enabled)
        self.assertEqual(environ, {})

    def test_viewledge_proxy_populates_standard_proxy_variables(self) -> None:
        environ = {VIEWLEDGE_HTTP_PROXY_ENV: "127.0.0.1:7897"}

        status = apply_network_proxy_env(environ)

        self.assertTrue(status.enabled)
        self.assertEqual(status.source, VIEWLEDGE_HTTP_PROXY_ENV)
        self.assertEqual(status.endpoint, "http://127.0.0.1:7897")
        self.assertEqual(environ["HTTP_PROXY"], "http://127.0.0.1:7897")
        self.assertEqual(environ["HTTPS_PROXY"], "http://127.0.0.1:7897")
        self.assertEqual(environ["http_proxy"], "http://127.0.0.1:7897")
        self.assertEqual(environ["https_proxy"], "http://127.0.0.1:7897")

    def test_existing_standard_proxy_takes_precedence(self) -> None:
        environ = {
            VIEWLEDGE_HTTP_PROXY_ENV: "http://127.0.0.1:7897",
            "HTTPS_PROXY": "http://proxy.example:8080",
        }

        status = apply_network_proxy_env(environ)

        self.assertTrue(status.enabled)
        self.assertEqual(status.source, "HTTPS_PROXY")
        self.assertEqual(status.endpoint, "http://proxy.example:8080")
        self.assertNotIn("HTTP_PROXY", environ)

    def test_public_endpoint_omits_credentials(self) -> None:
        environ = {VIEWLEDGE_HTTP_PROXY_ENV: "http://name:secret@127.0.0.1:7897"}

        status = apply_network_proxy_env(environ)

        self.assertEqual(status.endpoint, "http://127.0.0.1:7897")


if __name__ == "__main__":
    unittest.main()
