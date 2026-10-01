# Copyright 2026 Aayush Chawla
# SPDX-License-Identifier: Apache-2.0

"""Trace pipeline — semantic cross-platform entity search.

Three-phase search:
  1. Discovery  — ChromaDB semantic + SQLite fuzzy + entity lookup, merged via RRF
  2. Expansion  — fetch ALL cards for matched entities + cross-references
  3. Clustering — group by connected entities, order chronologically, detect chapters

This module is the thin orchestrator/public facade over three pieces split
out for maintainability (#8):

- ``trace_retrieval``: discovery signals, RRF fusion input, trace-feedback
  exclusion, and the LLM relevance filter (``_identifier_search``,
  ``_semantic_search``, ``_card_text_search``, ``_card_fuzzy_search``,
  ``_entity_table_search``, ``_event_keyword_search``,
  ``_query_trace_feedback``, ``_llm_relevance_filter``).
- ``trace_clustering``: seed expansion and entity clustering/chapter
  detection (``_expand_seeds``, ``_build_clusters``, ``_detect_chapters``).
- ``trace_narrative``: LLM narrative/summary synthesis, streamed over
  WebSocket (``stream_trace_narrative``, ``stream_trace_summary``).

What stays here is the ``run_trace`` orchestration itself — phase sequencing,
progress events, the cancel-event registry, and persistence — since it is
this module's own entry point, not one of the three concerns above.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid

import structlog

from laya.db.sqlite import get_db
from laya.db.timeutil import db_now
from laya.events import publish
from laya.retrieval import reciprocal_rank_fusion
from laya.llm.tools.constants import (
    TRACE_ENTITY_SEARCH_MAX,
    TRACE_EVENT_SEARCH_MAX,
    TRACE_FUZZY_SEARCH_MAX,
    TRACE_IDENTIFIER_SEARCH_MAX,
    TRACE_SEMANTIC_SEARCH_MAX,
    TRACE_TEXT_SEARCH_MAX,
)
from laya.models.trace import SearchMetadata, TraceRequest, TraceResponse

# Re-exported so existing callers (api/trace_api.py, tests) that import these
# names from `laya.pipeline.trace` keep working unchanged.
from laya.pipeline.trace_clustering import (  # noqa: F401
    _build_clusters,
    _detect_chapters,
    _expand_seeds,
    _find_linked_entities,
    _infer_chapter_label,
)
from laya.pipeline.trace_narrative import (  # noqa: F401
    _stream_cluster_narrative,
    _stream_cluster_narrative_inner,
    _update_cluster_narrative,
    stream_trace_narrative,
    stream_trace_summary,
)
from laya.pipeline.trace_retrieval import (  # noqa: F401
    _card_fuzzy_search,
    _card_text_search,
    _entity_table_search,
    _event_keyword_search,
    _event_keyword_search_fts,
    _event_keyword_search_like,
    _identifier_search,
    _llm_relevance_filter,
    _query_trace_feedback,
    _semantic_search,
)

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Cancellation support — per-trace asyncio.Event signals
# ---------------------------------------------------------------------------
_cancel_events: dict[str, asyncio.Event] = {}


class TraceCancelled(Exception):
    """Raised when a trace is cancelled mid-execution."""


class TraceAlreadyRunning(Exception):
    """Raised when a trace_id is already executing (concurrent rerun of the same id)."""


def request_cancel(trace_id: str) -> bool:
    """Signal a running trace to abort. Returns True if there was a trace to cancel."""
    ev = _cancel_events.get(trace_id)
    if ev:
        ev.set()
        return True
    return False


def _check_cancelled(trace_id: str) -> None:
    """Raise TraceCancelled if the trace has been cancelled."""
    ev = _cancel_events.get(trace_id)
    if ev and ev.is_set():
        raise TraceCancelled(f"Trace {trace_id} cancelled")


async def _cancellable(coro, trace_id: str):
    """Run a coroutine but abort immediately if the trace is cancelled.

    Wraps the coroutine in a task and races it against the cancel event.
    If cancelled, the underlying task is cancelled too (aborting the HTTP
    request to the LLM provider).
    """
    ev = _cancel_events.get(trace_id)
    if not ev:
        return await coro

    task = asyncio.ensure_future(coro)
    cancel_waiter = asyncio.ensure_future(ev.wait())

    done, pending = await asyncio.wait(
        {task, cancel_waiter}, return_when=asyncio.FIRST_COMPLETED
    )

    for p in pending:
        p.cancel()
        try:
            await p
        except (asyncio.CancelledError, Exception):
            pass

    if cancel_waiter in done:
        raise TraceCancelled(f"Trace {trace_id} cancelled")

    return task.result()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def run_trace(request: TraceRequest, trace_id: str | None = None) -> TraceResponse:
    """Execute a full trace: discovery → expansion → clustering.

    `trace_id` is supplied by a rerun so the run REUSES the existing identity and
    updates that row in place (see _save_trace's upsert). Minting a fresh id on
    rerun — and deleting the old row up front, as the API used to — meant every
    history link and in-flight client poll 404'd the instant a rerun started, and
    a cancel/crash mid-run destroyed the trace permanently. Reusing the id and
    upserting only on success makes rerun idempotent and crash-safe.
    """
    t0 = time.monotonic()
    trace_id = trace_id or f"trace_{uuid.uuid4().hex[:12]}"

    # _cancel_events is keyed by trace_id. With unique-per-run ids a same-id
    # collision was impossible; now that reruns reuse an id, two concurrent runs
    # of the SAME id would clobber each other's cancel event (making the first
    # uncancellable, and letting the first's finally-pop deregister the second)
    # and would race the same row in _save_trace. Reject the second run instead.
    if trace_id in _cancel_events:
        raise TraceAlreadyRunning(trace_id)

    # Register cancellation event for this trace
    cancel_event = asyncio.Event()
    _cancel_events[trace_id] = cancel_event

    # Logged here (not in the API handlers) so create + rerun both carry a trace_id
    # from the first line — the API's trace_requested fires before the id is minted,
    # which made lifecycle events impossible to correlate across a run.
    log.info("trace_started", trace_id=trace_id, query=request.query, space_id=request.space_id)

    async def _progress(stage: str, step: int, total: int) -> None:
        _check_cancelled(trace_id)  # Check before each stage
        await publish({
            "type": "trace_progress",
            "trace_id": trace_id,
            "query": request.query,
            "stage": stage,
            "step": step,
            "total": total,
        })

    try:
        return await _run_trace_inner(request, trace_id, _progress, t0)
    except TraceCancelled:
        log.info("trace_cancelled", trace_id=trace_id)
        await publish({
            "type": "trace_cancelled",
            "trace_id": trace_id,
        })
        raise
    finally:
        _cancel_events.pop(trace_id, None)


async def _run_trace_inner(
    request: TraceRequest,
    trace_id: str,
    _progress,
    t0: float,
) -> TraceResponse:
    """Inner trace execution — separated so run_trace can handle cancellation."""
    # Phase 1 — Discovery
    # Build search signals based on request flags. All default to enabled
    # for backward compat. Advanced settings let users disable stages.
    total_steps = 6
    await _progress("Searching", 1, total_steps)
    coros: list = []
    signal_labels: list[str] = []

    if request.enable_identifier:
        coros.append(_identifier_search(request.query, request.space_id, n=TRACE_IDENTIFIER_SEARCH_MAX))
        signal_labels.append("identifier")
    if request.enable_semantic:
        coros.append(_semantic_search(request.query, request.space_id, n=TRACE_SEMANTIC_SEARCH_MAX))
        signal_labels.append("semantic")
    if request.enable_entity:
        coros.append(_entity_table_search(request.query, n=TRACE_ENTITY_SEARCH_MAX))
        signal_labels.append("entity")

    # Text search: strict phrase-match LIKE on card content only.
    if request.enable_text:
        coros.append(_card_text_search(
            request.query, request.space_id, n=TRACE_TEXT_SEARCH_MAX,
            include_archived=request.include_archived,
        ))
        signal_labels.append("text")

    # Fuzzy search: keyword-split LIKE on cards + events — broader but noisier.
    if request.fuzzy_search:
        coros.append(_card_fuzzy_search(
            request.query, request.space_id, n=TRACE_FUZZY_SEARCH_MAX,
            include_archived=request.include_archived,
        ))
        coros.append(_event_keyword_search(request.query, request.space_id, n=TRACE_EVENT_SEARCH_MAX))
        signal_labels.extend(["fuzzy", "event"])

    results = await _cancellable(
        asyncio.gather(*coros, return_exceptions=True), trace_id
    )

    # Collect successful results.
    # Identifier matches are guaranteed seeds — they bypass RRF to ensure
    # precise matches (like "PR-540") aren't drowned by broader signals.
    guaranteed_seeds: list[dict] = []
    ranked_lists: list[list[dict]] = []
    meta = SearchMetadata(
        fuzzy_search=request.fuzzy_search,
        enable_semantic=request.enable_semantic,
        enable_text=request.enable_text,
        enable_llm_filter=request.enable_llm_filter,
    )
    for label, result in zip(signal_labels, results):
        if isinstance(result, list):
            if label == "identifier":
                guaranteed_seeds.extend(result)
            else:
                ranked_lists.append(result)
            if label == "semantic":
                meta.semantic_hits = len(result)
                distances = [r.get("distance", 1.0) for r in result if "distance" in r]
                if distances:
                    meta.avg_semantic_distance = round(sum(distances) / len(distances), 4)
            elif label == "fuzzy":
                meta.fuzzy_hits = len(result)
            elif label == "entity":
                meta.entity_hits = len(result)
        elif isinstance(result, Exception):
            log.warning("trace_discovery_signal_failed", signal=label, error=str(result))

    log.info(
        "trace_discovery_results",
        trace_id=trace_id,
        query=request.query,
        identifier_hits=len(guaranteed_seeds),
        identifier_ids=[(s.get("card_id") or s.get("entity_id") or "?")[:30] for s in guaranteed_seeds[:5]],
        rrf_signal_count=len(ranked_lists),
        rrf_signal_sizes=[len(rl) for rl in ranked_lists],
    )

    # Merge non-identifier signals via RRF
    await _progress("Ranking results", 2, total_steps)
    loop = asyncio.get_event_loop()
    fused = await loop.run_in_executor(None, reciprocal_rank_fusion, ranked_lists, 60)

    # Build seed list: guaranteed identifier matches first, then RRF results
    seen: set[str] = set()
    seeds: list[dict] = []
    for item in guaranteed_seeds:
        uid = item.get("entity_id") or item.get("card_id") or item.get("id") or ""
        if uid and uid not in seen:
            seen.add(uid)
            seeds.append(item)
    for item in fused:
        uid = item.get("entity_id") or item.get("card_id") or item.get("id") or ""
        if uid and uid not in seen:
            seen.add(uid)
            seeds.append(item)
        if len(seeds) >= request.max_results:
            break

    log.info(
        "trace_seeds",
        trace_id=trace_id,
        total=len(seeds),
        seed_ids=[(s.get("card_id") or s.get("entity_id") or "?")[:30] for s in seeds[:10]],
        seed_entity_ids=[(s.get("entity_id") or "?")[:40] for s in seeds[:10]],
    )

    # Phase 1.5 — Apply trace feedback (exclude/demote previously-rejected entities)
    await _progress("Applying feedback", 3, total_steps)
    feedback = await _query_trace_feedback(request.query)
    if feedback["exact_exclude"]:
        before = len(seeds)
        seeds = [
            s for s in seeds
            if s.get("entity_id") not in feedback["exact_exclude"]
            or s.get("source") == "identifier"
        ]
        meta.feedback_excluded = before - len(seeds)
    if feedback["global_demote"]:
        priority = [s for s in seeds if s.get("entity_id") not in feedback["global_demote"]]
        demoted = [s for s in seeds if s.get("entity_id") in feedback["global_demote"]]
        meta.feedback_demoted = len(demoted)
        seeds = (priority + demoted)[:request.max_results]

    # Phase 2 — Expansion
    await _progress("Expanding results", 4, total_steps)
    all_cards, entity_map = await _expand_seeds(seeds, request.space_id, request.include_archived)
    meta.expansion_cards = len(all_cards)

    # Phase 2.5 — LLM relevance filter (remove false positives before clustering)
    await _progress("Analyzing connections", 5, total_steps)
    if request.enable_llm_filter:
        seeds, removed_count = await _llm_relevance_filter(
            request.query, seeds, all_cards,
            trace_id=trace_id, space_id=request.space_id,
            cancellable=_cancellable,
        )
        meta.seeds_filtered = removed_count
    else:
        removed_count = 0

    if removed_count > 0:
        # Remove cards whose entities are no longer backed by surviving seeds
        surviving_eids: set[str] = set()
        for s in seeds:
            eid = s.get("entity_id")
            if eid:
                surviving_eids.add(eid)
            cid = s.get("card_id")
            if cid:
                for c in all_cards:
                    if c.card_id == cid and c.entity_id:
                        surviving_eids.add(c.entity_id)
                        break
        # Keep cross-referenced entities (same subject_id)
        keep_subjects: set[str] = set()
        for eid in surviving_eids:
            parts = eid.split(":", 2)
            if len(parts) >= 3:
                keep_subjects.add(parts[2].lower())
        for c in all_cards:
            if c.entity_id:
                parts = c.entity_id.split(":", 2)
                if len(parts) >= 3 and parts[2].lower() in keep_subjects:
                    surviving_eids.add(c.entity_id)
        all_cards = [c for c in all_cards if c.entity_id in surviving_eids]

    # Phase 3 — Clustering (before capping, so small clusters aren't eliminated)
    await _progress("Building clusters", 6, total_steps)
    # Clustering is CPU-bound (union-find + chapter detection) — run in
    # executor so the event loop stays responsive for other API requests.
    clusters = await loop.run_in_executor(
        None, _build_clusters, all_cards, entity_map, seeds
    )

    # Cap cards per cluster to keep results manageable without dropping
    # entire clusters. Distribute max_results proportionally.
    if clusters:
        per_cluster = max(request.max_results // len(clusters), 5)
        for cluster in clusters:
            if len(cluster.timeline) > per_cluster:
                cluster.timeline = cluster.timeline[:per_cluster]
                cluster.status_summary.total_cards = len(cluster.timeline)

    meta.elapsed_ms = int((time.monotonic() - t0) * 1000)
    now = db_now()

    response = TraceResponse(
        trace_id=trace_id,
        query=request.query,
        clusters=clusters,
        search_metadata=meta,
        created_at=now,
        space_id=request.space_id,
    )

    # Persist trace to DB
    await _save_trace(response)

    # Announce completion over WS so a client whose HTTP request already aborted
    # (a rerun can outlast any timeout) can still recover the result by fetching
    # this trace_id. Broadcast AFTER _save_trace so any client that reacts by
    # calling GET /traces/{id} is guaranteed to find the persisted row.
    await publish({
        "type": "trace_complete",
        "trace_id": trace_id,
        "query": request.query,
        "cluster_count": len(response.clusters),
    })

    return response


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


async def _save_trace(response: TraceResponse) -> None:
    """Persist a trace to the database."""
    db = await get_db()

    card_ids = []
    chapters_json = []
    cluster_data = []
    for cluster in response.clusters:
        card_ids.extend(c.card_id for c in cluster.timeline)
        chapters_json.extend(ch.model_dump() for ch in cluster.chapters)
        cluster_data.append({
            "cluster_id": cluster.cluster_id,
            "primary_entity": cluster.primary_entity.model_dump(),
            "linked_entities": [e.model_dump() for e in cluster.linked_entities],
            "status_summary": cluster.status_summary.model_dump(),
        })

    # Upsert (not a plain INSERT) so a rerun — which reuses the existing trace_id
    # (see run_trace) — replaces the row IN PLACE, atomically, and only on success.
    # This is a single statement, so it's inherently atomic and needs no
    # db/sqlite.transaction() wrapper (that's for multi-statement invariants);
    # keeping it single-statement is precisely what makes rerun crash-safe.
    #   - created_at is deliberately NOT in DO UPDATE SET: the original stands so
    #     history ordering (ORDER BY created_at DESC) is stable and a rerun doesn't
    #     jump the row to the top. updated_at moves to the new db_now() value.
    #   - narrative/summary are cleared: both describe the OLD cluster set (per-cluster
    #     narratives live inside cluster_data and are already discarded with it, but
    #     these two top-level columns must be NULLed so _reconstruct_trace doesn't
    #     render a summary narrating cards that are no longer in the trace).
    await db.execute(
        """INSERT INTO traces (trace_id, query, created_at, updated_at, chapters,
                               cluster_data, card_ids, search_metadata, space_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(trace_id) DO UPDATE SET
               query           = excluded.query,
               updated_at      = excluded.updated_at,
               chapters        = excluded.chapters,
               cluster_data    = excluded.cluster_data,
               card_ids        = excluded.card_ids,
               search_metadata = excluded.search_metadata,
               space_id        = excluded.space_id,
               narrative       = NULL,
               summary         = NULL""",
        (
            response.trace_id,
            response.query,
            response.created_at,
            response.created_at,
            json.dumps(chapters_json),
            json.dumps(cluster_data),
            json.dumps(card_ids),
            response.search_metadata.model_dump_json(),
            response.space_id,
        ),
    )
    await db.commit()
