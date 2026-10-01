# Copyright 2026 Aayush Chawla
# SPDX-License-Identifier: Apache-2.0

"""Build the MCP config that is passed to spawned CLI agents.

Spawned Claude Code sessions connect to the **same** HTTP/SSE MCP endpoint
that external clients (Claude Desktop, Cursor, VS Code) use. There is one MCP
transport in Laya — the FastAPI-mounted `/mcp/sse` route — and every caller
goes through it. This module just builds the per-spawn config dict.

The user's Settings → MCP toggles (read / write / egress) gate what tools the
server returns, and the per-spawn `--allowedTools` flags derived here narrow
that further to what Claude Code is allowed to call autonomously in
non-interactive `-p` mode.
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any

import structlog

from laya.config import ENGINE_HOST, ENGINE_PORT, load_settings
from laya.mcp.scope import enabled_tool_names
from laya.security.keychain import get_mcp_token

log = structlog.get_logger()

LAYA_MCP_SERVER_NAME = "laya"
CODEIDX_MCP_SERVER_NAME = "codeidx"


def _sse_url(space_id: str | None) -> str:
    base = f"http://{ENGINE_HOST}:{ENGINE_PORT}/mcp/sse"
    if space_id:
        return f"{base}?space_id={space_id}"
    return base


def _auth_headers() -> dict[str, str]:
    mcp_cfg = (load_settings().get("mcp", {}) or {})
    if mcp_cfg.get("auth_mode", "bearer") != "bearer":
        return {}
    token = get_mcp_token()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def _codeidx_settings() -> dict[str, Any]:
    mcp_cfg = load_settings().get("mcp", {}) or {}
    external = mcp_cfg.get("external_servers", {}) or {}
    return external.get("codeidx", {}) or {}


def codeidx_enabled() -> bool:
    """Return True if the user has enabled the codeidx external MCP server
    and configured a command that exists and is executable on disk."""
    cfg = _codeidx_settings()
    if not cfg.get("enabled"):
        return False
    command = (cfg.get("command") or "").strip()
    if not command:
        return False
    if not (os.path.isfile(command) and os.access(command, os.X_OK)):
        log.warning("codeidx_mcp_command_unusable", command=command)
        return False
    return True


def _codeidx_server_entry() -> dict[str, Any] | None:
    """Build the stdio mcpServers entry for codeidx, or None if not usable.

    Never raises — an unusable path logs a warning and is skipped so agent
    spawn is never broken by a bad external-server configuration.
    """
    if not codeidx_enabled():
        return None
    command = _codeidx_settings()["command"].strip()
    return {
        "type": "stdio",
        "command": command,
        "args": [],
        "env": {
            "CODEIDX_PROMPT_CACHE_L1": "1",
            "CODEIDX_KNOWN_ANSWER": "1",
        },
    }


def build_laya_mcp_config(space_id: str | None) -> dict[str, Any]:
    """Return the JSON-shaped MCP config for `claude --mcp-config`.

    Uses the running engine's `/mcp/sse` endpoint with the user's current
    bearer token (when bearer auth is enabled). No subprocess, no env vars —
    the engine is already running.

    When the user has enabled the external `codeidx` code-search MCP server
    (Settings -> MCP) and its configured command exists and is executable, a
    second, STDIO-launched `mcpServers` entry is added for it. An unusable
    command (missing/non-executable) is logged and skipped — it never breaks
    agent spawn.
    """
    servers: dict[str, Any] = {
        LAYA_MCP_SERVER_NAME: {
            "type": "sse",
            "url": _sse_url(space_id),
            "headers": _auth_headers(),
        }
    }

    codeidx_entry = _codeidx_server_entry()
    if codeidx_entry is not None:
        servers[CODEIDX_MCP_SERVER_NAME] = codeidx_entry

    return {"mcpServers": servers}


def build_laya_mcp_config_json(space_id: str | None) -> str:
    """JSON-serialized form suitable for passing inline to `--mcp-config`."""
    return json.dumps(build_laya_mcp_config(space_id))


def write_laya_mcp_config_file(space_id: str | None) -> str:
    """Write the MCP config JSON to a 0600 temp file and return its path.

    The config embeds the MCP bearer token. Passing it inline via `--mcp-config
    '<json>'` argv leaks the token to any local process reading `ps`; a file
    argument does not (review §6). Caller is responsible for unlinking the file
    once the agent process has started/finished.
    """
    data = build_laya_mcp_config_json(space_id)
    # mkstemp creates the file with 0600 perms on POSIX (owner-only).
    fd, path = tempfile.mkstemp(prefix="laya_mcp_", suffix=".json")
    try:
        os.write(fd, data.encode("utf-8"))
    finally:
        os.close(fd)
    try:
        os.chmod(path, 0o600)  # explicit, in case the platform default differs
    except OSError:
        pass
    return path


def laya_allowed_tool_flags() -> list[str]:
    """Return `--allowedTools` flag pairs for the tools the user currently
    has enabled in Settings → MCP.

    Claude Code in non-interactive `-p` mode rejects any tool not explicitly
    allowlisted, so this list must match the user's enabled scopes — otherwise
    the agent will hang on a permission prompt that never gets answered.
    """
    scopes = (load_settings().get("mcp", {}) or {}).get("tool_scopes", {}) or {}
    flags: list[str] = []
    for tool_name in sorted(enabled_tool_names(scopes)):
        flags.extend(["--allowedTools", f"mcp__{LAYA_MCP_SERVER_NAME}__{tool_name}"])

    if codeidx_enabled():
        # Codeidx tools are read-only code search — allowlisted together, no
        # further per-tool sub-scoping needed.
        flags.extend(["--allowedTools", f"mcp__{CODEIDX_MCP_SERVER_NAME}__*"])

    return flags


MCP_PROMPT_HINT = (
    "You have access to Laya's internal data via MCP tools (prefixed `mcp__laya__`). "
    "Use `mcp__laya__search_cards` or `mcp__laya__semantic_search` to find cards by "
    "keyword or natural-language phrase (e.g. \"cab payment related cards\"), and "
    "`mcp__laya__get_card` to fetch full details by card_id. Prefer these over guessing."
)

CODEIDX_PROMPT_HINT = (
    "You also have access to codeidx code-search MCP tools (prefixed `mcp__codeidx__`), "
    "such as `mcp__codeidx__codeidx_search`, `mcp__codeidx__codeidx_definitions`, "
    "`mcp__codeidx__codeidx_references`, and `mcp__codeidx__codeidx_query`. Prefer these "
    "over grepping the repo for compiler-accurate symbol lookups and code search."
)


def augment_prompt_with_mcp_hint(prompt: str) -> str:
    """Prepend a short hint so the agent knows Laya's MCP tools exist.

    The codeidx hint is appended only when the external codeidx MCP server is
    actually enabled and usable, so agents aren't told about tools that
    weren't wired into their `--mcp-config`.
    """
    hint = MCP_PROMPT_HINT
    if codeidx_enabled():
        hint = f"{hint} {CODEIDX_PROMPT_HINT}"
    return f"{hint}\n\n---\n\n{prompt}"
