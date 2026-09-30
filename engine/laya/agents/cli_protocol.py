# Copyright 2026 Aayush Chawla
# SPDX-License-Identifier: Apache-2.0

"""Shared, verified-identical fragments between the interactive CLI-agent
session adapters (``agents/claude_code.py``, ``agents/gemini_cli.py``,
``agents/codex_cli.py``, ``agents/pi_cli.py``) and the headless one-shot
inference backend (``llm/agent_backend.py``).

Scope (deliberately narrow — see issue #19 and the PR that introduced this
module for the full comparison): a close, line-by-line read of both call
sites for each of the four agents found that their argv-building and
output-parsing logic have genuinely diverged, because one side drives an
interactive multi-turn session and the other drives a single headless
completion with a different CLI invocation shape (and, for Gemini and Pi,
a literally different output format on the wire). Force-unifying that
logic would be a behavior change, not a refactor. Only the pieces below
were verified byte-identical (or identical-shape-with-per-agent-data) and
are safe to share:

  * ``APPROVAL_PATTERNS`` / ``is_approval_prompt`` — the plain-text
    approval-prompt regexes used by gemini_cli.py, codex_cli.py and
    pi_cli.py are byte-identical. (claude_code.py carries its own larger
    superset, but its checker is hardcoded to return False — dead code,
    left untouched; see the note in claude_code.py.)
  * ``classify_tool`` — the three-way (FILE_READ / FILE_WRITE / TOOL_CALL)
    tool-name classifiers in claude_code.py, gemini_cli.py and pi_cli.py
    all have the identical shape (check read-names, then write-names,
    else TOOL_CALL). The *name sets* are per-agent and NOT merged here —
    doing so would change behavior (e.g. gemini's ``replace_in_file`` is
    not a name any other agent uses).
  * ``build_claude_base_args`` — the common invocation prefix Claude Code
    uses in both one-shot (``agent_backend.py``) and interactive
    (``claude_code.py``) mode: ``-p <prompt> --output-format stream-json
    --verbose``. Everything appended after this prefix (permission mode,
    --mcp-config, --model, --json-schema, --disallowedTools, ...) differs
    per call site and stays where it is.

NOT shared, and why (see the PR body for the full write-up):
  * Gemini: the interactive session passes ``--output-format stream-json``
    (a line-delimited event stream: init/message/tool_use/tool_result/
    result); the one-shot backend passes ``-o json`` (a single JSON blob
    with ``.response``/``.stats``). These are different wire formats, not
    two copies of the same parser.
  * Pi: the backend reads ``message_update.message.content[]`` /
    ``message.usage`` directly off the event; the session accumulates
    ``assistantMessageEvent.text_delta`` chunks (Pi's newer v3 delta
    schema). Different fields of a schema that has itself drifted between
    the two call sites.
  * Codex: the backend accepts ``agent_message`` text from any
    ``item.*`` event; the session only emits on ``item.completed``
    (``is_final``). Sharing this would change which events get surfaced.
  * Claude: the backend aggregates only the final ``result`` event (plus
    ``rate_limit_event`` for budgeting); the session explicitly skips
    ``rate_limit_event`` as noise and maps every content block (text,
    tool_use, ExitPlanMode, AskUserQuestion, ...) to a WorkspaceEvent.
    Zero shared parsing logic once the base args above are stripped away.
"""

from __future__ import annotations

import re

from laya.models.workspace import WorkspaceEventType

# ── approval-prompt detection ───────────────────────────────────────────
# Verified byte-identical across gemini_cli.py, codex_cli.py, pi_cli.py.

APPROVAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"Do you want to (proceed|continue)\?", re.IGNORECASE),
    re.compile(r"\[Y/n\]", re.IGNORECASE),
    re.compile(r"\(y/N\)", re.IGNORECASE),
]


def is_approval_prompt(line: str, patterns: list[re.Pattern[str]] = APPROVAL_PATTERNS) -> bool:
    """True if ``line`` looks like a plain-text (non-JSON) approval prompt."""
    return any(p.search(line) for p in patterns)


# ── tool-name classification ────────────────────────────────────────────
# Shape verified identical across claude_code.py, gemini_cli.py, pi_cli.py.
# Name sets are per-agent and passed in explicitly — never merged.


def classify_tool(
    tool_name: str,
    read_names: tuple[str, ...],
    write_names: tuple[str, ...],
) -> WorkspaceEventType:
    """Map a tool name to FILE_READ / FILE_WRITE / TOOL_CALL.

    ``read_names`` and ``write_names`` are the agent's own known tool-name
    spellings for reads and writes (case/naming varies per CLI).
    """
    if tool_name in read_names:
        return WorkspaceEventType.FILE_READ
    if tool_name in write_names:
        return WorkspaceEventType.FILE_WRITE
    return WorkspaceEventType.TOOL_CALL


# ── Claude Code shared invocation prefix ────────────────────────────────
# Identical on both call sites; verified against agent_backend._build_args
# and claude_code.py's start_session/resume_with_answer. Everything the
# caller appends afterward (permission mode, --mcp-config, --model,
# --json-schema, --disallowedTools, --resume, --add-dir, ...) is
# call-site-specific and stays there.


def build_claude_base_args(binary: str, prompt: str) -> list[str]:
    """The common Claude Code one-shot invocation prefix.

    ``-p <prompt>`` = print mode (exits, never waits on a TTY).
    ``--output-format stream-json --verbose`` = line-delimited JSON events,
    required by both the interactive session (full event stream) and the
    one-shot backend (which only needs the final `result` + rate-limit
    events, but must ask for the same format to get them).
    """
    return [binary, "-p", prompt, "--output-format", "stream-json", "--verbose"]
