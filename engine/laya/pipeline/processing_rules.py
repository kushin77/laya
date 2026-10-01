# Copyright 2026 Aayush Chawla
# SPDX-License-Identifier: Apache-2.0

"""Processing rules engine — loads rules, evaluates conditions, rate-limits,
and dispatches to per-action-type executors.

Action execution (one function per action kind: set_status, set_priority,
bookmark, run_entity_agent, execute_egress, send_notification, add_tag) is
split out into ``processing_actions.py``. This module owns rule loading,
condition evaluation and dispatch, and re-exports ``_execute_action`` /
``_resolve_template`` for callers and tests that historically imported them
from here.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Any

import structlog

from laya.events import publish
from laya.db.sqlite import get_db
from laya.models.classification import RouterOutput
from laya.models.event import LayaEvent
from laya.models.processing_rules import (
    ProcessingAllCondition,
    ProcessingAnyCondition,
    ProcessingCondition,
    ProcessingNotCondition,
    ProcessingSimpleCondition,
    SetStatusAction,
)
from laya.pipeline.processing_actions import (
    _exec_add_tag,
    _exec_bookmark,
    _exec_egress,
    _exec_notification,
    _exec_run_agent,
    _exec_set_priority,
    _exec_set_status,
    _execute_action,
    _resolve_template,
)

log = structlog.get_logger()

_PRIORITY_ORDINAL = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

_processing_semaphore = asyncio.Semaphore(4)

# Auto-disable after this many consecutive errors (default; overridable via settings)
def _get_auto_disable_threshold() -> int:
    from laya.config import load_settings
    settings = load_settings()
    return settings.get("processing_rules", {}).get("auto_disable_threshold", 5)

# Max rules that can fire for a single card before we stop evaluating
_MAX_FIRINGS_PER_CARD = 5


# ---------------------------------------------------------------------------
# Condition evaluation
# ---------------------------------------------------------------------------

def _get_context_value(context: dict[str, Any], field_path: str) -> Any:
    """Extract a value from the flat trigger context dict using dot-notation."""
    parts = field_path.split(".")
    obj: Any = context
    for part in parts:
        if isinstance(obj, dict):
            obj = obj.get(part)
        elif hasattr(obj, part):
            obj = getattr(obj, part)
        else:
            return None
        if obj is None:
            return None
    return obj


def _evaluate_simple(condition: ProcessingSimpleCondition, context: dict[str, Any]) -> bool:
    """Evaluate a single field/operator/value condition against the context."""
    op = condition.operator.value
    actual = _get_context_value(context, condition.field)

    # exists / not_exists don't need a value
    if op == "exists":
        return actual is not None
    if op == "not_exists":
        return actual is None

    if actual is None:
        return False

    expected = condition.value
    actual_str = str(actual).lower()

    match op:
        case "equals":
            return actual_str == str(expected).lower()
        case "not_equals":
            return actual_str != str(expected).lower()
        case "contains":
            return str(expected).lower() in actual_str
        case "not_contains":
            return str(expected).lower() not in actual_str
        case "starts_with":
            return actual_str.startswith(str(expected).lower())
        case "ends_with":
            return actual_str.endswith(str(expected).lower())
        case "in":
            if isinstance(expected, list):
                return actual_str in [str(v).lower() for v in expected]
            return actual_str in str(expected).lower()
        case "not_in":
            if isinstance(expected, list):
                return actual_str not in [str(v).lower() for v in expected]
            return actual_str not in str(expected).lower()
        case "matches":
            pattern = str(expected)
            if len(pattern) > 500:
                log.warning("processing_rule_regex_too_long", length=len(pattern))
                return False
            try:
                return bool(re.search(pattern, str(actual), re.IGNORECASE))
            except re.error:
                return False
        case "gt" | "gte" | "lt" | "lte":
            return _compare_ordinal(op, actual, expected)
        case _:
            log.warning("unknown_processing_operator", operator=op)
            return False


def _compare_ordinal(op: str, actual: Any, expected: Any) -> bool:
    """Compare values ordinally. Supports priority names and numeric values."""
    actual_num = _to_ordinal(actual)
    expected_num = _to_ordinal(expected)
    if actual_num is None or expected_num is None:
        return False
    match op:
        case "gt":
            return actual_num > expected_num
        case "gte":
            return actual_num >= expected_num
        case "lt":
            return actual_num < expected_num
        case "lte":
            return actual_num <= expected_num
    return False


def _to_ordinal(value: Any) -> float | None:
    """Convert a value to a numeric ordinal for comparison."""
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).upper()
    if s in _PRIORITY_ORDINAL:
        return float(_PRIORITY_ORDINAL[s])
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


_MAX_CONDITION_DEPTH = 32


def evaluate_condition(condition: ProcessingCondition, context: dict[str, Any], *, _depth: int = 0) -> bool:
    """Recursively evaluate a processing rule condition tree."""
    if _depth > _MAX_CONDITION_DEPTH:
        log.warning("processing_rule_condition_too_deep", depth=_depth)
        return False
    if isinstance(condition, ProcessingSimpleCondition):
        return _evaluate_simple(condition, context)
    elif isinstance(condition, ProcessingAllCondition):
        return all(evaluate_condition(c, context, _depth=_depth + 1) for c in condition.all)
    elif isinstance(condition, ProcessingAnyCondition):
        return any(evaluate_condition(c, context, _depth=_depth + 1) for c in condition.any)
    elif isinstance(condition, ProcessingNotCondition):
        return not evaluate_condition(condition.not_, context, _depth=_depth + 1)
    return False


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------

def build_trigger_context(
    event: LayaEvent,
    router_output: RouterOutput,
    card_id: str,
    entity_id: str | None,
    space_id: str | None,
    actor_relationship: str | None = None,
    is_carry_forward: bool = False,
    entity_card_count: int = 1,
    card_header: str | None = None,
    card_summary: str | None = None,
) -> dict[str, Any]:
    """Build the flat trigger context dict from pipeline data."""
    now = datetime.now()
    return {
        "event": {
            "source": {
                "platform": event.source.platform,
                "raw_event_type": event.source.raw_event_type,
                "connection_id": getattr(event.source, "connection_id", None),
            },
            "actor": {
                "name": event.actor.name,
                "email": event.actor.email,
                "platform_handle": getattr(event.actor, "platform_handle", None),
            },
            "subject": {
                "type": event.subject.type,
                "id": event.subject.id,
                "title": event.subject.title,
                "url": event.subject.url,
            },
            "content": {
                "body": event.content.body,
                "metadata": event.content.metadata if hasattr(event.content, "metadata") else {},
            },
        },
        "classification": {
            "persona": router_output.persona.value if hasattr(router_output.persona, "value") else str(router_output.persona),
            "priority": router_output.priority.value if hasattr(router_output.priority, "value") else str(router_output.priority),
            "category": router_output.category.value if hasattr(router_output.category, "value") else str(router_output.category),
            "confidence": router_output.confidence,
            "requires_research": router_output.requires_research,
        },
        "card": {
            "card_id": card_id,
            "entity_id": entity_id,
            "space_id": space_id,
            # The card's LLM-generated title/summary (what the user sees on the
            # card), distinct from event.subject.title (the raw source subject).
            # Exposed so rules can match the visible title, not just the origin
            # subject line. Threaded in from stager_output at the emit call site.
            "header": card_header,
            "summary": card_summary,
        },
        "context": {
            "actor_relationship": actor_relationship or "unknown",
            "entity_card_count": entity_card_count,
            "is_carry_forward": is_carry_forward,
            "hour_of_day": now.hour,
            "day_of_week": now.weekday(),
        },
    }


# ---------------------------------------------------------------------------
# Rate limit checks
# ---------------------------------------------------------------------------

async def _check_rate_limits(
    rule_id: int,
    entity_id: str | None,
    rate_limit: int,
    cooldown_secs: int,
    max_daily: int,
) -> str | None:
    """Check rate limits for a rule. Returns a skip reason or None."""
    if not rate_limit and not cooldown_secs and not max_daily:
        return None

    db = await get_db()

    if rate_limit > 0:
        rows = await db.execute_fetchall(
            "SELECT COUNT(*) as cnt FROM processing_rule_firings WHERE rule_id = ? AND fired_at > datetime('now', '-1 hour')",
            (rule_id,),
        )
        if rows and rows[0]["cnt"] >= rate_limit:
            return f"hourly rate limit ({rate_limit}/hr)"

    if cooldown_secs > 0 and entity_id:
        rows = await db.execute_fetchall(
            "SELECT COUNT(*) as cnt FROM processing_rule_firings WHERE rule_id = ? AND entity_id = ? AND fired_at > datetime('now', ? || ' seconds')",
            (rule_id, entity_id, f"-{cooldown_secs}"),
        )
        if rows and rows[0]["cnt"] > 0:
            return f"entity cooldown ({cooldown_secs}s)"

    if max_daily > 0:
        rows = await db.execute_fetchall(
            "SELECT COUNT(*) as cnt FROM processing_rule_firings WHERE rule_id = ? AND fired_at > date('now', 'start of day')",
            (rule_id,),
        )
        if rows and rows[0]["cnt"] >= max_daily:
            return f"daily cap ({max_daily}/day)"

    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def run_processing_rules(
    event: LayaEvent,
    router_output: RouterOutput,
    card_id: str,
    entity_id: str | None = None,
    space_id: str | None = None,
    actor_relationship: str | None = None,
    is_carry_forward: bool = False,
    entity_card_count: int = 1,
    card_header: str | None = None,
    card_summary: str | None = None,
) -> None:
    """Evaluate all enabled processing rules against a newly emitted card.

    Called as a background task from run_emit(). Errors are logged and
    never propagate to the caller.
    """
    try:
        db = await get_db()

        # Load enabled rules for this space (global + space-scoped)
        if space_id:
            rows = await db.execute_fetchall(
                """SELECT id, name, condition_json, actions_json, space_id,
                          rate_limit, cooldown_secs, max_daily, error_count
                   FROM processing_rules
                   WHERE enabled = 1 AND (space_id IS NULL OR space_id = ?)
                   ORDER BY position ASC""",
                (space_id,),
            )
        else:
            rows = await db.execute_fetchall(
                """SELECT id, name, condition_json, actions_json, space_id,
                          rate_limit, cooldown_secs, max_daily, error_count
                   FROM processing_rules
                   WHERE enabled = 1 AND space_id IS NULL
                   ORDER BY position ASC""",
            )

        if not rows:
            return

        context = build_trigger_context(
            event, router_output, card_id, entity_id, space_id,
            actor_relationship, is_carry_forward, entity_card_count,
            card_header=card_header, card_summary=card_summary,
        )

        # Enrich context with card tags so rules can condition on them
        try:
            from laya.pipeline.tags import get_card_tag_names
            context["card"]["tags"] = await get_card_tag_names(card_id)
        except Exception:
            context["card"]["tags"] = []

        from laya.models.card_lifecycle import TERMINAL_STATUSES
        firings_this_card = 0
        card_terminated = False

        for rule_row in rows:
            if card_terminated:
                break
            if firings_this_card >= _MAX_FIRINGS_PER_CARD:
                log.info("processing_rules_per_card_cap", card_id=card_id, cap=_MAX_FIRINGS_PER_CARD)
                break

            rule_id = rule_row["id"]
            rule_name = rule_row["name"]

            try:
                condition = _parse_condition(rule_row["condition_json"])
                actions = _parse_actions(rule_row["actions_json"])
            except Exception as e:
                log.warning("processing_rule_parse_error", rule_id=rule_id, error=str(e))
                continue

            if not evaluate_condition(condition, context):
                continue

            # Rate limit check
            skip_reason = await _check_rate_limits(
                rule_id, entity_id,
                rule_row["rate_limit"], rule_row["cooldown_secs"], rule_row["max_daily"],
            )
            if skip_reason:
                log.info("processing_rule_rate_limited", rule_id=rule_id, rule=rule_name, reason=skip_reason)
                continue

            # Execute actions
            log.info("processing_rule_matched", rule_id=rule_id, rule=rule_name, card_id=card_id)
            results = []
            has_error = False

            for action in actions:
                result = await _execute_action(action, card_id, entity_id, space_id, context)
                results.append(result)
                if not result.get("success"):
                    has_error = True
                if isinstance(action, SetStatusAction) and result.get("success") and action.status in TERMINAL_STATUSES:
                    card_terminated = True
                    break

            firings_this_card += 1

            # Record firing
            await db.execute(
                """INSERT INTO processing_rule_firings
                   (rule_id, card_id, entity_id, event_id, actions_json, results_json, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    rule_id, card_id, entity_id, event.event_id,
                    json.dumps([a.model_dump() for a in actions]),
                    json.dumps(results),
                    results[-1].get("error") if has_error else None,
                ),
            )

            # Update rule stats
            new_error_count = (rule_row["error_count"] + 1) if has_error else 0
            auto_disable = new_error_count >= _get_auto_disable_threshold()

            await db.execute(
                """UPDATE processing_rules
                   SET fire_count = fire_count + 1,
                       last_fired_at = CURRENT_TIMESTAMP,
                       error_count = ?,
                       last_error = ?,
                       enabled = CASE WHEN ? THEN 0 ELSE enabled END,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (
                    new_error_count,
                    results[-1].get("error") if has_error else None,
                    auto_disable,
                    rule_id,
                ),
            )
            await db.commit()

            if auto_disable:
                log.warning("processing_rule_auto_disabled", rule_id=rule_id, rule=rule_name, consecutive_errors=new_error_count)
                await publish({
                    "type": "processing_rule_auto_disabled",
                    "payload": {"rule_id": rule_id, "name": rule_name, "reason": f"{new_error_count} consecutive errors"},
                })

    except Exception as e:
        log.error("processing_rules_fatal", card_id=card_id, error=str(e))


def _parse_condition(condition_json: str) -> ProcessingCondition:
    """Parse a condition JSON string into the discriminated union type."""
    data = json.loads(condition_json) if isinstance(condition_json, str) else condition_json
    if "all" in data:
        return ProcessingAllCondition(**data)
    elif "any" in data:
        return ProcessingAnyCondition(**data)
    elif "not" in data:
        return ProcessingNotCondition(**data)
    else:
        return ProcessingSimpleCondition(**data)


def _parse_actions(actions_json: str) -> list:
    """Parse actions JSON into typed action objects."""
    from laya.models.processing_rules import ProcessingRuleAction
    from pydantic import TypeAdapter
    adapter = TypeAdapter(list[ProcessingRuleAction])
    data = json.loads(actions_json) if isinstance(actions_json, str) else actions_json
    return adapter.validate_python(data)
