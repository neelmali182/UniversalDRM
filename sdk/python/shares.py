"""SDK Shares module (§20.1)."""
from __future__ import annotations

from typing import Any

import httpx


class SharesModule:
    """Manage shares — create, get, revoke."""

    def __init__(self, http: httpx.Client) -> None:
        self._http = http

    def create(
        self,
        asset_id: str,
        policy: dict[str, Any] | None = None,
        recipients: list[str] | None = None,
        identity_mode: str = "otp",
    ) -> dict[str, Any]:
        """Create a share for *asset_id*.

        Args:
            asset_id: ID of the asset to share.
            policy: Dict of policy fields (see §10.1).
            recipients: Email allowlist (overrides policy["recipients"] if given).
            identity_mode: ``"otp"`` (default) or ``"open"``.

        Returns:
            Share dict including the ``url`` and one-time ``token``.
        """
        pol = dict(policy or {})
        if recipients is not None:
            pol["recipients"] = recipients

        body = {"policy": pol, "identity_mode": identity_mode}
        r = self._http.post(f"/v1/assets/{asset_id}/shares", json=body)
        r.raise_for_status()
        return r.json()

    def get(self, share_id: str) -> dict[str, Any]:
        """Get share details (token is redacted after creation)."""
        r = self._http.get(f"/v1/shares/{share_id}")
        r.raise_for_status()
        return r.json()

    def revoke(self, share_id: str) -> None:
        """Revoke a share immediately (§9.4)."""
        r = self._http.delete(f"/v1/shares/{share_id}")
        r.raise_for_status()
