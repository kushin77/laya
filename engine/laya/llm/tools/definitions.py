# Copyright 2026 Aayush Chawla
# SPDX-License-Identifier: Apache-2.0

"""OpenAI function-calling tool definitions for Laya chat.

Each tool family owns its own schema definitions (``get_read_definitions()`` /
``get_write_definitions()`` on the family's module in ``laya.llm.tools``).
This module only aggregates them and exposes the chat-facing selection API.
"""

from __future__ import annotations

from laya.egress.tools import get_egress_tool_definitions
from laya.llm.tools import (
    card_tools,
    entity_tools,
    event_tools,
    rules_tools,
    search_tools,
    settings_tools,
    summary_tools,
)


def get_all_tool_definitions() -> list[dict]:
    """Return all tool definitions in OpenAI function calling format.

    The full ~8.4K-token set. Used by MCP (scope-filtered separately) and as the
    fallback; chat uses select_chat_tools() to gate the heavy groups (P6-8).
    """
    return [
        *_read_tools(),
        *_write_tools(),
        *_settings_read_tools(),
        *_settings_write_tools(),
        *_rules_read_tools(),
        *_rules_write_tools(),
        *get_egress_tool_definitions(),
    ]


# ---------------------------------------------------------------------------
# Intent-gated chat toolset (review §3 — P6-8)
#
# The full toolset is ~8.4K tokens (measured), resent on every chat turn AND
# every tool-loop iteration (up to 20) — on an 8K local context it blows the
# window before the user's question. Read + card-write tools (~2.8K) always
# ship; the settings, rules, and egress groups (~5.6K combined) ship only when
# the turn's text signals that intent. Inclusion-biased on purpose: a group ships
# on ANY keyword hit — a false positive merely costs tokens, whereas a false
# negative would deny the model a tool it needs. Keyword sets are lowercase
# substrings; keep them broad.
# ---------------------------------------------------------------------------

_RULES_HINTS = (
    "rule", "filter", "classif", "routing", "route to", "processing rule",
    "auto-tag", "auto tag", "auto-archive", "always mark", "never mark",
    "always route", "get_rule_options",
)
_SETTINGS_HINTS = (
    "setting", "configure", "config", "budget", "api key", "api-key",
    "model", "preference", "persona", "enable ", "disable ", "turn on", "turn off",
)
_EGRESS_HINTS = (
    "send", "reply", "respond", "post ", "email", "e-mail", "message",
    "comment", "notify", "notification", "ping", "slack", "draft", "compose",
    "create issue", "create a ticket", "create ticket", "follow up", "follow-up",
    "let them know", "let her know", "let him know",
)


def _hits(text: str, hints: tuple[str, ...]) -> bool:
    return any(h in text for h in hints)


def select_tool_definitions(text: str) -> list[dict]:
    """Chat toolset gated by a cheap keyword intent check over ``text`` (P6-8)."""
    t = (text or "").lower()
    defs = [*_read_tools(), *_write_tools()]
    if _hits(t, _SETTINGS_HINTS):
        defs += [*_settings_read_tools(), *_settings_write_tools()]
    if _hits(t, _RULES_HINTS):
        defs += [*_rules_read_tools(), *_rules_write_tools()]
    if _hits(t, _EGRESS_HINTS):
        defs += get_egress_tool_definitions()
    return defs


def select_chat_tools(user_message: str, chat_history: list[dict] | None = None) -> list[dict]:
    """Gate the chat toolset on the current message + recent USER turns.

    Recent user turns are included so a multi-turn flow ("create a rule" → the
    model asks for detail → "yes") keeps its group available through the follow-
    ups even when the later messages don't repeat the keyword. Assistant turns
    are excluded to avoid keeping a group alive off the model's own phrasing.
    """
    recent_user = " ".join(
        (m.get("content") or "")
        for m in (chat_history or [])
        if m.get("role") == "user"
    )
    return select_tool_definitions(f"{user_message or ''} {recent_user}")


# Public helpers that derive tool-name sets dynamically from the group functions
# above. MCP scope filtering uses these so new tools added to any group are
# automatically picked up — never hardcode names elsewhere.

def _names_of(defs: list[dict]) -> set[str]:
    return {d["function"]["name"] for d in defs}


def read_tool_names() -> set[str]:
    """Names of read-only data tools (search/fetch cards, events, entities) and
    the read-only settings/rules introspection tools."""
    return _names_of(_read_tools()) | _names_of(_settings_read_tools()) | _names_of(_rules_read_tools())


def write_tool_names() -> set[str]:
    """Names of mutating tools: card lifecycle, settings, and rule changes."""
    return _names_of(_write_tools()) | _names_of(_settings_write_tools()) | _names_of(_rules_write_tools())


def egress_tool_names() -> set[str]:
    """Names of outbound-action tools (Slack/Jira/GitHub/... egress)."""
    return _names_of(get_egress_tool_definitions())


def _read_tools() -> list[dict]:
    return [
        *card_tools.get_read_definitions(),
        *event_tools.get_read_definitions(),
        *entity_tools.get_read_definitions(),
        *search_tools.get_read_definitions(),
        *summary_tools.get_read_definitions(),
    ]


def _write_tools() -> list[dict]:
    return card_tools.get_write_definitions()


def _settings_read_tools() -> list[dict]:
    return settings_tools.get_read_definitions()


def _settings_write_tools() -> list[dict]:
    return settings_tools.get_write_definitions()


def _rules_read_tools() -> list[dict]:
    return rules_tools.get_read_definitions()


def _rules_write_tools() -> list[dict]:
    return rules_tools.get_write_definitions()
