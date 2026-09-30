# Copyright 2026 Aayush Chawla
# SPDX-License-Identifier: Apache-2.0

"""SMTP platform — a data-only adapter.

SMTP egress executes via ``backends.smtp.SmtpBackend`` (a generic email provider),
NOT through the n8n enrichment path, so this adapter carries only declarative data
(capabilities, draft schema, hint) and no-op behavior. It is deliberately excluded
from ``platforms.for_platform`` dispatch so enrichment never normalizes smtp
payloads — ``for_platform("smtp")`` stays ``None``.
"""

from __future__ import annotations

from laya.egress.models import EgressCapability
from laya.egress.platforms.base import Platform
from laya.egress.platforms.gmail import EMAIL_DRAFT_SCHEMA


class SmtpPlatform(Platform):
    name = "smtp"
    platform_hint = "a professional email"
    draft_schema = EMAIL_DRAFT_SCHEMA  # shares gmail's email draft schema

    # SmtpBackend-only — no n8n executor.  No event context → all fields
    # must be caller/LLM-provided, so content_fields mirror requires_fields.
    capabilities = [
        EgressCapability(
            action_type="send_email",
            label="Send Email",
            requires_fields=["to", "subject", "body"],
            optional_fields=["in_reply_to", "references", "cc", "bcc"],
            content_fields=["to", "subject", "body"],
            optional_content_fields=["cc", "bcc"],
            description="Send email via SMTP (generic email provider).",
            summary_template="Send email to {to} with subject '{subject}'",
            impact="medium",
        ),
    ]

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
        """Validate SMTP credentials by connecting and authenticating."""
        try:
            import aiosmtplib

            port = int(credentials.get("smtp_port", 587))
            use_tls = credentials.get("use_tls", True)

            # Port 465 = implicit TLS (use_tls=True, no STARTTLS needed)
            # Port 587 = STARTTLS (start_tls=True handles the upgrade automatically)
            # Port 25  = plain (no TLS)
            smtp = aiosmtplib.SMTP(
                hostname=credentials.get("smtp_host", ""),
                port=port,
                use_tls=(use_tls and port == 465),
                start_tls=(use_tls and port != 465),
            )
            await smtp.connect()
            await smtp.login(credentials.get("username", ""), credentials.get("password", ""))
            await smtp.quit()
            return True, None
        except ImportError:
            return False, "aiosmtplib not installed — SMTP support unavailable"
        except Exception as e:
            return False, f"SMTP connection failed: {str(e)}"


PLATFORM = SmtpPlatform()
