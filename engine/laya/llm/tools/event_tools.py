# Copyright 2026 Aayush Chawla
# SPDX-License-Identifier: Apache-2.0

"""Event-related tool implementations."""

from __future__ import annotations

import json
from typing import Any

from laya.db.sqlite import get_db
from laya.db.timeutil import db_ts_from_epoch
from laya.llm.tools.constants import (
    CHAT_SEARCH_DEFAULT,
    CHAT_SEARCH_MAX,
    RECENT_ACTIVITY_DEFAULT,
    RECENT_ACTIVITY_MAX,
    parse_iso_to_timestamp,
)


async def search_events(
    query: str | None = None,
    platform: str | None = None,
    actor: str | None = None,
    limit: int = CHAT_SEARCH_DEFAULT,
    offset: int = 0,
    space_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    """Search events by keyword, platform, or actor."""
    db = await get_db()
    conditions: list[str] = []
    params: list[Any] = []

    if query:
        keywords = [w for w in query.split() if len(w) >= 2]
        for kw in keywords[:5]:
            conditions.append("(subject_title LIKE ? OR content_body LIKE ?)")
            params.extend([f"%{kw}%"] * 2)

    if platform:
        conditions.append("source_platform = ?")
        params.append(platform)

    if actor:
        conditions.append("(actor_name LIKE ? OR actor_email LIKE ?)")
        params.extend([f"%{actor}%"] * 2)

    if space_id:
        conditions.append("space_id = ?")
        params.append(space_id)

    date_from_ts = parse_iso_to_timestamp(date_from)
    date_to_ts = parse_iso_to_timestamp(date_to, end_of_day=True)
    if date_from_ts is not None:
        conditions.append("timestamp >= ?")
        # Canonical DB format so the bound lexicographically matches the stored
        # (space-separated) events.timestamp — see laya/db/timeutil.py.
        params.append(db_ts_from_epoch(date_from_ts))
    if date_to_ts is not None:
        conditions.append("timestamp <= ?")
        params.append(db_ts_from_epoch(date_to_ts))

    where = " AND ".join(conditions) if conditions else "1=1"

    count_rows = await db.execute_fetchall(
        f"SELECT COUNT(*) as cnt FROM events WHERE {where}",
        params,
    )
    total = count_rows[0]["cnt"] if count_rows else 0

    capped_limit = min(limit, CHAT_SEARCH_MAX)
    rows = await db.execute_fetchall(
        f"""SELECT event_id, timestamp, source_platform, actor_name, actor_email,
                   subject_title, subject_url, space_id
            FROM events WHERE {where}
            ORDER BY timestamp DESC LIMIT ? OFFSET ?""",
        [*params, capped_limit, offset],
    )

    return {
        "events": [
            {
                "event_id": r["event_id"],
                "timestamp": r["timestamp"],
                "platform": r["source_platform"],
                "actor_name": r["actor_name"],
                "actor_email": r["actor_email"],
                "subject_title": r["subject_title"],
                "subject_url": r["subject_url"],
                "space_id": r["space_id"],
            }
            for r in rows
        ],
        "count": len(rows),
        "total": total,
        "offset": offset,
        "has_more": offset + len(rows) < total,
    }


async def get_event(event_id: str) -> dict[str, Any]:
    """Get full details of a specific event."""
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT event_id, timestamp, source_platform, source_raw_event_type,
                  actor_name, actor_email, actor_handle, actor_relationship,
                  subject_type, subject_id, subject_title, subject_url,
                  content_body, content_metadata, space_id, created_at
           FROM events WHERE event_id = ?""",
        (event_id,),
    )
    if not rows:
        return {"error": f"Event '{event_id}' not found"}

    r = rows[0]
    event: dict[str, Any] = {
        "event_id": r["event_id"],
        "timestamp": r["timestamp"],
        "platform": r["source_platform"],
        "event_type": r["source_raw_event_type"],
        "actor": {
            "name": r["actor_name"],
            "email": r["actor_email"],
            "handle": r["actor_handle"],
            "relationship": r["actor_relationship"],
        },
        "subject": {
            "type": r["subject_type"],
            "id": r["subject_id"],
            "title": r["subject_title"],
            "url": r["subject_url"],
        },
        "content_body": r["content_body"],
        "space_id": r["space_id"],
    }

    if r["content_metadata"]:
        try:
            event["content_metadata"] = json.loads(r["content_metadata"])
        except json.JSONDecodeError:
            pass

    return {"event": event}


async def get_recent_activity(
    hours: int = 24,
    limit: int = RECENT_ACTIVITY_DEFAULT,
    offset: int = 0,
    space_id: str | None = None,
) -> dict[str, Any]:
    """Get recent events and cards from the last N hours."""
    db = await get_db()
    space_filter = "AND space_id = ?" if space_id else ""
    space_params: list[Any] = [space_id] if space_id else []
    capped_limit = min(limit, RECENT_ACTIVITY_MAX)
    time_filter = f"datetime('now', '-{int(hours)} hours')"

    # Counts
    event_count_rows = await db.execute_fetchall(
        f"SELECT COUNT(*) as cnt FROM events WHERE timestamp >= {time_filter} {space_filter}",
        space_params,
    )
    card_count_rows = await db.execute_fetchall(
        f"SELECT COUNT(*) as cnt FROM action_cards WHERE created_at >= {time_filter} {space_filter}",
        space_params,
    )
    total_events = event_count_rows[0]["cnt"] if event_count_rows else 0
    total_cards = card_count_rows[0]["cnt"] if card_count_rows else 0

    # Recent events
    event_rows = await db.execute_fetchall(
        f"""SELECT event_id, timestamp, source_platform, actor_name, subject_title
            FROM events
            WHERE timestamp >= {time_filter}
            {space_filter}
            ORDER BY timestamp DESC LIMIT ? OFFSET ?""",
        [*space_params, capped_limit, offset],
    )

    # Recent cards
    card_rows = await db.execute_fetchall(
        f"""SELECT card_id, header, summary, status, priority, created_at
            FROM action_cards
            WHERE created_at >= {time_filter}
            {space_filter}
            ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        [*space_params, capped_limit, offset],
    )

    return {
        "hours": hours,
        "recent_events": [
            {
                "event_id": r["event_id"],
                "timestamp": r["timestamp"],
                "platform": r["source_platform"],
                "actor": r["actor_name"],
                "subject": r["subject_title"],
            }
            for r in event_rows
        ],
        "recent_cards": [
            {
                "card_id": r["card_id"],
                "header": r["header"],
                "summary": r["summary"],
                "status": r["status"],
                "priority": r["priority"],
                "created_at": r["created_at"],
            }
            for r in card_rows
        ],
        "event_count": len(event_rows),
        "card_count": len(card_rows),
        "total_events": total_events,
        "total_cards": total_cards,
        "offset": offset,
        "has_more_events": offset + len(event_rows) < total_events,
        "has_more_cards": offset + len(card_rows) < total_cards,
    }


def get_definitions() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "search_events",
                "description": (
                    "Search raw events by keyword, platform, or actor. "
                    "Returns paginated results — check 'has_more' and use 'offset' to retrieve additional pages."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Free-text search query to match against subject and content.",
                        },
                        "platform": {
                            "type": "string",
                            "description": "Filter by source platform (e.g. 'jira', 'slack', 'gmail', 'bitbucket', 'calendar').",
                        },
                        "actor": {
                            "type": "string",
                            "description": "Filter by actor name or email (partial match).",
                        },
                        "date_from": {
                            "type": "string",
                            "description": (
                                "ISO 8601 date or datetime for the start of a time range "
                                "filter (inclusive). Examples: '2026-04-01', '2026-04-01T00:00:00Z'. "
                                "Use when the user mentions a time period like 'last month', "
                                "'since April', 'past 2 weeks'. Omit if no temporal intent."
                            ),
                        },
                        "date_to": {
                            "type": "string",
                            "description": (
                                "ISO 8601 date or datetime for the end of a time range "
                                "filter (inclusive). Examples: '2026-04-30', '2026-04-30T23:59:59Z'. "
                                "Use when the user mentions a bounded time period like "
                                "'in April', 'last week', 'between March and May'. Omit for "
                                "open-ended ranges like 'since April'."
                            ),
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max results to return (default 20, max 200).",
                            "default": 20,
                        },
                        "offset": {
                            "type": "integer",
                            "description": "Starting position for pagination (default 0). Use with 'total' and 'has_more' from results to page through all matches.",
                            "default": 0,
                        },
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_event",
                "description": "Get full details of a specific event by its ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "event_id": {
                            "type": "string",
                            "description": "The event ID.",
                        },
                    },
                    "required": ["event_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_recent_activity",
                "description": (
                    "Get the most recent events and cards across all platforms. "
                    "Returns paginated results — check 'has_more_events'/'has_more_cards' and use 'offset' to page."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "hours": {
                            "type": "integer",
                            "description": "Look back this many hours (default 24).",
                            "default": 24,
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max results per category (default 10, max 200).",
                            "default": 10,
                        },
                        "offset": {
                            "type": "integer",
                            "description": "Starting position for pagination (default 0).",
                            "default": 0,
                        },
                    },
                    "required": [],
                },
            },
        },
    ]
