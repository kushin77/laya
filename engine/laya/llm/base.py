# Copyright 2026 Aayush Chawla
# SPDX-License-Identifier: Apache-2.0

"""LLMClient protocol (#12).

Pipeline stages previously imported the bare `llm_call`/`llm_call_streaming`
functions from `laya.llm.client` directly, which meant substituting a fake
client in tests required monkeypatching the imported name in every module
under test. This module defines the typed interface pipeline stages should
depend on instead, and a default concrete implementation backed by
`laya.llm.client`.

This mirrors the callback-injection pattern `pipeline/llm_hooks.py` already
uses to decouple `laya.llm.client` from the pipeline layer (#73): the
concrete implementation is constructed once and wired in from app startup
(see `laya.main`'s lifespan), rather than each module importing a global
directly.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Protocol, runtime_checkable

from laya.llm.client import DEFAULT_MAX_TOKENS, LLMResponse, StreamEvent


@runtime_checkable
class LLMClient(Protocol):
    """Typed interface for making LLM calls — the seam pipeline stages depend on."""

    async def generate(
        self,
        role: str,
        messages: list[dict[str, str]],
        response_schema: dict | None = None,
        event_id: str | None = None,
        card_id: str | None = None,
        step: str = "unknown",
        temperature: float = 0.0,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        num_retries: int = 3,
        space_id: str | None = None,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        """Make a single (non-streaming) LLM call. See `laya.llm.client.llm_call`."""
        ...

    def stream(
        self,
        role: str,
        messages: list[dict[str, str]],
        step: str = "chat",
        temperature: float = 0.3,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        space_id: str | None = None,
        tools: list[dict] | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Make a streaming LLM call. See `laya.llm.client.llm_call_streaming`."""
        ...


class LiteLLMClient:
    """Default LLMClient, delegating to the LiteLLM-backed functions in `laya.llm.client`."""

    async def generate(
        self,
        role: str,
        messages: list[dict[str, str]],
        response_schema: dict | None = None,
        event_id: str | None = None,
        card_id: str | None = None,
        step: str = "unknown",
        temperature: float = 0.0,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        num_retries: int = 3,
        space_id: str | None = None,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        from laya.llm.client import llm_call

        return await llm_call(
            role=role,
            messages=messages,
            response_schema=response_schema,
            event_id=event_id,
            card_id=card_id,
            step=step,
            temperature=temperature,
            max_tokens=max_tokens,
            num_retries=num_retries,
            space_id=space_id,
            tools=tools,
        )

    def stream(
        self,
        role: str,
        messages: list[dict[str, str]],
        step: str = "chat",
        temperature: float = 0.3,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        space_id: str | None = None,
        tools: list[dict] | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        from laya.llm.client import llm_call_streaming

        return llm_call_streaming(
            role=role,
            messages=messages,
            step=step,
            temperature=temperature,
            max_tokens=max_tokens,
            space_id=space_id,
            tools=tools,
        )


# Process-wide default, overridable via `set_llm_client` (e.g. from app startup,
# or a test fixture that wants a fake without monkeypatching module internals).
_client: LLMClient = LiteLLMClient()


def get_llm_client() -> LLMClient:
    """Return the process-wide LLMClient."""
    return _client


def set_llm_client(client: LLMClient) -> None:
    """Override the process-wide LLMClient. Called once from app startup."""
    global _client
    _client = client
