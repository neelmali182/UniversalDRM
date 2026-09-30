"""UniversalDRM Python SDK Client (§20.1).

Usage:
    from sdk.python import Client

    drm = Client(api_key="udrm_live_xxx", base_url="http://localhost:8000")

    asset = drm.assets.upload("confidential.pdf")

    share = drm.shares.create(
        asset_id=asset["id"],
        recipients=["alice@example.com"],
        policy={
            "view": True,
            "download": False,
            "copy": False,
            "print": False,
            "watermark_visible": True,
            "watermark_forensic": True,
            "expires_in": 3600,
            "max_sessions": 1,
        },
    )

    print(share["url"])
"""
from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path
from typing import Any

import httpx

from .assets import AssetsModule
from .shares import SharesModule


class Client:
    """UniversalDRM API client.

    Args:
        api_key: Developer API key (``udrm_live_...`` or ``udrm_test_...``).
        base_url: Base URL of the API server.
        timeout: HTTP request timeout in seconds.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "http://localhost:8000",
        timeout: float = 30.0,
    ) -> None:
        self._http = httpx.Client(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "universaldrm-python-sdk/0.1.0",
            },
            timeout=timeout,
        )
        self.assets = AssetsModule(self._http)
        self.shares = SharesModule(self._http)

    def _get(self, path: str, **kwargs) -> Any:
        r = self._http.get(path, **kwargs)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, **kwargs) -> Any:
        r = self._http.post(path, **kwargs)
        r.raise_for_status()
        return r.json()

    def _delete(self, path: str, **kwargs) -> None:
        r = self._http.delete(path, **kwargs)
        r.raise_for_status()

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, *args) -> None:
        self.close()
