# Copyright 2026 Aayush Chawla
# SPDX-License-Identifier: Apache-2.0

"""Discord platform — credential-validation-only adapter.

Discord has no n8n executor/ingestion integration (see ``registry.py``'s
``_PLATFORM_KEYWORDS`` note), so this adapter carries no capabilities and
no-op payload behavior. It exists so credential validation can go through
the same ``Platform.validate_credentials`` seam as every other platform
instead of a special case in ``egress/connections.py``.
"""

from __future__ import annotations

import httpx

from laya.egress.platforms.base import Platform


class DiscordPlatform(Platform):
    name = "discord"
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
        """Validate Discord bot token by calling GET /users/@me."""
        token = credentials.get("botToken", "")
        if not token:
            return False, "Missing botToken"

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://discord.com/api/v10/users/@me",
                headers={"Authorization": f"Bot {token}"},
                timeout=10.0,
            )

        if resp.status_code == 200:
            return True, None
        elif resp.status_code == 401:
            return False, "Invalid bot token"
        else:
            return False, f"Discord returned HTTP {resp.status_code}"


PLATFORM = DiscordPlatform()
