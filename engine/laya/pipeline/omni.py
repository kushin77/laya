# Copyright 2026 Aayush Chawla
# SPDX-License-Identifier: Apache-2.0

"""OMNI pipeline — maintain a rolling cross-platform summary.

Incremental updates append to the "recent" section without LLM calls.
Scheduled resynthesis uses the LLM to compress layers progressively.

Delta storage: incremental snapshots store only the diff (added/fused items
+ new card_ids). Resynthesis snapshots store the full structure and serve as
base checkpoints. Reconstruction chains deltas from the nearest base.

This module is the thin public facade over three pieces split out for
maintainability:

- ``omni_snapshot``: snapshot load/reconstruction and delta application
  (``load_full_snapshot``, ``apply_delta``, ``get_gate``, ``all_resolved``,
  plus the shared ``_latest_cache`` / ``_resynthesis_gates`` state).
- ``omni_synthesis``: the LLM-powered full resynthesis (``run_omni_resynthesis``).
- ``omni_live``: live per-card state decoration (``fetch_card_meta``,
  ``live_max_priority``).

What stays here is the incremental queue processor — appending newly-emitted
cards to the "recent" section without an LLM call — since it is the module's
own read/write entry point into the snapshot store, not one of the three
concerns above.
"""

from __future__ import annotations

import asyncio
import copy
import json
import uuid

import structlog

from laya.events import publish
from laya.config import load_settings
from laya.db.sqlite import get_db
from laya.db.timeutil import db_now

# Re-exported so existing callers (api/omni_api.py, laya/scheduler.py, tests)
# that import these names from `laya.pipeline.omni` keep working unchanged.
from laya.pipeline.omni_snapshot import (  # noqa: F401
    _find_base_version,
    _latest_cache,
    _resynthesis_gates,
    all_resolved,
    apply_delta,
    get_gate,
    load_full_snapshot,
)
from laya.pipeline.omni_synthesis import (  # noqa: F401
    _is_degenerate_sections,
    run_omni_resynthesis,
)
from laya.pipeline.omni_live import fetch_card_meta, live_max_priority  # noqa: F401
from laya.pipeline.omni_change import compute_incremental_change_summary, decorate_item_keys

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Delta helpers (incremental append path only — resynthesis's own reconstruction
# delta-apply lives in omni_snapshot.apply_delta)
# ---------------------------------------------------------------------------


def _compute_delta(
    old_items: list[dict],
    new_items: list[dict],
) -> dict:
    """Compute the delta between old and new recent section items.

    Returns a dict with:
      - added_items: items that are entirely new (no entity match in old)
      - fused_updates: items that existed but were modified (keyed by entity_id)
    """
    old_by_entity: dict[str, dict] = {}
    old_card_set: set[str] = set()
    for item in old_items:
        eid = item.get("entity_id")
        if eid:
            old_by_entity[eid] = item
        for cid in item.get("source_cards", []):
            old_card_set.add(cid)

    added_items: list[dict] = []
    fused_updates: dict[str, dict] = {}

    for item in new_items:
        eid = item.get("entity_id")
        if eid and eid in old_by_entity:
            old = old_by_entity[eid]
            # Check if anything changed
            if (
                item.get("text") != old.get("text")
                or item.get("source_cards") != old.get("source_cards")
                or item.get("platforms") != old.get("platforms")
                or item.get("priority") != old.get("priority")
            ):
                fused_updates[eid] = {
                    "text": item["text"],
                    "source_cards": item.get("source_cards", []),
                    "platforms": item.get("platforms", []),
                    "priority": item.get("priority", "MEDIUM"),
                }
        else:
            # Check it's genuinely new (not already present in old by card ID)
            item_cards = set(item.get("source_cards", []))
            if not item_cards.issubset(old_card_set):
                added_items.append(item)

    return {
        "added_items": added_items,
        "fused_updates": fused_updates,
    }


# ---------------------------------------------------------------------------
# Queue processor — polls omni_queue table instead of in-memory list.
# Cards are enqueued by emit.py in the same transaction as the card persist,
# so they survive engine crashes. During resynthesis the processor pauses
# to avoid the race where incremental updates get overwritten.
# ---------------------------------------------------------------------------
_POLL_INTERVAL_SECONDS = 10
_queue_task: asyncio.Task | None = None


def start_omni_processor() -> None:
    """Start the background queue processor. Called once at startup."""
    global _queue_task
    if _queue_task is not None and not _queue_task.done():
        return
    from laya.tasks import create_task as create_tracked_task
    _queue_task = create_tracked_task(_queue_loop(), name="omni_queue_processor")
    log.info("omni_queue_processor_started")


def stop_omni_processor() -> None:
    """Stop the background queue processor. Called on shutdown."""
    global _queue_task
    if _queue_task is not None:
        _queue_task.cancel()
        _queue_task = None
        log.info("omni_queue_processor_stopped")


async def _queue_loop() -> None:
    """Poll omni_queue every POLL_INTERVAL_SECONDS and process batches."""
    while True:
        try:
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
            await _process_queue()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.error("omni_queue_loop_error", error=str(e))


async def _process_queue() -> None:
    """Read pending cards from omni_queue, group by space, and append.

    For spaces with an active resynthesis, cards are left in the queue
    and picked up on the next poll (after resynthesis completes).
    """
    settings = load_settings()
    if not settings.get("omni", {}).get("enabled", True):
        return

    db = await get_db()

    rows = await db.execute_fetchall(
        """SELECT oq.card_id, oq.space_id,
                  ac.header, ac.summary, ac.priority,
                  ac.entity_id, e.source_platform
           FROM omni_queue oq
           JOIN action_cards ac ON oq.card_id = ac.card_id
           LEFT JOIN events e ON ac.event_id = e.event_id
           ORDER BY oq.created_at ASC
           LIMIT 200"""
    )

    if not rows:
        return

    # Group by space_id; skip spaces with active resynthesis
    by_space: dict[str, list[dict]] = {}
    skipped_ids: list[str] = []
    for row in rows:
        sid = row["space_id"]
        gate = get_gate(sid)
        if not gate.is_set():
            # Resynthesis running for this space — leave in queue
            skipped_ids.append(row["card_id"])
            continue
        by_space.setdefault(sid, []).append({
            "card_id": row["card_id"],
            "card_header": row["header"],
            "card_summary": row["summary"],
            "card_priority": row["priority"],
            "source_platform": row["source_platform"] or "unknown",
            "space_id": sid,
            "entity_id": row["entity_id"],
        })

    if skipped_ids:
        log.debug("omni_queue_skipped_resynthesis", count=len(skipped_ids))

    for space_id, space_cards in by_space.items():
        try:
            await _append_to_recent(space_cards)
            # Delete processed rows from the queue
            processed_ids = [c["card_id"] for c in space_cards]
            placeholders = ",".join("?" for _ in processed_ids)
            await db.execute(
                f"DELETE FROM omni_queue WHERE card_id IN ({placeholders})",
                processed_ids,
            )
            await db.commit()
        except Exception as e:
            log.error("omni_incremental_update_failed", space_id=space_id, error=str(e))


async def _append_to_recent(cards: list[dict]) -> None:
    """Append cards to the 'recent' section of the latest snapshot.

    No LLM call — purely structured data manipulation.
    """
    db = await get_db()

    # Group cards by space_id
    by_space: dict[str, list[dict]] = {}
    for card in cards:
        sid = card.get("space_id", "default")
        by_space.setdefault(sid, []).append(card)

    for space_id, space_cards in by_space.items():
        # Load latest snapshot (reconstructed if delta chain)
        content, version, existing_card_ids, _meta = await load_full_snapshot(db, space_id)

        is_first = content is None
        if is_first:
            # First snapshot for this space — create skeleton as full base
            version = 0
            content = {
                "sections": [
                    {"type": "attention", "label": None, "items": []},
                    {"type": "recent", "label": None, "items": []},
                    {"type": "period", "label": None, "items": []},
                    {"type": "milestone", "label": None, "items": []},
                ]
            }
            existing_card_ids = []

        # Find the "recent" section
        recent_section = None
        for section in content.get("sections", []):
            if section.get("type") == "recent":
                recent_section = section
                break

        if recent_section is None:
            recent_section = {"type": "recent", "label": None, "items": []}
            content.setdefault("sections", []).append(recent_section)

        # Snapshot old items for delta computation
        old_recent_items = copy.deepcopy(recent_section.get("items", []))

        # Build an index of existing recent items by entity_id for fusion.
        # entity_id is stored on each item so we can match incoming cards
        # against items already in the recent section.
        entity_index: dict[str, int] = {}
        for idx, existing_item in enumerate(recent_section.get("items", [])):
            eid = existing_item.get("entity_id")
            if eid:
                entity_index[eid] = idx

        # Append new cards — fuse with existing items when same entity
        new_card_ids = []
        _PRIORITY_RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        for card in space_cards:
            cid = card["card_id"]
            if cid in existing_card_ids:
                continue

            card_entity_id = card.get("entity_id")
            platform = card.get("source_platform", "unknown")
            priority = card.get("card_priority", "MEDIUM")

            # Check if an existing recent item covers the same entity
            if card_entity_id and card_entity_id in entity_index:
                # Fuse: update existing item instead of creating a new one
                existing_idx = entity_index[card_entity_id]
                existing_item = recent_section["items"][existing_idx]

                # Use the latest card's text (most recent = most complete picture)
                existing_item["text"] = f"{card['card_header']} — {card['card_summary']}"

                # Merge source_cards list
                if cid not in existing_item.get("source_cards", []):
                    existing_item.setdefault("source_cards", []).append(cid)

                # Merge platforms (deduplicate)
                if platform not in existing_item.get("platforms", []):
                    existing_item.setdefault("platforms", []).append(platform)

                # Escalate priority (keep the highest)
                old_rank = _PRIORITY_RANK.get(existing_item.get("priority", "MEDIUM"), 2)
                new_rank = _PRIORITY_RANK.get(priority, 2)
                if new_rank < old_rank:
                    existing_item["priority"] = priority
            else:
                # New entity — create a fresh item
                item = {
                    "text": f"{card['card_header']} — {card['card_summary']}",
                    "source_cards": [cid],
                    "platforms": [platform],
                    "priority": priority,
                    "pinned": False,
                    "bookmarked": False,
                    "entity_id": card_entity_id,
                }
                recent_section["items"].append(item)
                if card_entity_id:
                    entity_index[card_entity_id] = len(recent_section["items"]) - 1

            new_card_ids.append(cid)

        if not new_card_ids:
            continue

        all_card_ids = existing_card_ids + new_card_ids
        now = db_now()

        # Keys are stamped on every write so the drill-down link and the
        # changelog name the same item; recomputing on read yields the same
        # value, so pre-072 snapshots stay addressable too.
        decorate_item_keys(content.get("sections", []))

        # Create a new incremental snapshot (version++)
        new_snapshot_id = f"omni_{uuid.uuid4().hex[:12]}"
        new_version = version + 1

        if is_first:
            # First snapshot ever — store as full base (no delta possible).
            # Every item is new, so the change summary is the whole recent list.
            change_summary = compute_incremental_change_summary(
                recent_section.get("items", []), "recent"
            )
            await db.execute(
                """INSERT INTO omni_snapshots
                   (snapshot_id, space_id, version, generated_at, snapshot_type,
                    content_json, card_ids, events_processed, created_at,
                    is_delta, base_version, change_summary_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    new_snapshot_id, space_id, new_version, now, "incremental",
                    json.dumps(content), json.dumps(all_card_ids),
                    len(all_card_ids), now, 0, None,
                    json.dumps(change_summary),
                ),
            )
        else:
            # Compute delta from old state and store only the diff
            delta = _compute_delta(old_recent_items, recent_section.get("items", []))
            base_ver = await _find_base_version(db, space_id, version)
            change_summary = compute_incremental_change_summary(
                delta.get("added_items", []), "recent"
            )

            await db.execute(
                """INSERT INTO omni_snapshots
                   (snapshot_id, space_id, version, generated_at, snapshot_type,
                    content_json, card_ids, events_processed, created_at,
                    is_delta, base_version, change_summary_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    new_snapshot_id, space_id, new_version, now, "incremental",
                    json.dumps(delta), json.dumps(new_card_ids),
                    len(all_card_ids), now, 1, base_ver,
                    json.dumps(change_summary),
                ),
            )

        await db.commit()

        # Update in-memory cache with full reconstructed state
        _latest_cache[space_id] = {
            "content": content,
            "version": new_version,
            "card_ids": all_card_ids,
            "meta": {
                "snapshot_id": new_snapshot_id,
                "generated_at": now,
                "snapshot_type": "incremental",
            },
        }

        # Broadcast update
        await publish({
            "type": "omni_updated",
            "payload": {
                "space_id": space_id,
                "version": new_version,
                "snapshot_type": "incremental",
                "new_items": len(new_card_ids),
            },
        })

        log.info(
            "omni_incremental_update",
            space_id=space_id,
            version=new_version,
            new_items=len(new_card_ids),
        )
