# Copyright 2026 Aayush Chawla
# SPDX-License-Identifier: Apache-2.0

"""Trace pipeline — discovery signals, RRF fusion, and the post-retrieval
LLM relevance filter (split out of pipeline/trace.py, #8).

Split boundary: everything here turns a query into a *ranked seed list* —
SQLite/ChromaDB discovery signals, feedback-based exclusion, and the
JSON-schema-validated LLM pass that drops false-positive seeds before
expansion/clustering. Card expansion and clustering are trace_clustering.py;
narrative generation is trace_narrative.py; trace.py orchestrates all three.
"""

from __future__ import annotations

import re

import structlog

from laya.db.chromadb_store import memory_search
from laya.db.sqlite import get_db
from laya.llm.base import get_llm_client
from laya.llm.client import DEFAULT_MAX_TOKENS
from laya.llm.prompts.trace_filter import (
    RELEVANCE_FILTER_SCHEMA,
    build_relevance_filter_messages,
)
from laya.models.card import CardResponse
from laya.retrieval import extract_keywords, fts_or_like

log = structlog.get_logger()

# Regex to detect identifier patterns like "PR 540", "PR-540", "PR#540",
# LAYA"-986", "BUG-123", "ISSUE 42", etc.
_IDENTIFIER_RE = re.compile(
    r"([A-Za-z]{1,10})[\s\-#]?(\d{1,6})",
)


# ---------------------------------------------------------------------------
# Pre-retrieval feedback & post-retrieval relevance filter
# ---------------------------------------------------------------------------


async def _query_trace_feedback(query: str) -> dict:
    """Query past cluster-removal feedback to exclude/demote entities.

    Returns:
        {"exact_exclude": set[str], "global_demote": set[str]}
    """
    db = await get_db()
    exact_exclude: set[str] = set()
    global_demote: set[str] = set()

    # Exact: entities net-removed for this specific query
    rows = await db.execute_fetchall(
        """SELECT entity_id
           FROM trace_feedback WHERE query = ?
           GROUP BY entity_id
           HAVING SUM(CASE WHEN action = 'removed' THEN 1 ELSE -1 END) > 0""",
        (query,),
    )
    for row in rows:
        exact_exclude.add(row["entity_id"])

    # Global: entities removed across 3+ different queries
    rows = await db.execute_fetchall(
        """SELECT entity_id
           FROM trace_feedback WHERE action = 'removed'
           GROUP BY entity_id
           HAVING COUNT(DISTINCT query) >= 3""",
    )
    for row in rows:
        global_demote.add(row["entity_id"])

    return {"exact_exclude": exact_exclude, "global_demote": global_demote}


async def _llm_relevance_filter(
    query: str,
    seeds: list[dict],
    all_cards: list[CardResponse],
    trace_id: str | None = None,
    space_id: str | None = None,
    cancellable=None,
) -> tuple[list[dict], int]:
    """Batch LLM call to judge whether each non-identifier seed is relevant.

    `cancellable` is an optional `async def (coro, trace_id) -> result` racer —
    trace.py passes its own cancellation-aware wrapper so this module doesn't
    need to own the cancel-event registry (that stays in trace.py, the
    orchestrator). Without one, the coroutine is simply awaited.

    Returns (filtered_seeds, count_removed). Fails open on error.
    """
    # Identifier matches are always kept — they're exact and reliable
    id_seeds = [s for s in seeds if s.get("source") == "identifier"]
    other_seeds = [s for s in seeds if s.get("source") != "identifier"]

    if not other_seeds:
        return seeds, 0

    # Build card lookup for quick access
    card_by_id: dict[str, CardResponse] = {}
    for c in all_cards:
        card_by_id[c.card_id] = c

    # Build candidates with content for LLM
    candidates: list[dict] = []
    seed_index_map: dict[int, dict] = {}  # seed_index -> seed dict
    for i, seed in enumerate(other_seeds):
        card_id = seed.get("card_id") or seed.get("id")
        card = card_by_id.get(card_id) if card_id else None
        # If no card found by card_id, try matching via entity_id
        if not card and seed.get("entity_id"):
            for c in all_cards:
                if c.entity_id == seed["entity_id"]:
                    card = c
                    break
        candidates.append({
            "seed_index": i,
            "header": card.header if card else seed.get("id", "unknown"),
            "summary": card.summary if card else "",
        })
        seed_index_map[i] = seed

    try:
        messages = build_relevance_filter_messages(query, candidates)
        llm_coro = get_llm_client().generate(
            role="router",
            messages=messages,
            response_schema=RELEVANCE_FILTER_SCHEMA,
            step="trace_filter",
            temperature=0.0,
            max_tokens=DEFAULT_MAX_TOKENS,
            space_id=space_id,
        )
        # Race the LLM call against the cancel event so abort is near-instant
        response = await (cancellable(llm_coro, trace_id) if cancellable and trace_id else llm_coro)

        if not response.parsed or "judgments" not in response.parsed:
            log.warning("trace_filter_no_judgments", trace_id=trace_id)
            return seeds, 0

        # Collect relevant seed indices
        relevant_indices: set[int] = set()
        for j in response.parsed["judgments"]:
            if j.get("relevant"):
                relevant_indices.add(j["seed_index"])
            else:
                log.debug(
                    "trace_filter_removed",
                    seed_index=j["seed_index"],
                    reason=j.get("reason", ""),
                    header=candidates[j["seed_index"]]["header"][:60]
                    if j["seed_index"] < len(candidates) else "?",
                )

        # Build filtered list: all identifier seeds + relevant non-identifier seeds
        filtered = list(id_seeds)
        for i, seed in enumerate(other_seeds):
            if i in relevant_indices:
                filtered.append(seed)

        removed = len(seeds) - len(filtered)
        log.info("trace_filter_complete", trace_id=trace_id, kept=len(filtered), removed=removed)
        return filtered, removed

    except Exception as e:
        log.warning("trace_filter_failed", trace_id=trace_id, error=str(e))
        return seeds, 0


# ---------------------------------------------------------------------------
# Phase 1 — Discovery signals
# ---------------------------------------------------------------------------


async def _identifier_search(query: str, space_id: str | None, n: int) -> list[dict]:
    """Direct identifier lookup for patterns like 'PR 540', 'LAYA-986', etc.

    Generates common variants (PR-540, PR #540, PR-540, #540) and searches
    source_ref, entity_id, and header with exact substring matching.
    This is the highest-signal search — if it finds matches, they're almost
    certainly what the user is looking for.
    """
    matches = _IDENTIFIER_RE.findall(query)
    if not matches:
        return []

    db = await get_db()
    all_results: list[dict] = []

    for prefix, number in matches:
        # Generate common identifier variants
        variants = [
            f"{prefix}-{number}",    # PR-540, LAYA-986
            f"{prefix} #{number}",   # PR #540
            f"{prefix}#{number}",    # PR#540
            f"#{number}",            # #540
            f"{prefix} {number}",    # PR 540
        ]
        # Also uppercase variant
        up = prefix.upper()
        if up != prefix:
            variants.extend([
                f"{up}-{number}",
                f"{up} #{number}",
                f"{up}#{number}",
            ])

        conditions: list[str] = []
        params: list[str] = []
        for v in variants:
            conditions.append(
                "(c.source_ref LIKE ? OR c.entity_id LIKE ? OR c.header LIKE ?)"
            )
            params.extend([f"%{v}%"] * 3)

        where = " OR ".join(conditions)
        extra = ""
        if space_id:
            extra = " AND c.space_id = ?"
            params.append(space_id)
        params.append(str(n))

        rows = await db.execute_fetchall(
            f"""SELECT c.card_id, c.entity_id, c.source_ref, c.header
                FROM action_cards c
                WHERE ({where}){extra}
                ORDER BY c.created_at DESC LIMIT ?""",
            params,
        )
        for row in rows:
            all_results.append({
                "id": row["card_id"],
                "card_id": row["card_id"],
                "entity_id": row["entity_id"] or "",
                "source": "identifier",
            })

    return all_results[:n]


async def _semantic_search(query: str, space_id: str | None, n: int) -> list[dict]:
    """ChromaDB semantic search on card embeddings."""
    where = {"space_id": space_id} if space_id else None
    results = await memory_search(query, n_results=n, where=where, max_distance=0.65)
    return [
        {
            "id": r["metadata"].get("card_id", r["id"]),
            "card_id": r["metadata"].get("card_id"),
            # Real grouping key, not the entity_refs CSV that used to sit here and
            # broke dedup + feedback exclusion for semantic seeds (review §2 — P4-4).
            # Pre-fix embeds lack this key and fall back to "" (still better than a
            # wrong value); new embeds carry it (see emit._embed_card metadata).
            "entity_id": r["metadata"].get("entity_id", ""),
            "source": "semantic",
            "distance": r.get("distance", 1.0),
        }
        for r in results
    ]


async def _card_text_search(
    query: str, space_id: str | None, n: int, include_archived: bool = True
) -> list[dict]:
    """SQLite phrase-match search — matches the full query as a substring."""
    db = await get_db()
    phrase = query.strip()
    if len(phrase) < 2:
        return []

    fields = ["c.header", "c.summary", "c.source_ref", "c.entity_id", "c.source_url"]
    condition = " OR ".join(f"{f} LIKE ?" for f in fields)
    params: list[str] = [f"%{phrase}%"] * len(fields)

    extra = ""
    if space_id:
        extra += " AND c.space_id = ?"
        params.append(space_id)
    if not include_archived:
        extra += " AND c.status != 'archived'"

    # Boost: phrase in header/source_ref ranks higher
    boost = "(CASE WHEN c.header LIKE ? OR c.source_ref LIKE ? THEN 1 ELSE 0 END)"
    boost_params = [f"%{phrase}%"] * 2

    all_params = boost_params + params + [str(n)]

    rows = await db.execute_fetchall(
        f"""SELECT c.card_id, c.entity_id, c.source_ref, c.header, c.priority,
                   ({boost}) AS relevance
            FROM action_cards c
            WHERE ({condition}){extra}
            ORDER BY relevance DESC, c.created_at DESC LIMIT ?""",
        all_params,
    )
    return [
        {
            "id": row["card_id"],
            "card_id": row["card_id"],
            "entity_id": row["entity_id"] or "",
            "source": "text",
        }
        for row in rows
    ]


async def _card_fuzzy_search(
    query: str, space_id: str | None, n: int, include_archived: bool = True
) -> list[dict]:
    """SQLite keyword-split search — each keyword must appear somewhere (broad matching)."""
    db = await get_db()
    keywords = extract_keywords(query, min_len=2)
    if not keywords:
        return []

    # Each keyword must match at least one searchable field (AND across keywords)
    conditions: list[str] = []
    params: list[str] = []
    for kw in keywords[:8]:
        conditions.append(
            "(c.header LIKE ? OR c.summary LIKE ? OR c.source_ref LIKE ? "
            "OR c.entity_id LIKE ? OR c.source_url LIKE ?)"
        )
        params.extend([f"%{kw}%"] * 5)

    where = " AND ".join(conditions)
    extra = ""
    if space_id:
        extra += " AND c.space_id = ?"
        params.append(space_id)
    if not include_archived:
        extra += " AND c.status != 'archived'"

    # Build exact-match boost: cards where keywords appear in header/source_ref
    # score higher (sorted first) vs those matching only in summary/body
    boost_parts: list[str] = []
    boost_params: list[str] = []
    for kw in keywords[:8]:
        boost_parts.append("(CASE WHEN c.header LIKE ? OR c.source_ref LIKE ? THEN 1 ELSE 0 END)")
        boost_params.extend([f"%{kw}%"] * 2)

    boost_expr = " + ".join(boost_parts) if boost_parts else "0"

    all_params = boost_params + params + [str(n)]

    rows = await db.execute_fetchall(
        f"""SELECT c.card_id, c.entity_id, c.source_ref, c.header, c.priority,
                   ({boost_expr}) AS relevance
            FROM action_cards c
            WHERE ({where}){extra}
            ORDER BY relevance DESC, c.created_at DESC LIMIT ?""",
        all_params,
    )
    return [
        {
            "id": row["card_id"],
            "card_id": row["card_id"],
            "entity_id": row["entity_id"] or "",
            "source": "fuzzy",
        }
        for row in rows
    ]


async def _entity_table_search(query: str, n: int) -> list[dict]:
    """Search the entities table by canonical_name and platform_refs."""
    db = await get_db()
    keywords = extract_keywords(query, min_len=2)
    if not keywords:
        return []

    conditions: list[str] = []
    params: list[str] = []
    for kw in keywords[:5]:
        conditions.append("(canonical_name LIKE ? OR platform_refs LIKE ?)")
        params.extend([f"%{kw}%"] * 2)

    where = " OR ".join(conditions)
    params.append(str(n))

    rows = await db.execute_fetchall(
        f"""SELECT entity_id, entity_type, canonical_name, platform_refs, confidence
            FROM entities WHERE {where}
            ORDER BY confidence DESC LIMIT ?""",
        params,
    )
    return [
        {
            "id": row["entity_id"],
            "entity_id": row["entity_id"],
            "entity_type": row["entity_type"],
            "canonical_name": row["canonical_name"],
            "platform_refs": row["platform_refs"],
            "source": "entity",
        }
        for row in rows
    ]


async def _event_keyword_search(query: str, space_id: str | None, n: int) -> list[dict]:
    """Keyword search on events mapped back to cards — FTS5/BM25 or LIKE fallback.

    Only this trace signal moves to FTS: it is the clean analog of chat's event
    search. The card-side trace searches (_identifier_search, _card_text_search,
    _card_fuzzy_search) stay on LIKE — they match identifier columns (source_ref,
    entity_id, source_url) that are not in cards_fts and use bespoke boost/phrase
    semantics tuned for the RRF ensemble.
    """
    return await fts_or_like(
        query,
        min_len=2,
        max_terms=5,
        fts=lambda m: _event_keyword_search_fts(m, space_id, n),
        like=lambda q: _event_keyword_search_like(q, space_id, n),
        warn_event="trace_events_fts_failed_fallback_like",
    )


async def _event_keyword_search_fts(match: str, space_id: str | None, n: int) -> list[dict]:
    """BM25-ranked event search over events_fts, mapped back to cards."""
    db = await get_db()
    where = "events_fts MATCH ?"
    params: list = [match]
    if space_id:
        where += " AND e.space_id = ?"
        params.append(space_id)
    params.append(n)

    rows = await db.execute_fetchall(
        f"""SELECT c.card_id, c.entity_id
            FROM events_fts
            JOIN events e ON e.event_id = events_fts.event_id
            JOIN action_cards c ON c.event_id = e.event_id
            WHERE {where}
            ORDER BY bm25(events_fts) LIMIT ?""",
        params,
    )
    # A card can have several matching events; keep its best-ranked occurrence
    # (DISTINCT in SQL is incompatible with ORDER BY bm25 here, so dedup in Python).
    seen: set[str] = set()
    out: list[dict] = []
    for row in rows:
        cid = row["card_id"]
        if cid in seen:
            continue
        seen.add(cid)
        out.append({
            "id": cid,
            "card_id": cid,
            "entity_id": row["entity_id"] or "",
            "source": "event_keyword",
        })
    return out


async def _event_keyword_search_like(query: str, space_id: str | None, n: int) -> list[dict]:
    """SQLite LIKE keyword search on events (fallback when FTS5 is unavailable)."""
    db = await get_db()
    keywords = extract_keywords(query, min_len=2)
    if not keywords:
        return []

    conditions: list[str] = []
    params: list[str] = []
    for kw in keywords[:5]:
        conditions.append("(e.subject_title LIKE ? OR e.content_body LIKE ?)")
        params.extend([f"%{kw}%"] * 2)

    where = " OR ".join(conditions)
    extra = ""
    if space_id:
        extra = " AND e.space_id = ?"
        params.append(space_id)
    params.append(str(n))

    rows = await db.execute_fetchall(
        f"""SELECT DISTINCT c.card_id, c.entity_id
            FROM events e
            JOIN action_cards c ON c.event_id = e.event_id
            WHERE ({where}){extra}
            ORDER BY e.timestamp DESC LIMIT ?""",
        params,
    )
    return [
        {
            "id": row["card_id"],
            "card_id": row["card_id"],
            "entity_id": row["entity_id"] or "",
            "source": "event_keyword",
        }
        for row in rows
    ]
