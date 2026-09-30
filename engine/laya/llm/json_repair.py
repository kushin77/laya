# Copyright 2026 Aayush Chawla
# SPDX-License-Identifier: Apache-2.0

"""Best-effort JSON extraction/repair for LLM output, plus the thinking-block
and padding-detection helpers that feed into it.

Split out of llm/client.py (#21) — pure text-processing logic with no
dependency on the LLM call path itself.
"""

import json
import re
from typing import Any

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>\s*", flags=re.DOTALL)


def _strip_think_blocks(text: str) -> str:
    """Remove <think>...</think> blocks that thinking models embed in content."""
    if "<think>" not in text:
        return text
    result = _THINK_BLOCK_RE.sub("", text).strip()
    if result.startswith("<think>"):
        result = result[len("<think>"):].strip()
    return result


def _extract_json(content: str, allow_completion: bool = False) -> Any | None:
    """Best-effort parse of a JSON object/array from model output.

    Beyond a strict json.loads() this handles two things verbose/non-stopping models add:
    1. ```json … ``` markdown fences some models wrap around the JSON.
    2. A complete JSON document followed by trailing junk — non-stopping local models
       (e.g. Gemma on LMStudio, whose <end_of_turn> isn't recognized as a stop) keep
       generating after the object closes, usually padding `\n`. A simple .strip() handles
       *pure* trailing whitespace; the balanced-brace scan below also recovers a complete
       object/array followed by non-whitespace junk.

    When `allow_completion` is set and the balanced-brace scan fails, a last-resort pass
    (`_complete_json`) rebuilds an object the model left *unterminated* because it padded
    whitespace before emitting the closing brackets — the Gemma-on-LMStudio failure where the
    turn stops (finish_reason=stop, NOT length) mid-padding, so the object never closed and no
    truncation retry ever fires. That completion is opt-in because it changes the "unterminated
    → None" contract other call sites (e.g. the truncation detector) rely on to trigger a retry.

    Returns the parsed value, or None when no object/array could be recovered (the document was
    genuinely truncated before a complete value — a real retry candidate).
    """
    if not content:
        return None
    s = content.strip()
    # Strip ```json … ``` fences that some models wrap around the JSON.
    if s.startswith("```"):
        nl = s.find("\n")
        if nl != -1:
            s = s[nl + 1:]
        if s.endswith("```"):
            s = s[:-3]
        s = s.strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    # Salvage: walk from the first opener to its matching closer (respecting strings and
    # escapes) and parse just that span, ignoring whatever the model padded afterwards. A
    # genuinely-unterminated document never balances → None.
    start = next((i for i, c in enumerate(s) if c in "{["), -1)
    if start == -1:
        return None
    opener = s[start]
    closer = "}" if opener == "{" else "]"
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(s[start:i + 1])
                except json.JSONDecodeError:
                    return None
    # The first opener never balanced. If the caller allows it, try to close a document the
    # model left unterminated because it padded whitespace instead of emitting the closers.
    if allow_completion:
        return _complete_json(s, start)
    return None


def _complete_json(s: str, start: int) -> Any | None:
    """Recover JSON left unterminated by a non-stopping model that padded trailing whitespace
    instead of emitting the closing brackets.

    The Gemma-on-LMStudio failure: the model emits the whole object, then pads `\n  ` (newline +
    indent) until it finally hits a recognized stop — so it halts with finish_reason=stop having
    never written the final `}`. The object is complete in every way except the closers, so we
    strip the whitespace padding (and a dangling comma), then append the brackets needed to
    balance. `json.loads` is the final guard: a genuinely-broken document (unbalanced, or cut
    mid-value) still returns None.

    Bails when the padding-stripped body ends *inside a string* — there the trailing whitespace
    is real value content, not structural padding, so completing it would corrupt/truncate the
    value. That's the signature of a genuine mid-content truncation, which the caller handles
    via the doubling retry instead.
    """
    body = s[start:].rstrip()
    if body.endswith(","):  # model stopped right after a separator, before the next value
        body = body[:-1].rstrip()
    if not body:
        return None
    stack: list[str] = []
    in_str = False
    esc = False
    for c in body:
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            stack.append("}")
        elif c == "[":
            stack.append("]")
        elif c == "}" or c == "]":
            if stack:
                stack.pop()
    # Ended mid-string, or already balanced (a balanced-but-invalid doc, e.g. trailing junk the
    # strict/scan passes already rejected) — nothing safe to append.
    if in_str or not stack:
        return None
    try:
        return json.loads(body + "".join(reversed(stack)))
    except json.JSONDecodeError:
        return None


def _looks_like_padding(content: str) -> bool:
    """True when the tail of `content` is dominated by repeated whitespace / a single repeated
    character — the signature of a non-stopping model padding to max_tokens (e.g. Gemma on
    LMStudio spewing `\n`) rather than a genuinely truncated document. Used to skip the
    doubling-retry, which on a padder would just generate *more* padding and fail again."""
    tail = content[-200:]
    if not tail:
        return False
    stripped = tail.strip()
    # Almost-all-whitespace tail, or the same character over and over.
    return len(stripped) <= 2 or len(set(stripped)) <= 1
