# Copyright 2026 Aayush Chawla
# SPDX-License-Identifier: Apache-2.0

"""Trace pipeline — LLM narrative synthesis, streamed over WebSocket
(split out of pipeline/trace.py, #8).

Split boundary: everything here takes clusters built by trace_clustering.py
and generates prose over them — a per-cluster narrative, or an overall
summary across all clusters — streaming chunks out via `laya.events.publish`
and persisting the final text. Uses the injected LLMClient (#12) rather than
importing `llm_call_streaming` directly.
"""

from __future__ import annotations

import asyncio
import json

import structlog

from laya.config import get_self_user
from laya.db.sqlite import get_db
from laya.db.timeutil import db_now
from laya.events import publish
from laya.llm.base import get_llm_client
from laya.llm.client import DEFAULT_MAX_TOKENS
from laya.llm.prompts.trace import build_narrative_messages, build_summary_messages
from laya.models.trace import TraceCluster
from laya.pipeline.queue import _get_semaphore

log = structlog.get_logger()


async def _update_cluster_narrative(
    trace_id: str, cluster_id: str, narrative: str
) -> None:
    """Persist a narrative for a specific cluster inside the trace's cluster_data JSON."""
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT cluster_data FROM traces WHERE trace_id = ?", (trace_id,)
    )
    if not rows:
        return

    cluster_data = json.loads(rows[0]["cluster_data"]) if rows[0]["cluster_data"] else []
    for cdata in cluster_data:
        if cdata.get("cluster_id") == cluster_id:
            cdata["narrative"] = narrative
            break

    await db.execute(
        "UPDATE traces SET cluster_data = ?, updated_at = ? WHERE trace_id = ?",
        (json.dumps(cluster_data), db_now(), trace_id),
    )
    await db.commit()


async def _stream_cluster_narrative(
    trace_id: str, cluster: TraceCluster, space_id: str | None = None
) -> None:
    """Generate and stream a narrative for a single cluster via WebSocket.

    Acquires the shared pipeline semaphore so trace narratives respect
    the same concurrency limit as feed card generation.
    """
    sem = _get_semaphore()
    async with sem:
        await _stream_cluster_narrative_inner(trace_id, cluster, space_id=space_id)


async def _stream_cluster_narrative_inner(
    trace_id: str, cluster: TraceCluster, space_id: str | None = None
) -> None:
    """Inner narrative generation (called under semaphore)."""
    cluster_id = cluster.cluster_id
    full_narrative = ""
    try:
        messages = build_narrative_messages([cluster], user_identity=get_self_user())

        await publish({
            "type": "trace_narrative_start",
            "trace_id": trace_id,
            "cluster_id": cluster_id,
        })

        async for event in get_llm_client().stream(
            role="trace",
            messages=messages,
            step="trace",
            temperature=0.3,
            max_tokens=DEFAULT_MAX_TOKENS,
            space_id=space_id,
        ):
            if event.type == "chunk" and event.content:
                full_narrative += event.content
                await publish({
                    "type": "trace_narrative_chunk",
                    "trace_id": trace_id,
                    "cluster_id": cluster_id,
                    "content": event.content,
                })
            elif event.type == "error":
                log.error(
                    "trace_narrative_error",
                    trace_id=trace_id, cluster_id=cluster_id, error=event.content,
                )
                break

        # Persist per-cluster narrative
        await _update_cluster_narrative(trace_id, cluster_id, full_narrative)
    except Exception as e:
        log.error(
            "trace_narrative_inner_error",
            trace_id=trace_id, cluster_id=cluster_id, error=str(e),
        )
    finally:
        await publish({
            "type": "trace_narrative_done",
            "trace_id": trace_id,
            "cluster_id": cluster_id,
            "narrative": full_narrative,
        })

    log.info(
        "trace_narrative_complete",
        trace_id=trace_id, cluster_id=cluster_id, length=len(full_narrative),
    )


async def stream_trace_narrative(
    trace_id: str, clusters: list[TraceCluster], space_id: str | None = None
) -> None:
    """Generate and stream narratives for each cluster independently."""
    try:
        # Run narratives for all clusters concurrently
        await asyncio.gather(
            *(_stream_cluster_narrative(trace_id, c, space_id=space_id) for c in clusters)
        )
    except Exception as e:
        log.error("trace_narrative_failed", trace_id=trace_id, error=str(e))


async def stream_trace_summary(
    trace_id: str, query: str, clusters: list[TraceCluster],
    space_id: str | None = None,
) -> None:
    """Generate and stream an overall summary across all clusters via WebSocket."""
    sem = _get_semaphore()
    async with sem:
        full_text = ""
        summary_id = "__summary__"
        try:
            messages = build_summary_messages(query, clusters, user_identity=get_self_user())

            await publish({
                "type": "trace_narrative_start",
                "trace_id": trace_id,
                "cluster_id": summary_id,
            })

            async for event in get_llm_client().stream(
                role="trace",
                messages=messages,
                step="trace_summary",
                temperature=0.3,
                max_tokens=DEFAULT_MAX_TOKENS,
                space_id=space_id,
            ):
                if event.type == "chunk" and event.content:
                    full_text += event.content
                    await publish({
                        "type": "trace_narrative_chunk",
                        "trace_id": trace_id,
                        "cluster_id": summary_id,
                        "content": event.content,
                    })
                elif event.type == "error":
                    log.error("trace_summary_error", trace_id=trace_id, error=event.content)
                    break

            # Persist summary to the trace record
            db = await get_db()
            await db.execute(
                "UPDATE traces SET summary = ? WHERE trace_id = ?",
                (full_text, trace_id),
            )
            await db.commit()

        except Exception as e:
            log.error("trace_summary_failed", trace_id=trace_id, error=str(e))
        finally:
            await publish({
                "type": "trace_narrative_done",
                "trace_id": trace_id,
                "cluster_id": summary_id,
                "narrative": full_text,
            })

        log.info("trace_summary_complete", trace_id=trace_id, length=len(full_text))
