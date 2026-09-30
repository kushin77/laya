# Copyright 2026 Aayush Chawla
# SPDX-License-Identifier: Apache-2.0

"""GitLab platform — credential-validation-only adapter.

GitLab has no n8n executor/ingestion integration (see ``registry.py``'s
``_PLATFORM_KEYWORDS`` note), so this adapter carries no capabilities and
no-op payload behavior. It exists so credential validation can go through
the same ``Platform.validate_credentials`` seam as every other platform
instead of a special case in ``egress/connections.py``.
"""

from __future__ import annotations

import httpx

from laya.egress.platforms.base import Platform


class GitlabPlatform(Platform):
    name = "gitlab"
    capabilities = []

    def identifiers_from_event(
        self,
        action_type: str,
        event_id: str | None,
        content_metadata: dict,
        event_row: dict,
        self_emails: set[str] | None = None,
    ) -> dict:
        return {}

    def normalize_payload(self, action_type: str, payload: dict) -> dict:
        return dict(payload)

    def validate_payload(self, action_type: str, payload: dict) -> list[str]:
        return []

    async def validate_credentials(self, credentials: dict) -> tuple[bool, str | None]:
        """Validate GitLab token by calling GET /api/v4/user."""
        token = credentials.get("accessToken", "")
        base_url = (credentials.get("baseUrl", "https://gitlab.com")).rstrip("/")
        if not token:
            return False, "Missing accessToken"

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{base_url}/api/v4/user",
                headers={"PRIVATE-TOKEN": token},
                timeout=10.0,
            )

        if resp.status_code == 200:
            return True, None
        elif resp.status_code == 401:
            return False, "Invalid or expired token"
        else:
            return False, f"GitLab returned HTTP {resp.status_code}"


PLATFORM = GitlabPlatform()
