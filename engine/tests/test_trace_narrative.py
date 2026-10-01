# Copyright 2026 Aayush Chawla
# SPDX-License-Identifier: Apache-2.0

"""Tests that trace narrative/summary generation goes through the injected
LLMClient (#12) rather than calling llm_call_streaming directly, now that
pipeline/trace.py has been split (#8).
"""

import json

import pytest

from laya.llm.base import get_llm_client, set_llm_client
from laya.llm.client import StreamEvent
from laya.models.trace import (
    SearchMetadata,
    TraceCluster,
    TraceEntity,
    TraceStatusSummary,
)
from laya.pipeline.trace_narrative import stream_trace_summary


class FakeStreamingClient:
    """Fake LLMClient whose stream() yields fixed chunks, for asserting on wiring."""

    def __init__(self, chunks: list[str]):
        self._chunks = chunks
        self.stream_calls: list[dict] = []

    async def generate(self, *args, **kwargs):
        raise AssertionError("stream_trace_summary should not call generate()")

    def stream(self, role, messages, **kwargs):
        self.stream_calls.append({"role": role, "messages": messages, **kwargs})

        async def _gen():
            for chunk in self._chunks:
                yield StreamEvent(type="chunk", content=chunk)
            yield StreamEvent(type="done")
        return _gen()


@pytest.fixture(autouse=True)
def _restore_default_client():
    original = get_llm_client()
    yield
    set_llm_client(original)


async def _seed_trace_row(db, trace_id="trace_narr001"):
    await db.execute(
        """INSERT INTO traces (trace_id, query, created_at, updated_at, chapters,
                               cluster_data, card_ids, search_metadata, space_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            trace_id,
            "nexus related changes",
            "2026-01-01T00:00:00.000000Z",
            "2026-01-01T00:00:00.000000Z",
            json.dumps([]),
            json.dumps([]),
            json.dumps([]),
            SearchMetadata().model_dump_json(),
            None,
        ),
    )
    await db.commit()


def _make_cluster() -> TraceCluster:
    return TraceCluster(
        cluster_id="cluster_abc123",
        primary_entity=TraceEntity(entity_id="jira:ticket:BUG-1", title="BUG-1", platform="jira"),
        status_summary=TraceStatusSummary(
            current_state="pending",
            platforms_involved=["jira"],
            total_cards=1,
            date_range={"from": "2026-01-01", "to": "2026-01-01"},
            pending_actions=1,
        ),
    )


@pytest.mark.asyncio
async def test_stream_trace_summary_uses_injected_llm_client(db):
    """stream_trace_summary must resolve its model via get_llm_client().stream(),
    not a bare llm_call_streaming import — the whole point of #12's seam."""
    await _seed_trace_row(db)
    fake = FakeStreamingClient(["Hello ", "world"])
    set_llm_client(fake)

    await stream_trace_summary("trace_narr001", "nexus related changes", [_make_cluster()])

    assert len(fake.stream_calls) == 1
    assert fake.stream_calls[0]["role"] == "trace"

    rows = await db.execute_fetchall(
        "SELECT summary FROM traces WHERE trace_id = ?", ("trace_narr001",)
    )
    assert rows[0]["summary"] == "Hello world"
