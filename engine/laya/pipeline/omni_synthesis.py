# Copyright 2026 Aayush Chawla
# SPDX-License-Identifier: Apache-2.0

"""OMNI LLM resynthesis — the expensive, scheduled operation that compresses
the recent layer into period aggregates, folds old periods into milestones,
and surfaces attention items via the LLM.

Public surface (used outside this module, including by api/omni_api.py via the
``omni.py`` facade): ``run_omni_resynthesis``.
"""

from __future__ import annotations

import copy
import json
import uuid

import structlog

from laya.config import load_settings
from laya.db.timeutil import db_now
from laya.events import publish
from laya.llm.base import get_llm_client
from laya.llm.client import DEFAULT_MAX_TOKENS
from laya.models.card_lifecycle import TERMINAL_STATUSES as _TERMINAL_STATUSES
from laya.llm.prompts.omni import (
    build_omni_resynthesis_messages,
    get_omni_json_schema,
)
from laya.pipeline.omni_change import (
    compute_resynthesis_change_summary,
    decorate_item_keys,
)
from laya.pipeline.omni_live import fetch_card_meta, item_source_cards, live_max_priority
from laya.pipeline.omni_snapshot import _latest_cache, all_resolved, get_gate, load_full_snapshot

log = structlog.get_logger()

# Max new cards folded into a single resynthesis LLM call. A full run can fetch
# up to fetch_cap (~100-150) cards; combined with the current snapshot that
# exceeds a local model's usable window, and the omni JSON schema is unforgiving
# — a truncated response yields NO parsed output, losing the whole batch AND
# handing the next run an even bigger backlog (the failure spiral flagged in the
# Jul-2026 review, P6-13). We fold new cards in chunks of this size across
# sequential smaller calls instead. ~30-50 is the sweet spot: strictly smaller
# calls that local models can complete, at the cost of more of them.
_RESYNTH_CHUNK_SIZE = 40

_VALID_OMNI_PRIORITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}

# `_TERMINAL_STATUSES` is imported from card_lifecycle at module top (single source
# of truth): a subject in one of these statuses is resolved and leaves the attention
# section. No local mirror — that previously risked silent divergence.


def _is_degenerate_sections(sections: list[dict]) -> bool:
    """Detect a placeholder/skeleton resynthesis result rather than real content.

    A local model under load (e.g. flooded because the concurrency cap wasn't
    honored) can return every field as a literal '...' — observed: all items with
    text='...' and priority='...', plus a hallucinated extra section. Because
    resynthesis carries the snapshot FORWARD, storing such a result poisons the
    base and EVERY later incremental inherits it, so the whole Omni page renders
    as '...' until a good full snapshot replaces it.

    We use this to (a) reject a degenerate result before storing it — treating it
    like a failed synthesis so the last good snapshot stays — and (b) refuse to
    feed an already-poisoned snapshot back to the model on the next run, so it
    regenerates fresh instead of echoing the '...'.
    """
    items = [it for s in sections for it in s.get("items", [])]
    if not items:
        return False
    bad = 0
    for it in items:
        text = (it.get("text") or "").strip()
        prio = it.get("priority")
        if text in ("", "...", "…") or (prio is not None and prio not in _VALID_OMNI_PRIORITIES):
            bad += 1
    # Half or more of the items being placeholders is unmistakable — a healthy
    # synthesis has ~zero. A ratio (not "all") tolerates one odd item.
    return bad >= len(items) * 0.5


async def run_omni_resynthesis(
    space_id: str | None = None,
    snapshot_type: str = "scheduled",
) -> list[str]:
    """Run a full Omni resynthesis for one or all spaces.

    This is the expensive operation — it calls the LLM to compress the
    recent layer into period aggregates, fold old periods into milestones,
    and surface attention items.

    Args:
        space_id: Specific space to resynthesize, or None for all spaces.
        snapshot_type: "scheduled" (EOD), "rolling" (interval/threshold), or "manual".

    Returns:
        List of snapshot_ids created.
    """
    from laya.db.sqlite import get_db

    settings = load_settings()
    omni_cfg = settings.get("omni", {})
    density = omni_cfg.get("density", "compact")
    try:
        event_threshold = int(omni_cfg.get("event_threshold", 50))
    except (TypeError, ValueError):
        event_threshold = 50
    event_threshold = max(0, min(100, event_threshold))

    db = await get_db()

    # Determine which spaces to process
    if space_id:
        space_ids = [space_id]
    else:
        space_rows = await db.execute_fetchall("SELECT space_id FROM spaces")
        space_ids = [row["space_id"] for row in space_rows] if space_rows else ["default"]
        # Ensure default is always included
        if "default" not in space_ids:
            space_ids.append("default")

    created_ids = []

    for sid in space_ids:
        try:
            snapshot_id = await _resynthesize_space(db, sid, density, snapshot_type, event_threshold)
            if snapshot_id:
                created_ids.append(snapshot_id)
        except Exception as e:
            log.error("omni_resynthesis_failed", space_id=sid, error=str(e))

    return created_ids


async def _resynthesize_space(
    db,
    space_id: str,
    density: str,
    snapshot_type: str = "scheduled",
    event_threshold: int = 50,
) -> str | None:
    """Resynthesize Omni for a single space.

    Gates the queue processor for this space during the LLM call so that
    incremental updates don't race with the resynthesis snapshot write.
    Cards that arrive during resynthesis stay in omni_queue and are
    processed on the next poll after the gate reopens.
    """
    gate = get_gate(space_id)

    # 1. Load latest snapshot (reconstructed if delta chain)
    current_snapshot, current_version, existing_card_ids, _meta = await load_full_snapshot(db, space_id)

    # The pre-fold sections, kept separately because `current_snapshot` may be
    # discarded below (degenerate recovery) and is fed forward through the LLM
    # calls. The change summary must diff against what the user was ACTUALLY
    # looking at, so it reads this copy.
    prior_sections = copy.deepcopy((current_snapshot or {}).get("sections", []))

    # Recovery: if the last snapshot is itself degenerate (a prior bad synthesis
    # poisoned the chain), don't feed it back to the model — that just makes it
    # echo the '...'. Drop it so this run regenerates real content from scratch;
    # item_states/resolved-pruning below are skipped when there's no snapshot.
    if current_snapshot and _is_degenerate_sections(current_snapshot.get("sections", [])):
        log.warning(
            "omni_resynthesis_discarding_degenerate_snapshot",
            space_id=space_id, version=current_version,
        )
        current_snapshot = None

    # 2. Load pinned items
    pin_rows = await db.execute_fetchall(
        "SELECT item_text, source_card_ids, platforms FROM omni_pins WHERE space_id = ?",
        (space_id,),
    )
    pinned_items = [
        {
            "item_text": row["item_text"],
            "source_card_ids": json.loads(row["source_card_ids"]),
            "platforms": json.loads(row["platforms"]),
        }
        for row in pin_rows
    ]

    # 3. Query recent cards (since last successful resynthesis)
    last_synth_row = await db.execute_fetchall(
        """SELECT generated_at FROM omni_snapshots
           WHERE space_id = ? AND snapshot_type IN ('scheduled', 'rolling', 'manual')
           ORDER BY version DESC LIMIT 1""",
        (space_id,),
    )

    # generated_at and resolved_at are both stored in canonical DB format now
    # (space-separated UTC — see laya/db/timeutil.py), so one space-format `since`
    # bound compares correctly against both created_at and resolved_at.
    raw = last_synth_row[0]["generated_at"] if last_synth_row else None
    since = raw if raw else "2000-01-01 00:00:00"

    # Fetch cap scales with event_threshold so users who tolerate larger
    # per-run batches get proportional headroom for failure recovery. Floor
    # is 100 (also applies when threshold is disabled).
    fetch_cap = max(100, 3 * event_threshold) if event_threshold > 0 else 100

    card_rows = await db.execute_fetchall(
        """SELECT ac.card_id, ac.header, ac.summary, ac.priority, ac.persona,
                  ac.status, ac.user_feedback, ac.category, ac.entity_id,
                  e.source_platform, e.actor_name
           FROM action_cards ac
           LEFT JOIN events e ON ac.event_id = e.event_id
           WHERE ac.space_id = ? AND ac.created_at > ?
           ORDER BY ac.created_at DESC
           LIMIT ?""",
        (space_id, since, fetch_cap),
    )

    new_cards = [
        {
            "card_id": row["card_id"],
            "header": row["header"],
            "summary": row["summary"],
            "priority": row["priority"],
            "source_platform": row["source_platform"] or "unknown",
            "user_feedback": row["user_feedback"],
            "status": row["status"],
            "entity_id": row["entity_id"],
        }
        for row in card_rows
    ]

    # Enrich cards with tags for the LLM prompt
    from laya.pipeline.tags import batch_load_tags
    omni_card_ids = [c["card_id"] for c in new_cards]
    tags_map = await batch_load_tags(omni_card_ids)
    for c in new_cards:
        card_tag_entries = tags_map.get(("card", c["card_id"]), [])
        c["tags"] = ", ".join(t["tag_name"] for t in card_tag_entries) if card_tag_entries else ""

    # 4. Separate user-acted cards (for higher weight in prompt)
    acted_cards = [
        c for c in new_cards
        if c.get("user_feedback") or c.get("status") in ("done", "dismissed", "archived")
    ]

    # If no new cards, skip — nothing has changed since the last synthesis.
    # (No snapshot + no cards = first run with nothing to process;
    #  existing snapshot + no cards = redundant LLM call with identical input.)
    if not new_cards:
        log.info("omni_resynthesis_skipped_no_new_cards", space_id=space_id)
        return None

    # Visibility: warn when the fetch cap is saturated. Under the default
    # trigger config this should be rare; if it fires repeatedly, check for
    # recent LLM failures or misconfigured triggers before trusting the
    # summary (cards beyond the window are silently dropped from the LLM
    # input, though they remain in the incremental snapshot).
    if len(new_cards) >= fetch_cap:
        log.warning(
            "omni_resynthesis_cards_saturated",
            space_id=space_id,
            cap=fetch_cap,
            event_threshold=event_threshold,
            since=since,
        )

    # 4b. Derive the live state of the CURRENT snapshot's items so the LLM can
    # drop subjects that have since resolved or de-escalated. Resynthesis is
    # otherwise blind to status-only transitions of cards created before `since`
    # (they don't reappear in `new_cards`), so without this an attention item
    # sticks forever. We compute state from each item's source_cards because the
    # auto-resolution path (emit.py) transitions the very sibling cards embedded
    # in the aggregate to a terminal status.
    item_states: list[dict] = []
    if current_snapshot:
        snapshot_card_ids: list[str] = []
        for section in current_snapshot.get("sections", []):
            if section.get("type") not in ("attention", "recent"):
                continue
            for item in section.get("items", []):
                snapshot_card_ids.extend(item_source_cards(item))
        snap_meta = await fetch_card_meta(db, snapshot_card_ids)
        for section in current_snapshot.get("sections", []):
            if section.get("type") not in ("attention", "recent"):
                continue
            for item in section.get("items", []):
                cids = item_source_cards(item)
                if not cids:
                    continue
                item_states.append({
                    "text": item.get("text", ""),
                    "all_resolved": all_resolved(cids, snap_meta),
                    "live_max_priority": live_max_priority(cids, snap_meta),
                })

    # 4c. Subjects that reached a terminal state since the last synthesis.
    resolved_rows = await db.execute_fetchall(
        """SELECT entity_id, header, status, resolved_at
           FROM action_cards
           WHERE space_id = ? AND resolved_at IS NOT NULL AND resolved_at > ?
             AND status IN ('done', 'dismissed', 'archived')
           ORDER BY resolved_at DESC LIMIT 100""",
        (space_id, since),
    )
    resolved_cards: list[dict] = []
    _seen_entities: set[str] = set()
    # entity_id → when that subject reached a terminal state. The changelog rail
    # renders "closed 14:22" beside a resolved line; the card that resolved a
    # subject is often NOT one of the aggregate's own source_cards (a merge event
    # mints a new card on the same entity), so the timestamp is keyed by entity.
    resolved_at_by_entity: dict[str, str] = {}
    for r in resolved_rows:
        eid = r["entity_id"]
        if eid and r["resolved_at"] and eid not in resolved_at_by_entity:
            resolved_at_by_entity[eid] = r["resolved_at"]
        if eid and eid in _seen_entities:
            continue  # dedupe by entity — one resolution line per subject
        if eid:
            _seen_entities.add(eid)
        resolved_cards.append({
            "entity_id": eid,
            "header": r["header"],
            "status": r["status"],
        })

    # 5. Fold the new cards into the snapshot across one or more LLM calls.
    #
    # Small batches run as a SINGLE call, byte-identical to the pre-P6-13 path.
    # Large bursts are folded in chunks of _RESYNTH_CHUNK_SIZE across sequential
    # calls, each folding one chunk into the evolving snapshot, so no single call
    # carries the whole burst (see the constant's comment for why that matters).
    #
    # Ordering: new_cards is newest-first (created_at DESC), so we fold the
    # OLDEST chunk first and the newest last — that way the freshest cards land
    # in the final call and dominate the "recent" section. Snapshot-relative
    # inputs (item_states / resolved_cards, which prune subjects that resolved
    # since the last synthesis) apply only to the FIRST fold; afterwards the
    # evolving snapshot already reflects them. Pins carry through every fold, and
    # each chunk brings its own acted cards.
    #
    # Failure handling is deliberately all-or-nothing: if any chunk fails to
    # parse we discard the whole run and return None WITHOUT storing, leaving
    # `since` unadvanced so every card returns next run. That avoids the plumbing
    # needed to store a partial fold without silently dropping the un-folded
    # cards (the fetch is purely `since`-driven — line ~724), and because each
    # chunk is small the retry almost always succeeds. The previous snapshot
    # stays on screen until it does.
    schema = get_omni_json_schema(density)

    chunks = [
        new_cards[i:i + _RESYNTH_CHUNK_SIZE]
        for i in range(0, len(new_cards), _RESYNTH_CHUNK_SIZE)
    ]
    chunks.reverse()  # oldest chunk first, newest last

    # --- GATE: pause queue processing for this space during the LLM call(s) ---
    gate.clear()
    log.info("omni_resynthesis_gate_closed", space_id=space_id, chunks=len(chunks))

    # 6. Call LLM (once per chunk)
    try:
        folded_snapshot = current_snapshot
        result_sections: list[dict] = []
        for idx, chunk in enumerate(chunks):
            first = idx == 0
            chunk_acted = [
                c for c in chunk
                if c.get("user_feedback")
                or c.get("status") in ("done", "dismissed", "archived")
            ]
            messages = build_omni_resynthesis_messages(
                current_snapshot=folded_snapshot,
                new_cards=chunk,
                acted_cards=chunk_acted,
                pinned_items=pinned_items,
                density=density,
                space_id=space_id,
                # Prune-resolved hints only make sense against the ORIGINAL
                # snapshot — apply them once, on the first fold.
                item_states=item_states if first else [],
                resolved_cards=resolved_cards if first else [],
            )
            response = await get_llm_client().generate(
                role="omni",
                messages=messages,
                response_schema=schema,
                step="omni_resynthesis",
                temperature=0.3,
                max_tokens=DEFAULT_MAX_TOKENS,
                space_id=space_id,
            )

            if not response.parsed:
                truncation_hint = " (response was truncated)" if response.truncated else ""
                raise ValueError(
                    f"LLM returned malformed JSON for Omni resynthesis "
                    f"chunk {idx + 1}/{len(chunks)}{truncation_hint} "
                    f"(output_tokens={response.output_tokens}, model={response.model})"
                )

            result_sections = response.parsed.get("sections", [])
            folded_snapshot = response.parsed  # feed the fold forward

    except Exception as e:
        log.error("omni_resynthesis_llm_failed", space_id=space_id, error=str(e))
        # Re-open the gate so queued cards resume processing
        gate.set()
        log.info("omni_resynthesis_gate_opened", space_id=space_id, reason="llm_failed")
        return None

    # Reject a degenerate ('...'-everywhere) result before it can be stored and
    # poison the forward-carried snapshot — see _is_degenerate_sections. Treat it
    # like a failed synthesis: keep the last good snapshot, retry next run.
    if _is_degenerate_sections(result_sections):
        log.warning(
            "omni_resynthesis_degenerate_result",
            space_id=space_id, items=sum(len(s.get("items", [])) for s in result_sections),
        )
        gate.set()
        log.info("omni_resynthesis_gate_opened", space_id=space_id, reason="degenerate_result")
        return None

    # Reject an all-empty result (zero items across every section) for the same
    # reason as the '...' skeleton above: it poisons the forward-carried snapshot.
    # _is_degenerate_sections deliberately EXEMPTS the no-items case (it targets
    # the placeholder-text variant), so the empty-collapse variant is caught here.
    # We only reach this point with new_cards non-empty (the `if not new_cards`
    # early-return above guarantees it), so a synthesis that folds real,
    # un-summarized cards into *nothing* is a model failure, not a legitimately
    # empty state — a mid-size local model can over-apply the prompt's "compress
    # everything / an empty array is allowed" guidance and emit zero items.
    # Storing it would wipe the recent items the incremental queue accumulated
    # AND feed the empty snapshot back into the next run, so every later
    # resynthesis stays empty (observed: high-volume space collapsing 13k→389
    # bytes over successive rolling runs). Treat it as a failed synthesis: keep
    # the last good snapshot, leave `since` unadvanced so these cards retry.
    # NOTE: checked BEFORE the resolved-attention prune below, so a result whose
    # items were legitimately dropped as resolved still stores (correctly empty)
    # while a model that returned nothing does not.
    if sum(len(s.get("items", [])) for s in result_sections) == 0:
        log.warning(
            "omni_resynthesis_empty_result",
            space_id=space_id, new_cards=len(new_cards),
        )
        gate.set()
        log.info("omni_resynthesis_gate_opened", space_id=space_id, reason="empty_result")
        return None

    # 7. Inject space_id into all items
    for section in result_sections:
        for item in section.get("items", []):
            item["space_id"] = space_id

    # 7b. Deterministic safety-net prune + entity_ids backfill.
    # The prompt asks the LLM to drop resolved subjects, but a stubborn model can
    # carry them anyway, and the status-only-transition path gives the LLM only a
    # derived hint. So we authoritatively drop any *attention* item whose source
    # cards are ALL terminal — that item cannot need attention. We also backfill
    # entity_ids from source_cards when the LLM left them empty, so the NEXT
    # resynthesis can correlate this subject reliably.
    output_card_ids: list[str] = []
    for section in result_sections:
        for item in section.get("items", []):
            output_card_ids.extend(item_source_cards(item))
    # Prior cards are fetched in the same batch: the change summary has to decide
    # whether a line that VANISHED did so because its subjects resolved, and
    # those cards are by definition absent from the new output.
    for section in prior_sections:
        for item in section.get("items", []):
            output_card_ids.extend(item_source_cards(item))
    out_meta = await fetch_card_meta(db, output_card_ids)

    pruned_attention = 0
    for section in result_sections:
        is_attention = section.get("type") == "attention"
        kept_items = []
        for item in section.get("items", []):
            cids = item_source_cards(item)
            if is_attention and all_resolved(cids, out_meta):
                pruned_attention += 1
                continue  # every source subject resolved — drop from attention
            # Backfill entity_ids the LLM omitted, from the live card metadata.
            if not item.get("entity_ids"):
                eids = []
                for cid in cids:
                    eid = (out_meta.get(cid) or {}).get("entity_id")
                    if eid and eid not in eids:
                        eids.append(eid)
                item["entity_ids"] = eids
            kept_items.append(item)
        section["items"] = kept_items

    if pruned_attention:
        log.info("omni_attention_pruned", space_id=space_id, dropped=pruned_attention)

    # 7c. Stamp item keys, then diff this result against what the user was
    # looking at. Order matters: keys are computed from the FINAL entity_ids
    # (backfilled just above), and the diff must see the post-prune sections so a
    # resolved attention item reads as `resolved`, not as a silent disappearance.
    decorate_item_keys(result_sections)
    change_summary = compute_resynthesis_change_summary(
        prior_sections,
        result_sections,
        out_meta,
        _TERMINAL_STATUSES,
        resolved_at_by_entity,
    )

    # 8. Build stats
    cards_acted_count = len(acted_cards)
    total_items_before = sum(
        len(s.get("items", []))
        for s in (current_snapshot or {}).get("sections", [])
    ) + len(new_cards)
    total_items_after = sum(len(s.get("items", [])) for s in result_sections)
    compression = 1.0 - (total_items_after / max(total_items_before, 1))

    content = {
        "sections": result_sections,
        "stats": {
            "events_processed": len(existing_card_ids) + len(new_cards),
            "cards_acted_on": cards_acted_count,
            "compression_ratio": round(compression, 2),
        },
    }

    # 9. Save new snapshot — re-read the current max version to avoid
    #    collision with any incremental snapshots that were written before
    #    the gate closed (the gate only blocks future queue polls).
    now = db_now()
    snapshot_id = f"omni_{uuid.uuid4().hex[:12]}"
    all_card_ids = list(set(existing_card_ids + [c["card_id"] for c in new_cards]))

    max_ver_rows = await db.execute_fetchall(
        "SELECT COALESCE(MAX(version), 0) AS mv FROM omni_snapshots WHERE space_id = ?",
        (space_id,),
    )
    new_version = max_ver_rows[0]["mv"] + 1

    await db.execute(
        """INSERT INTO omni_snapshots
           (snapshot_id, space_id, version, generated_at, snapshot_type,
            content_json, card_ids, events_processed, created_at,
            is_delta, base_version, change_summary_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            snapshot_id,
            space_id,
            new_version,
            now,
            snapshot_type,
            json.dumps(content),
            json.dumps(all_card_ids),
            len(all_card_ids),
            now,
            0,     # Full base snapshot, not a delta
            None,
            json.dumps(change_summary),
        ),
    )
    await db.commit()

    # Update cache with full state
    _latest_cache[space_id] = {
        "content": content,
        "version": new_version,
        "card_ids": all_card_ids,
        "meta": {
            "snapshot_id": snapshot_id,
            "generated_at": now,
            "snapshot_type": snapshot_type,
        },
    }

    # --- GATE: re-open so queued cards resume on next poll ---
    gate.set()
    log.info("omni_resynthesis_gate_opened", space_id=space_id, reason="resynthesis_complete")

    # 10. Broadcast
    await publish({
        "type": "omni_updated",
        "payload": {
            "space_id": space_id,
            "version": new_version,
            "snapshot_type": snapshot_type,
            "sections_count": len(result_sections),
        },
    })

    log.info(
        "omni_resynthesis_complete",
        space_id=space_id,
        version=new_version,
        snapshot_id=snapshot_id,
        items=total_items_after,
        compression=round(compression, 2),
        **{f"changed_{k}": v for k, v in change_summary["counts"].items()},
    )

    return snapshot_id
