# Copyright 2026 Aayush Chawla
# SPDX-License-Identifier: Apache-2.0

"""Minimal async pub/sub bus decoupling the reasoning/pipeline layers from
the API transport layer (see issues #5, #15)."""

from typing import Any, Awaitable, Callable

Handler = Callable[[dict[str, Any]], Awaitable[None]]

_subscribers: list[Handler] = []


def subscribe(handler: Handler) -> None:
    """Register a handler to receive every published event."""
    _subscribers.append(handler)


async def publish(message: dict[str, Any]) -> None:
    """Publish an event to all subscribed handlers."""
    for handler in _subscribers:
        await handler(message)
