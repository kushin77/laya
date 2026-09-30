# Copyright 2026 Aayush Chawla
# SPDX-License-Identifier: Apache-2.0

"""Wires the pipeline-layer callbacks into laya.llm.client (#14).

llm/client.py is pure infra and does not import laya.pipeline. Budget tracking,
agent rate-limit accounting, and the model-timeout/retry config it previously
imported directly are injected here instead, via `configure_pipeline_hooks`.
Called once at startup (see laya.main's lifespan).
"""

from laya.llm.client import LLMResponse, configure_pipeline_hooks
from laya.pipeline.agent_budget import evaluate_agent_budget, record_rate_limit
from laya.pipeline.budget import check_budget
from laya.pipeline.queue import get_llm_retries, get_model_timeout
from laya.tasks import create_task as create_tracked_task


def _on_complete(_result: LLMResponse) -> None:
    """Fire-and-forget budget check after every completed llm_call."""
    create_tracked_task(check_budget())


def _on_agent_rate_limit(agent_id: str, info: dict | None) -> None:
    """Persist the agent's native rate-limit signal (if any), then evaluate
    window limits — same fire-and-forget contract llm_call previously ran
    inline via direct pipeline.agent_budget imports."""

    async def _run() -> None:
        if info:
            await record_rate_limit(agent_id, info)
        await evaluate_agent_budget()

    create_tracked_task(_run())


def install() -> None:
    """Register this module's callbacks with laya.llm.client. Idempotent."""
    configure_pipeline_hooks(
        on_complete=_on_complete,
        on_agent_rate_limit=_on_agent_rate_limit,
        model_timeout=get_model_timeout,
        llm_retries=get_llm_retries,
    )
