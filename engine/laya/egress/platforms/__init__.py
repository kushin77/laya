# Copyright 2026 Aayush Chawla
# SPDX-License-Identifier: Apache-2.0

"""Per-platform egress adapters.

Each ``platforms/<name>.py`` defines one ``Platform`` subclass (see ``base.py``)
and exposes it as a module-level singleton ``PLATFORM`` (calendar exposes two
leaves). Each adapter is the single source of truth for everything about its
platform: behavior + capabilities + terminal events + compose/draft/source-ref
data. The registry facade (``laya.egress.registry``) imports these adapters and
delegates to them.

Two maps:
- ``registry_platforms()`` — the canonical platform→adapter map (all platforms,
  incl. smtp), in the historical capability order. The registry facade iterates
  this for capability lookups and derived groupings.
- ``for_platform(name)`` — enrichment dispatch. Excludes smtp (its egress goes
  through SmtpBackend, not n8n enrichment), and resolves the three calendar keys.

To add a platform: implement the ``Platform`` interface in a new file, expose
``PLATFORM``, and register it in ``_REGISTRY`` (and ``_DISPATCH`` if it enriches).
"""

from laya.egress.platforms.base import Platform
from laya.egress.platforms import (
    bitbucket,
    bitbucket_server,
    calendar,
    discord,
    github,
    gitlab,
    gmail,
    jira,
    linear,
    notion,
    outlook,
    slack,
    smtp,
)

# Canonical platform -> adapter. Order matches the historical _CAPABILITIES
# insertion order so get_all_platforms() / compose ordering stay stable.
# Every entry here must declare real capabilities (enforced by
# test_platform_interface.test_adapter_contract) — gitlab/discord have no n8n
# executor/ingestion integration (see registry.py's _PLATFORM_KEYWORDS note),
# so they live in ``_VALIDATION_ONLY`` instead of here.
_REGISTRY: dict[str, Platform] = {
    "gmail": gmail.PLATFORM,
    "outlook": outlook.PLATFORM,
    "smtp": smtp.PLATFORM,
    "jira": jira.PLATFORM,
    "notion": notion.PLATFORM,
    "github": github.PLATFORM,
    "bitbucket": bitbucket.PLATFORM,
    "bitbucket_server": bitbucket_server.PLATFORM,
    "slack": slack.PLATFORM,
    "linear": linear.PLATFORM,
    "calendar": calendar.GOOGLE_CALENDAR,
    "outlook_calendar": calendar.OUTLOOK_CALENDAR,
}

# Platforms with no n8n executor/ingestion integration (no capabilities to
# declare) that still need Platform.validate_credentials — kept out of
# _REGISTRY so they don't trip the "every registered adapter has capabilities"
# contract. ``credential_validators()`` merges this with _REGISTRY for the
# connection broker's validation dispatch.
_VALIDATION_ONLY: dict[str, Platform] = {
    "gitlab": gitlab.PLATFORM,
    "discord": discord.PLATFORM,
}

# Enrichment dispatch: platform string -> adapter. smtp is intentionally absent
# (SMTP egress goes through SmtpBackend, not n8n enrichment), so
# ``for_platform("smtp")`` stays None. The three calendar keys
# (google_calendar / outlook_calendar / calendar) resolve to a working adapter.
_DISPATCH: dict[str, Platform] = {
    "github": github.PLATFORM,
    "jira": jira.PLATFORM,
    "linear": linear.PLATFORM,
    "notion": notion.PLATFORM,
    "bitbucket": bitbucket.PLATFORM,
    "bitbucket_server": bitbucket_server.PLATFORM,
    "gmail": gmail.PLATFORM,
    "outlook": outlook.PLATFORM,
    "slack": slack.PLATFORM,
    "google_calendar": calendar.GOOGLE_CALENDAR,
    "outlook_calendar": calendar.OUTLOOK_CALENDAR,
    "calendar": calendar.GOOGLE_CALENDAR,
}


def for_platform(name: str) -> Platform | None:
    """Return the adapter for enrichment dispatch, or ``None`` if unsupported."""
    return _DISPATCH.get(name)


def registry_platforms() -> dict[str, Platform]:
    """Canonical platform→adapter map (all platforms, ordered) for the registry facade."""
    return _REGISTRY


def credential_validators() -> dict[str, Platform]:
    """Platform→adapter map for credential validation: _REGISTRY plus the
    validation-only adapters (gitlab, discord) that have no capabilities."""
    return {**_REGISTRY, **_VALIDATION_ONLY}


__all__ = [
    "Platform",
    "bitbucket",
    "bitbucket_server",
    "calendar",
    "discord",
    "github",
    "gitlab",
    "gmail",
    "jira",
    "linear",
    "notion",
    "outlook",
    "slack",
    "smtp",
    "for_platform",
    "registry_platforms",
    "credential_validators",
]
