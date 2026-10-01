# Copyright 2026 Aayush Chawla
# SPDX-License-Identifier: Apache-2.0

"""Tests for the LLMClient protocol (#12).

Covers: the Protocol accepts the real client structurally, a fake can be
injected via set_llm_client without monkeypatching module internals, and
LiteLLMClient.generate/stream delegate to llm_call/llm_call_streaming.
"""

from unittest.mock import AsyncMock, patch

import pytest

from laya.llm.base import LiteLLMClient, LLMClient, get_llm_client, set_llm_client
from laya.llm.client import LLMResponse, StreamEvent


class FakeLLMClient:
    """Minimal fake conforming to the LLMClient protocol."""

    def __init__(self, response: LLMResponse):
        self._response = response
        self.calls: list[dict] = []

    async def generate(self, role, messages, **kwargs) -> LLMResponse:
        self.calls.append({"role": role, "messages": messages, **kwargs})
        return self._response

    def stream(self, role, messages, **kwargs):
        async def _gen():
            yield StreamEvent(type="chunk", content="hi")
            yield StreamEvent(type="done")
        return _gen()


@pytest.fixture(autouse=True)
def _restore_default_client():
    """Each test gets a clean default client — set_llm_client is process-global."""
    original = get_llm_client()
    yield
    set_llm_client(original)


def test_litellm_client_is_runtime_checkable_as_protocol():
    assert isinstance(LiteLLMClient(), LLMClient)


def test_fake_client_is_runtime_checkable_as_protocol():
    assert isinstance(FakeLLMClient(LLMResponse(content="x", model="m", input_tokens=0, output_tokens=0, latency_ms=0)), LLMClient)


def test_default_client_is_litellm_client():
    assert isinstance(get_llm_client(), LiteLLMClient)


def test_set_llm_client_overrides_default():
    fake = FakeLLMClient(LLMResponse(content="stubbed", model="m", input_tokens=0, output_tokens=0, latency_ms=0))
    set_llm_client(fake)
    assert get_llm_client() is fake


@pytest.mark.asyncio
async def test_set_llm_client_lets_tests_inject_without_monkeypatching_callers():
    fake = FakeLLMClient(LLMResponse(content="stubbed", parsed={"ok": True}, model="m", input_tokens=0, output_tokens=0, latency_ms=0))
    set_llm_client(fake)

    response = await get_llm_client().generate(role="router", messages=[{"role": "user", "content": "hi"}])

    assert response.content == "stubbed"
    assert fake.calls == [{"role": "router", "messages": [{"role": "user", "content": "hi"}]}]


@pytest.mark.asyncio
async def test_litellm_client_generate_delegates_to_llm_call():
    expected = LLMResponse(content="ok", model="m", input_tokens=0, output_tokens=0, latency_ms=0)
    with patch("laya.llm.client.llm_call", new_callable=AsyncMock, return_value=expected) as mock_call:
        result = await LiteLLMClient().generate(
            role="router", messages=[{"role": "user", "content": "hi"}], temperature=0.5,
        )
    assert result is expected
    mock_call.assert_awaited_once()
    assert mock_call.await_args.kwargs["role"] == "router"
    assert mock_call.await_args.kwargs["temperature"] == 0.5


@pytest.mark.asyncio
async def test_litellm_client_stream_delegates_to_llm_call_streaming():
    async def _fake_stream(**kwargs):
        yield StreamEvent(type="chunk", content="hello")
        yield StreamEvent(type="done")

    with patch("laya.llm.client.llm_call_streaming", side_effect=_fake_stream) as mock_stream:
        events = [e async for e in LiteLLMClient().stream(role="chat", messages=[])]

    assert [e.type for e in events] == ["chunk", "done"]
    mock_stream.assert_called_once()
    assert mock_stream.call_args.kwargs["role"] == "chat"
