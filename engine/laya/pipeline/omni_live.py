# Copyright 2026 Aayush Chawla
# SPDX-License-Identifier: Apache-2.0

"""OMNI live-state decoration — fetches live per-card state (status, priority,
timestamps) from the database and derives display-time facts (highest live
priority among a set of source cards) that decorate an otherwise-static
snapshot with what's true right now.

Public surface (used outside this module, including by api/omni_api.py via the
``omni.py`` facade): ``fetch_card_meta``, ``live_max_priority``.
"""

from __future__ import annotations

from laya.models.card_lifecycle import TERMINAL_STATUSES as _TERMINAL_STATUSES

_PRIORITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


async def fetch_card_meta(db, card_ids: list[str]) -> dict[str, dict]:
    """Fetch live per-card state for a set of card_ids.

    Returns ``{card_id: {status, priority, entity_id, created_at, resolved_at,
    source_platform}}``. The last three feed the API's per-item ``live``
    decoration (item age, resolution timestamps, the platform-mix instrument);
    the pipeline itself only reads status/priority/entity_id.
    """
    if not card_ids:
        return {}
    unique_ids = list(dict.fromkeys(card_ids))
    placeholders = ",".join("?" for _ in unique_ids)
    rows = await db.execute_fetchall(
        f"""SELECT ac.card_id, ac.status, ac.priority, ac.entity_id,
                   ac.created_at, ac.resolved_at, e.source_platform
            FROM action_cards ac
            LEFT JOIN events e ON ac.event_id = e.event_id
            WHERE ac.card_id IN ({placeholders})""",
        unique_ids,
    )
    return {
        r["card_id"]: {
            "status": r["status"],
            "priority": r["priority"],
            "entity_id": r["entity_id"],
            "created_at": r["created_at"],
            "resolved_at": r["resolved_at"],
            "source_platform": r["source_platform"] or "unknown",
        }
        for r in rows
    }


def item_source_cards(item: dict) -> list[str]:
    return [c for c in item.get("source_cards", []) if c]


def live_max_priority(card_ids: list[str], meta: dict[str, dict]) -> str | None:
    """Highest priority among non-terminal source cards, or None if all resolved/unknown."""
    best: str | None = None
    best_rank = 99
    for cid in card_ids:
        m = meta.get(cid)
        if not m or m.get("status") in _TERMINAL_STATUSES:
            continue
        rank = _PRIORITY_ORDER.get(m.get("priority", "MEDIUM"), 2)
        if rank < best_rank:
            best_rank = rank
            best = m.get("priority", "MEDIUM")
    return best
