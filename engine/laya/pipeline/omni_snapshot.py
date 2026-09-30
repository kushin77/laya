# Copyright 2026 Aayush Chawla
# SPDX-License-Identifier: Apache-2.0

"""OMNI snapshot storage — reconstruction of full snapshots from delta chains,
delta application, and the small pieces of shared per-space state (the latest
in-memory snapshot cache and the resynthesis gate) that both the incremental
queue processor (``omni.py``) and the LLM resynthesis path (``omni_synthesis.py``)
need to read and mutate.

Public surface (used outside this module, including by api/omni_api.py via the
``omni.py`` facade): ``load_full_snapshot``, ``apply_delta``, ``get_gate``,
``all_resolved``.
"""

from __future__ import annotations

import asyncio
import copy
import json

import structlog

from laya.models.card_lifecycle import TERMINAL_STATUSES as _TERMINAL_STATUSES

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# In-memory cache for the latest reconstructed snapshot per space.
# Populated on every write, avoids delta chain reconstruction on hot reads.
# ---------------------------------------------------------------------------
_latest_cache: dict[str, dict] = {}

# Per-space gate: when a space has an active resynthesis, its asyncio.Event
# is *cleared* (blocking). When resynthesis finishes it is *set* (unblocked).
_resynthesis_gates: dict[str, asyncio.Event] = {}


def get_gate(space_id: str) -> asyncio.Event:
    """Get or create the resynthesis gate for a space (default: open)."""
    if space_id not in _resynthesis_gates:
        ev = asyncio.Event()
        ev.set()  # open by default — no resynthesis running
        _resynthesis_gates[space_id] = ev
    return _resynthesis_gates[space_id]


def apply_delta(content: dict, delta: dict) -> dict:
    """Apply a delta to a full content snapshot, mutating in place."""
    sections = content.get("sections", [])

    # Find the "recent" section
    recent_section = None
    for section in sections:
        if section.get("type") == "recent":
            recent_section = section
            break

    if recent_section is None:
        recent_section = {"type": "recent", "label": None, "items": []}
        sections.append(recent_section)

    # Apply fused_updates — match by entity_id, update fields
    for entity_id, updates in delta.get("fused_updates", {}).items():
        for item in recent_section.get("items", []):
            if item.get("entity_id") == entity_id:
                item.update(updates)
                break

    # Append added_items
    recent_section.setdefault("items", []).extend(delta.get("added_items", []))

    # Apply bookmark overrides
    for source_card_id, bookmarked in delta.get("bookmark_overrides", {}).items():
        for section in sections:
            for item in section.get("items", []):
                cards = item.get("source_cards", [])
                if cards and cards[0] == source_card_id:
                    item["bookmarked"] = bookmarked

    content["sections"] = sections
    return content


async def _find_base_version(db, space_id: str, current_version: int) -> int | None:
    """Find the version of the nearest base (non-delta) snapshot."""
    rows = await db.execute_fetchall(
        """SELECT version FROM omni_snapshots
           WHERE space_id = ? AND is_delta = 0 AND version <= ?
           ORDER BY version DESC LIMIT 1""",
        (space_id, current_version),
    )
    return rows[0]["version"] if rows else None


async def load_full_snapshot(
    db, space_id: str, version: int | None = None
) -> tuple[dict | None, int, list[str], dict]:
    """Load a fully reconstructed snapshot, handling delta chains.

    For the latest version (version=None), checks the in-memory cache first.

    Returns (content_dict, version_number, card_ids_list, metadata_dict).
    metadata_dict contains snapshot_id, generated_at, snapshot_type.
    """
    # Cache hit for latest
    if version is None and space_id in _latest_cache:
        c = _latest_cache[space_id]
        # Deep-copy so a caller that mutates the returned content (e.g.
        # _append_to_recent appending recent items) can't corrupt the cached
        # snapshot before the DB commit. A failed commit would otherwise leave
        # the cache serving phantom state and re-processing would double-append
        # (review §2 pipeline / §4). Installs into the cache stay post-commit.
        return (
            copy.deepcopy(c["content"]),
            c["version"],
            list(c["card_ids"]),
            dict(c.get("meta", {})),
        )

    # Load the target row
    if version is not None:
        rows = await db.execute_fetchall(
            """SELECT snapshot_id, version, generated_at, snapshot_type,
                      content_json, card_ids, is_delta, base_version
               FROM omni_snapshots
               WHERE space_id = ? AND version = ?""",
            (space_id, version),
        )
    else:
        rows = await db.execute_fetchall(
            """SELECT snapshot_id, version, generated_at, snapshot_type,
                      content_json, card_ids, is_delta, base_version
               FROM omni_snapshots
               WHERE space_id = ?
               ORDER BY version DESC LIMIT 1""",
            (space_id,),
        )

    if not rows:
        return None, 0, [], {}

    row = rows[0]
    meta = {
        "snapshot_id": row["snapshot_id"],
        "generated_at": row["generated_at"],
        "snapshot_type": row["snapshot_type"],
    }

    if not row["is_delta"]:
        # Full snapshot — return directly
        content = json.loads(row["content_json"])
        card_ids = json.loads(row["card_ids"])
        return content, row["version"], card_ids, meta

    # Delta snapshot — reconstruct from base
    target_version = row["version"]
    base_version = row["base_version"]

    if base_version is None:
        base_version = await _find_base_version(db, space_id, target_version)

    if base_version is None:
        log.warning("omni_delta_no_base", space_id=space_id, version=target_version)
        return None, 0, [], {}

    # Load base snapshot
    base_rows = await db.execute_fetchall(
        """SELECT content_json, card_ids FROM omni_snapshots
           WHERE space_id = ? AND version = ? AND is_delta = 0""",
        (space_id, base_version),
    )

    if not base_rows:
        base_rows = await db.execute_fetchall(
            """SELECT content_json, card_ids, version FROM omni_snapshots
               WHERE space_id = ? AND is_delta = 0 AND version < ?
               ORDER BY version DESC LIMIT 1""",
            (space_id, target_version),
        )
        if not base_rows:
            log.warning("omni_delta_base_missing", space_id=space_id, base=base_version)
            return None, 0, [], {}
        base_version = base_rows[0]["version"]

    content = json.loads(base_rows[0]["content_json"])
    card_ids = json.loads(base_rows[0]["card_ids"])

    # Load all deltas from base+1 to target, in order
    delta_rows = await db.execute_fetchall(
        """SELECT version, content_json, card_ids FROM omni_snapshots
           WHERE space_id = ? AND is_delta = 1
             AND version > ? AND version <= ?
           ORDER BY version ASC""",
        (space_id, base_version, target_version),
    )

    for delta_row in delta_rows:
        delta = json.loads(delta_row["content_json"])
        delta_card_ids = json.loads(delta_row["card_ids"])
        content = apply_delta(content, delta)
        card_ids = card_ids + [cid for cid in delta_card_ids if cid not in card_ids]

    return content, target_version, card_ids, meta


def all_resolved(card_ids: list[str], meta: dict[str, dict]) -> bool:
    """True if there is at least one known source card and ALL are terminal."""
    known = [meta[cid] for cid in card_ids if cid in meta]
    if not known:
        return False
    return all(m.get("status") in _TERMINAL_STATUSES for m in known)
