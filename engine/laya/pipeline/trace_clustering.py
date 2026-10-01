# Copyright 2026 Aayush Chawla
# SPDX-License-Identifier: Apache-2.0

"""Trace pipeline — seed expansion, entity clustering, chapter detection
(split out of pipeline/trace.py, #8).

Split boundary: everything here takes a ranked seed list (trace_retrieval.py's
output) and turns it into `TraceCluster`s — fetching all related cards for the
matched entities, following cross-references, union-finding cards into
connected clusters, and grouping each cluster's timeline into chapters.
Narrative generation over the resulting clusters is trace_narrative.py.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import structlog

from laya.api.cards_common import CARD_SELECT_COLUMNS, _row_to_card
from laya.db.sqlite import get_db
from laya.egress.registry import get_chapter_default as _get_chapter_default
from laya.models.card import CardResponse
from laya.models.trace import TraceChapter, TraceCluster, TraceEntity, TraceStatusSummary

log = structlog.get_logger()

_CARD_SELECT = f"""
    SELECT {CARD_SELECT_COLUMNS}
    FROM action_cards c
    LEFT JOIN events e ON c.event_id = e.event_id
    LEFT JOIN spaces s ON c.space_id = s.space_id
"""


async def _expand_seeds(
    seeds: list[dict],
    space_id: str | None,
    include_archived: bool,
) -> tuple[list[CardResponse], dict[str, TraceEntity]]:
    """Expand seed results to all related cards + build entity map."""
    db = await get_db()

    # Collect unique entity_ids from seeds
    entity_ids: set[str] = set()
    card_ids: set[str] = set()
    for seed in seeds:
        eid = seed.get("entity_id")
        if eid and not eid.startswith("singleton:"):
            entity_ids.add(eid)
        cid = seed.get("card_id")
        if cid:
            card_ids.add(cid)

    # Also fetch entity_ids from the seed card_ids we found
    if card_ids:
        placeholders = ",".join("?" * len(card_ids))
        rows = await db.execute_fetchall(
            f"SELECT DISTINCT entity_id FROM action_cards WHERE card_id IN ({placeholders}) AND entity_id IS NOT NULL",
            list(card_ids),
        )
        for row in rows:
            if row["entity_id"]:
                entity_ids.add(row["entity_id"])

    # Cross-reference expansion: find linked entities
    linked_entity_ids = await _find_linked_entities(db, entity_ids)
    all_entity_ids = entity_ids | linked_entity_ids

    # Fetch ALL cards for these entity_ids
    all_cards: list[CardResponse] = []
    entity_map: dict[str, TraceEntity] = {}

    if all_entity_ids:
        placeholders = ",".join("?" * len(all_entity_ids))
        where_parts = [f"c.entity_id IN ({placeholders})"]
        params: list[str] = list(all_entity_ids)

        if space_id:
            where_parts.append("c.space_id = ?")
            params.append(space_id)
        if not include_archived:
            where_parts.append("c.status != 'archived'")

        where_clause = " AND ".join(where_parts)
        rows = await db.execute_fetchall(
            f"{_CARD_SELECT} WHERE {where_clause} ORDER BY c.created_at ASC",
            params,
        )
        for row in rows:
            all_cards.append(_row_to_card(row))

    # Also include any seed cards that weren't captured by entity expansion
    existing_card_ids = {c.card_id for c in all_cards}
    missing_card_ids = card_ids - existing_card_ids
    if missing_card_ids:
        placeholders = ",".join("?" * len(missing_card_ids))
        rows = await db.execute_fetchall(
            f"{_CARD_SELECT} WHERE c.card_id IN ({placeholders}) ORDER BY c.created_at ASC",
            list(missing_card_ids),
        )
        for row in rows:
            all_cards.append(_row_to_card(row))

    # Sort all cards chronologically
    all_cards.sort(key=lambda c: c.created_at or "")

    # Build entity map from event metadata
    seen_entities: set[str] = set()
    for card in all_cards:
        eid = card.entity_id
        if eid and eid not in seen_entities:
            seen_entities.add(eid)
            # Parse platform from entity_id format: "platform:subject_type:subject_id"
            parts = eid.split(":", 2)
            platform = parts[0] if parts else ""
            entity_map[eid] = TraceEntity(
                entity_id=eid,
                title=card.source_ref or card.header,
                url=card.source_url,
                platform=platform,
            )

    return all_cards, entity_map


# Bounds for _find_linked_entities so a hub entity can't explode into an
# O(entities × refs) storm of full-table LIKE scans (review §4 — P5-6).
_MAX_LINK_SUBJECTS = 25
_MAX_LINK_REFS = 50


async def _find_linked_entities(db, entity_ids: set[str]) -> set[str]:
    """Find cross-referenced entities via the entities table.

    The entities lookup is batched into a single query (was one per entity_id)
    and the ref-id fan-out is deduped and capped, avoiding a nested N+1 of
    per-ref full-table LIKE scans (review §4 — P5-6).
    """
    if not entity_ids:
        return set()

    # Extract subject_ids (e.g. "BUG-1234" from "jira:ticket:BUG-1234").
    subject_ids = []
    for eid in entity_ids:
        parts = eid.split(":", 2)
        subject_id = parts[-1] if parts else eid
        if len(subject_id) >= 3:
            subject_ids.append(subject_id)
    if not subject_ids:
        return set()

    linked: set[str] = set()

    # One entities query for all subjects instead of one per entity_id.
    clauses: list[str] = []
    params: list = []
    for sid in subject_ids[:_MAX_LINK_SUBJECTS]:
        clauses.append("platform_refs LIKE ? OR canonical_name LIKE ?")
        params.extend([f"%{sid}%", f"%{sid}%"])
    rows = await db.execute_fetchall(
        f"SELECT entity_id, platform_refs FROM entities WHERE {' OR '.join(clauses)}",
        params,
    )

    ref_ids: set[str] = set()
    for row in rows:
        linked.add(row["entity_id"])
        try:
            refs = json.loads(row["platform_refs"]) if row["platform_refs"] else {}
            for _platform, rid_list in refs.items():
                if isinstance(rid_list, list):
                    for rid in rid_list:
                        if rid and len(str(rid)) >= 3:
                            ref_ids.add(str(rid))
        except (json.JSONDecodeError, TypeError):
            pass

    # Deduped, capped ref fan-out (the final result is a set, so dedup is lossless).
    for rid in list(ref_ids)[:_MAX_LINK_REFS]:
        card_rows = await db.execute_fetchall(
            "SELECT DISTINCT entity_id FROM action_cards WHERE entity_id LIKE ? LIMIT 5",
            (f"%{rid}%",),
        )
        for cr in card_rows:
            if cr["entity_id"]:
                linked.add(cr["entity_id"])

    return linked - entity_ids  # Only return newly discovered ones


# ---------------------------------------------------------------------------
# Clustering and chapter detection
# ---------------------------------------------------------------------------

_PRIORITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

# Display labels per raw_event_type (a different value space from terminal-ness;
# the terminal-event source of truth lives in egress/registry._TERMINAL_EVENT_TYPES —
# keep these in mind together when adding/renaming platform event types).
_CHAPTER_LABELS = {
    # event_type hints
    "issue_created": "Created",
    "pr_created": "Created",
    "message_sent": "Discussion",
    "email_received": "Discussion",
    "pr_commented": "Code Review",
    "issue_commented": "Discussion",
    "pr_approved": "Approved",
    "pr_merged": "Merged",
    "issue_resolved": "Resolved",
    "issue_status_changed": "Status Change",
    "issue_reopened": "Reopened",
    "build_completed": "Build",
    "build_failed": "Build Failed",
    "pr_declined": "Declined",
}


def _build_clusters(
    all_cards: list[CardResponse],
    entity_map: dict[str, TraceEntity],
    seeds: list[dict],
) -> list[TraceCluster]:
    """Group cards into clusters by connected entity_ids."""
    if not all_cards:
        return []

    # Union-Find to group connected entity_ids
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # All entity_ids from cards
    card_entity_ids = {c.entity_id for c in all_cards if c.entity_id}

    # Initialize parent
    for eid in card_entity_ids:
        parent[eid] = eid

    # Union entities that share the same subject_id or are in entity_map links
    entity_subjects: dict[str, list[str]] = {}
    for eid in card_entity_ids:
        parts = eid.split(":", 2)
        if len(parts) >= 3:
            subject = parts[2].lower()
            entity_subjects.setdefault(subject, []).append(eid)

    for _subject, eids in entity_subjects.items():
        for i in range(1, len(eids)):
            union(eids[0], eids[i])

    # Group cards by cluster root
    cluster_cards: dict[str, list[CardResponse]] = {}
    for card in all_cards:
        eid = card.entity_id or f"singleton:{card.card_id}"
        root = find(eid) if eid in parent else eid
        cluster_cards.setdefault(root, []).append(card)

    # Build TraceCluster objects
    clusters: list[TraceCluster] = []
    for root, cards in cluster_cards.items():
        # Identify primary entity (most cards)
        entity_counts: dict[str, int] = {}
        for c in cards:
            if c.entity_id:
                entity_counts[c.entity_id] = entity_counts.get(c.entity_id, 0) + 1

        primary_eid = max(entity_counts, key=entity_counts.get) if entity_counts else root
        primary = entity_map.get(primary_eid, TraceEntity(
            entity_id=primary_eid,
            title=cards[0].source_ref or cards[0].header,
            url=cards[0].source_url,
            platform=primary_eid.split(":")[0] if ":" in primary_eid else "",
        ))

        linked = [
            entity_map.get(eid, TraceEntity(
                entity_id=eid, title=eid, platform=eid.split(":")[0] if ":" in eid else ""
            ))
            for eid in entity_counts
            if eid != primary_eid
        ]

        # Build chapters
        chapters = _detect_chapters(cards)

        # Build status summary
        platforms = list({c.entity_id.split(":")[0] for c in cards if c.entity_id and ":" in c.entity_id})
        dates = [c.created_at for c in cards if c.created_at]
        pending = sum(
            1 for c in cards if c.status in ("pending", "ready", "awaiting_input")
        )

        latest_card = cards[-1]
        current_state = latest_card.status
        if latest_card.source_ref:
            current_state = f"{latest_card.status} ({latest_card.source_ref})"

        status_summary = TraceStatusSummary(
            current_state=current_state,
            platforms_involved=sorted(platforms),
            total_cards=len(cards),
            date_range={
                "from": min(dates)[:10] if dates else "",
                "to": max(dates)[:10] if dates else "",
            },
            pending_actions=pending,
        )

        clusters.append(TraceCluster(
            cluster_id=f"cluster_{uuid.uuid4().hex[:8]}",
            primary_entity=primary,
            linked_entities=linked,
            chapters=chapters,
            timeline=cards,
            status_summary=status_summary,
        ))

    # Sort clusters: largest first
    clusters.sort(key=lambda c: c.status_summary.total_cards, reverse=True)
    return clusters


def _detect_chapters(cards: list[CardResponse]) -> list[TraceChapter]:
    """Group chronological cards into logical chapters."""
    if not cards:
        return []

    chapters: list[TraceChapter] = []
    current_label = ""
    current_cards: list[str] = []
    current_ts = ""
    last_time: datetime | None = None

    for card in cards:
        label = _infer_chapter_label(card, is_first=(len(chapters) == 0 and not current_cards))

        # Detect time gap > 24 hours
        card_time = None
        if card.created_at:
            try:
                card_time = datetime.fromisoformat(card.created_at.replace("Z", "+00:00"))
            except ValueError:
                pass

        time_gap = False
        if last_time and card_time:
            gap_hours = (card_time - last_time).total_seconds() / 3600
            time_gap = gap_hours > 24

        # Start new chapter if label changes or time gap
        if label != current_label or time_gap:
            if current_cards:
                chapters.append(TraceChapter(
                    label=current_label,
                    timestamp=current_ts,
                    card_ids=current_cards,
                ))
            current_label = label
            current_cards = [card.card_id]
            current_ts = card.created_at or ""
        else:
            current_cards.append(card.card_id)

        if card_time:
            last_time = card_time

    # Flush last chapter
    if current_cards:
        chapters.append(TraceChapter(
            label=current_label,
            timestamp=current_ts,
            card_ids=current_cards,
        ))

    return chapters


def _infer_chapter_label(card: CardResponse, is_first: bool = False) -> str:
    """Infer a human-readable chapter label from card metadata."""
    if is_first:
        return "Created"

    # Try to infer from entity_id platform
    platform = ""
    if card.entity_id and ":" in card.entity_id:
        platform = card.entity_id.split(":")[0]

    # Check status for terminal states
    if card.status in ("done", "dismissed"):
        return "Resolved"
    if card.status == "failed":
        return "Failed"
    if card.status == "archived":
        return "Archived"

    # Use platform defaults
    return _get_chapter_default(platform)
