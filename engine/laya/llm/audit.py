# Copyright 2026 Aayush Chawla
# SPDX-License-Identifier: Apache-2.0

"""Audit-log writes for LLM calls. Split out of llm/client.py (#21) — many
callers across api/, pipeline/, and llm/tools/ import this directly.
"""

import json
import uuid

import structlog

from laya.db.sqlite import get_db

log = structlog.get_logger()


async def log_to_audit(
    event_id: str | None,
    card_id: str | None,
    step: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    success: bool,
    error: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Write an entry to the audit_log table. Never raises."""
    try:
        db = await get_db()
        await db.execute(
            """INSERT INTO audit_log
               (log_id, event_id, card_id, step, model_used, input_tokens,
                output_tokens, latency_ms, success, error, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                f"audit_{uuid.uuid4().hex[:12]}",
                event_id,
                card_id,
                step,
                model,
                input_tokens,
                output_tokens,
                latency_ms,
                success,
                error,
                json.dumps(metadata) if metadata else None,
            ),
        )
        await db.commit()
    except Exception as e:
        log.warning("audit_log_failed", error=str(e))
