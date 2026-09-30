# Copyright 2026 Aayush Chawla
# SPDX-License-Identifier: Apache-2.0

"""Processing rule action executors — one function per action kind.

Split out of ``processing_rules.py`` (which owns rule loading, condition
evaluation, rate limiting and dispatch) so each action kind's side effects
live in one place. Public surface used by ``processing_rules.py``:
``_execute_action`` (the dispatcher) and ``_resolve_template`` (also used to
resolve ``{{field.path}}`` placeholders in action templates).
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import structlog

from laya.events import publish
from laya.db.sqlite import get_db
from laya.db.timeutil import db_now
from laya.models.processing_rules import (
    AddTagAction,
    BookmarkAction,
    ExecuteEgressAction,
    RunEntityAgentAction,
    SendNotificationAction,
    SetPriorityAction,
    SetStatusAction,
)

log = structlog.get_logger()

_VAR_RE = re.compile(r"\{\{([\w.]+)\}\}")

# Per-entity locks to prevent concurrent agent spawns
_agent_locks: dict[str, asyncio.Lock] = {}


def _resolve_template(template: str, context: dict[str, Any]) -> str:
    """Replace {{field.path}} placeholders with values from the context."""
    def _replace(match: re.Match) -> str:
        path = match.group(1)
        value: Any = context
        for part in path.split("."):
            if isinstance(value, dict):
                value = value.get(part)
            else:
                value = None
                break
        if value is None or value == "":
            log.warning("processing_rule_template_missing_key", key=path)
            return f"<missing:{path}>"
        return str(value)
    return _VAR_RE.sub(_replace, template)


async def _execute_action(
    action: Any,
    card_id: str,
    entity_id: str | None,
    space_id: str | None,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Execute a single processing rule action. Returns result dict."""
    try:
        if isinstance(action, SetStatusAction):
            return await _exec_set_status(action, card_id)
        elif isinstance(action, SetPriorityAction):
            return await _exec_set_priority(action, card_id)
        elif isinstance(action, BookmarkAction):
            return await _exec_bookmark(card_id)
        elif isinstance(action, RunEntityAgentAction):
            return await _exec_run_agent(action, entity_id, context)
        elif isinstance(action, ExecuteEgressAction):
            return await _exec_egress(action, card_id, space_id, context)
        elif isinstance(action, SendNotificationAction):
            return await _exec_notification(action, card_id, context)
        elif isinstance(action, AddTagAction):
            return await _exec_add_tag(action, card_id)
        else:
            return {"success": False, "error": f"Unknown action type: {type(action).__name__}"}
    except Exception as e:
        log.error("processing_rule_action_error", action_type=type(action).__name__, error=str(e))
        return {"success": False, "error": str(e)}


async def _exec_set_status(action: SetStatusAction, card_id: str) -> dict[str, Any]:
    from laya.models.card_lifecycle import transition_card_status
    try:
        await transition_card_status(
            card_id, action.status,
            actor="processing_rule",
            reason=action.reason,
        )
        return {"success": True, "status": action.status}
    except ValueError as e:
        log.warning("processing_rule_invalid_transition", card_id=card_id, error=str(e))
        return {"success": False, "error": str(e)}


async def _exec_set_priority(action: SetPriorityAction, card_id: str) -> dict[str, Any]:
    db = await get_db()
    await db.execute(
        "UPDATE action_cards SET priority = ?, updated_at = CURRENT_TIMESTAMP WHERE card_id = ?",
        (action.priority, card_id),
    )
    await db.commit()
    await publish({"type": "card_updated", "card_id": card_id, "payload": {"priority": action.priority}})
    return {"success": True, "priority": action.priority}


async def _exec_bookmark(card_id: str) -> dict[str, Any]:
    db = await get_db()
    now = db_now()
    await db.execute(
        "UPDATE action_cards SET bookmarked_at = ?, updated_at = CURRENT_TIMESTAMP WHERE card_id = ? AND bookmarked_at IS NULL",
        (now, card_id),
    )
    await db.commit()
    await publish({"type": "card_updated", "card_id": card_id, "payload": {"bookmarked": True}})
    return {"success": True, "bookmarked": True}


async def _exec_run_agent(
    action: RunEntityAgentAction,
    entity_id: str | None,
    context: dict[str, Any],
) -> dict[str, Any]:
    if not entity_id:
        return {"success": False, "error": "No entity_id for agent run"}
    prompt = _resolve_template(action.prompt_template, context) if action.prompt_template else None
    lock = _agent_locks.setdefault(entity_id, asyncio.Lock())
    async with lock:
        try:
            from laya.agents.entity_context import (
                build_entity_agent_prompt,
                get_entity_research_dir,
                write_entity_context_file,
            )
            from laya.agents import session_manager
            from laya.config import load_repos
            from laya.workers.engineer import resolve_repo_path
            from laya.models.classification import Category, Persona, Priority, RouterOutput as RO
            from laya.api.cards_agent import _stream_entity_agent
            from laya.tasks import create_task as create_tracked_task

            # Reuse the entity's existing workspace instead of spawning a duplicate.
            # include_terminal=True so a completed run (the common case — a manual
            # or prior rule run finishes its turn and the session is marked
            # 'completed') is resumed rather than replaced by a new session, which
            # would orphan the workspace the user sees via the Workspace button
            # (get_workspace returns the most-recent session for the entity).
            # Skip only while the agent is actively working or waiting on the user;
            # otherwise resume. Mirrors the manual flow in cards_api.run_entity_agent.
            existing = await session_manager.get_session_for_entity(entity_id, include_terminal=True)
            if existing:
                status = existing["status"]
                if status in ("starting", "running"):
                    return {"success": True, "skipped": True, "reason": "agent already running"}
                if status == "awaiting_input" or await session_manager.has_unanswered_questions(existing["session_id"]):
                    return {"success": True, "skipped": True, "reason": "workspace awaiting user input"}

            db = await get_db()
            card_rows = await db.execute_fetchall(
                "SELECT card_id, space_id FROM action_cards WHERE entity_id = ? ORDER BY created_at DESC",
                (entity_id,),
            )
            if not card_rows:
                return {"success": False, "error": "No cards for entity"}

            space_id = card_rows[0]["space_id"] or "default"
            anchor_card_id = card_rows[0]["card_id"]

            # Refresh CONTEXT.md so the agent (new or resumed) sees the latest cards.
            await write_entity_context_file(entity_id, space_id)
            research_dir_str = str(get_entity_research_dir(entity_id))

            dummy_router = RO(persona=Persona.ENGINEER, priority=Priority.MEDIUM, category=Category.CODE, confidence=0.8, entities=[])
            repo_path, other_repos = await resolve_repo_path(dummy_router, space_id=space_id)

            if repo_path:
                cwd = repo_path
                add_dirs = [research_dir_str] + [p for p in other_repos if p != research_dir_str]
            else:
                cwd = research_dir_str
                repos_data = load_repos()
                add_dirs = [r["path"] for r in repos_data.get("repos", []) if r.get("path")]

            # Spawn/resume the session FIRST. Only after it actually exists do
            # we flip the card to agent_running — the previous order set the
            # status via a raw UPDATE *before* the spawn, so a spawn failure
            # stranded the card in agent_running until the next restart sweep
            # (review §2 pipeline — P3-7). A failure here is caught by the outer
            # try/except and the card is left untouched.
            if existing:
                # Resume the same session (reuses session_id, so the Workspace
                # button keeps opening the workspace the user already had).
                resume_text = prompt or "Continue working. Check CONTEXT.md for updated entity context."
                agent = await session_manager.resume_conversation(
                    existing["session_id"], resume_text, add_dirs=add_dirs,
                )
                session_id = existing["session_id"]
            else:
                agent_prompt = build_entity_agent_prompt(entity_id, research_dir_str, repo_path, prompt)
                agent_type = session_manager.get_configured_agent_type()
                session_id, agent = await session_manager.start_session(
                    card_id=anchor_card_id, prompt=agent_prompt, repo_path=cwd,
                    agent_type=agent_type, space_id=space_id, add_dirs=add_dirs,
                    mode="plan", research=True, entity_id=entity_id,
                )

            now = db_now()
            await db.execute(
                "UPDATE action_cards SET has_workspace = 1, updated_at = ? WHERE entity_id = ?",
                (now, entity_id),
            )
            await db.commit()
            # Route the status flip through the lifecycle SSOT (validation +
            # atomic guard + broadcast) instead of a raw UPDATE.
            try:
                from laya.models.card_lifecycle import transition_card_status
                await transition_card_status(anchor_card_id, "agent_running", actor="processing_rule")
            except ValueError:
                # Anchor in a status that can't move to agent_running (e.g.
                # dismissed) — the workspace still exists; leave the card as-is.
                pass

            for card_row in card_rows:
                await publish(
                    {"type": "card_updated", "card_id": card_row["card_id"], "payload": {"has_workspace": True}}
                )

            create_tracked_task(
                _stream_entity_agent(session_id=session_id, agent=agent, entity_id=entity_id, anchor_card_id=anchor_card_id),
                name=f"proc_rule_agent_{entity_id}",
            )

            return {"success": True, "session_id": session_id, "resumed": bool(existing)}
        except Exception as e:
            return {"success": False, "error": str(e)}


async def _exec_egress(
    action: ExecuteEgressAction,
    card_id: str,
    space_id: str | None,
    context: dict[str, Any],
) -> dict[str, Any]:
    resolved_payload = {}
    for k, v in action.payload_template.items():
        resolved_payload[k] = _resolve_template(v, context) if isinstance(v, str) else v

    try:
        from laya.egress import route_and_execute
        from laya.egress.models import EgressRequest

        req = EgressRequest(
            card_id=card_id,
            platform=action.platform,
            action_type=action.action_type,
            payload=resolved_payload,
            connection_id=action.connection_id,
            space_id=space_id,
        )
        result = await route_and_execute(req)
        return {"success": result.success, "result": result.result_data if result.success else None, "error": result.error if not result.success else None}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _exec_notification(
    action: SendNotificationAction,
    card_id: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    title = _resolve_template(action.title_template, context)
    body = _resolve_template(action.body_template, context)
    await publish({
        "type": "push_notification",
        "payload": {"title": title, "body": body, "card_id": card_id},
    })
    return {"success": True, "title": title}


async def _exec_add_tag(action: AddTagAction, card_id: str) -> dict[str, Any]:
    from laya.pipeline.tags import TAG_SOFT_CAP, update_card_tags_in_chromadb

    db = await get_db()
    tag_name = action.tag_name.strip().lower()
    if not tag_name:
        return {"success": False, "error": "Empty tag name"}

    rows = await db.execute_fetchall("SELECT tag_id FROM tags WHERE name = ?", (tag_name,))
    if rows:
        tag_id = rows[0]["tag_id"]
    elif action.create_if_missing:
        await db.execute("INSERT INTO tags (name) VALUES (?)", (tag_name,))
        await db.commit()
        new = await db.execute_fetchall("SELECT tag_id FROM tags WHERE name = ?", (tag_name,))
        tag_id = new[0]["tag_id"]
    else:
        return {"success": False, "error": f"Tag '{tag_name}' not found"}

    count_rows = await db.execute_fetchall(
        "SELECT COUNT(*) AS cnt FROM tag_assignments WHERE target_type = 'card' AND target_id = ?",
        (card_id,),
    )
    if count_rows[0]["cnt"] >= TAG_SOFT_CAP:
        return {"success": False, "error": f"Tag cap ({TAG_SOFT_CAP}) reached"}

    await db.execute(
        "INSERT OR IGNORE INTO tag_assignments (tag_id, target_type, target_id, assigned_by) VALUES (?, 'card', ?, 'rule')",
        (tag_id, card_id),
    )
    await db.commit()

    try:
        await update_card_tags_in_chromadb(card_id)
    except Exception as e:
        log.warning("rule_tag_chromadb_failed", card_id=card_id, error=str(e))

    await publish({
        "type": "tags_changed",
        "payload": {"target_type": "card", "target_id": card_id, "tag_name": tag_name, "action": "assigned"},
    })
    return {"success": True, "tag_name": tag_name}
