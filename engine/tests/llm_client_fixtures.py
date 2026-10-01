# Copyright 2026 Aayush Chawla
# SPDX-License-Identifier: Apache-2.0

"""Shared test helper for injecting a fake LLMClient (#12).

Pipeline stages now call `get_llm_client().generate(...)` /
`get_llm_client().stream(...)` instead of importing `llm_call`/
`llm_call_streaming` directly, so tests swap in a fake client via
`set_llm_client()` instead of monkeypatching the module-qualified function
name. This mirrors the pattern in `test_trace_narrative.py`, generalized so
each call site doesn't need to redefine its own fake client class.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import AsyncMock

from laya.llm.base import get_llm_client, set_llm_client


class _FakeLLMClient:
    """Fake LLMClient delegating `generate`/`stream` to the given callables."""

    def __init__(self, generate=None, stream=None):
        self._generate = generate
        self._stream = stream

    async def generate(self, *args, **kwargs):
        if self._generate is None:
            raise AssertionError("generate() was not expected to be called")
        return await self._generate(*args, **kwargs)

    def stream(self, *args, **kwargs):
        if self._stream is None:
            raise AssertionError("stream() was not expected to be called")
        return self._stream(*args, **kwargs)


@contextmanager
def patch_llm_generate(new=None, return_value=None, side_effect=None):
    """Swap in a fake LLMClient whose `generate()` is `new`, or an AsyncMock.

    Drop-in replacement for
    ``patch("...llm_call", new_callable=AsyncMock, return_value=..., side_effect=...)``
    / ``patch.object(module, "llm_call", new=fake_llm_call)``. Yields the mock
    (or `new`) so existing assertions on the returned object keep working.
    """
    mock = new if new is not None else AsyncMock(return_value=return_value, side_effect=side_effect)
    original = get_llm_client()
    set_llm_client(_FakeLLMClient(generate=mock))
    try:
        yield mock
    finally:
        set_llm_client(original)


@contextmanager
def patch_llm_stream(new):
    """Swap in a fake LLMClient whose `stream()` is `new`.

    Drop-in replacement for ``patch("...llm_call_streaming", new=fake_stream)``.
    """
    original = get_llm_client()
    set_llm_client(_FakeLLMClient(stream=new))
    try:
        yield new
    finally:
        set_llm_client(original)
