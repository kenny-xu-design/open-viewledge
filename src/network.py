from __future__ import annotations

from dataclasses import dataclass
from typing import MutableMapping
from urllib.parse import urlsplit
import os


VIEWLEDGE_HTTP_PROXY_ENV = "VIEWLEDGE_HTTP_PROXY"
_HTTP_PROXY_KEYS = ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy")


@dataclass(frozen=True)
class NetworkProxyStatus:
    enabled: bool
    source: str = ""
    endpoint: str = ""

    def public_payload(self) -> dict[str, object]:
        return {
            "proxyEnabled": self.enabled,
            "proxySource": self.source,
            "proxyEndpoint": self.endpoint,
        }


def apply_network_proxy_env(
    environ: MutableMapping[str, str] | None = None,
) -> NetworkProxyStatus:
    target = environ if environ is not None else os.environ
    for key in _HTTP_PROXY_KEYS:
        value = str(target.get(key) or "").strip()
        if value:
            normalized = _normalize_proxy_url(value)
            return NetworkProxyStatus(True, key, _safe_proxy_endpoint(normalized))

    configured = str(target.get(VIEWLEDGE_HTTP_PROXY_ENV) or "").strip()
    if not configured:
        return NetworkProxyStatus(False)

    normalized = _normalize_proxy_url(configured)
    for key in _HTTP_PROXY_KEYS:
        target.setdefault(key, normalized)
    return NetworkProxyStatus(
        True,
        VIEWLEDGE_HTTP_PROXY_ENV,
        _safe_proxy_endpoint(normalized),
    )


def _normalize_proxy_url(value: str) -> str:
    stripped = value.strip()
    if "://" not in stripped:
        return f"http://{stripped}"
    return stripped


def _safe_proxy_endpoint(value: str) -> str:
    parsed = urlsplit(value)
    if not parsed.hostname:
        return "已配置"
    scheme = parsed.scheme or "http"
    port = f":{parsed.port}" if parsed.port is not None else ""
    return f"{scheme}://{parsed.hostname}{port}"
