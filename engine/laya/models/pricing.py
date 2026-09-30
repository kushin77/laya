# Copyright 2026 Aayush Chawla
# SPDX-License-Identifier: Apache-2.0

"""Shared LLM pricing table — used by both the dashboard API and pipeline budget enforcement."""

from __future__ import annotations

# LLM pricing per 1M tokens (input, output) in USD
MODEL_PRICING: dict[str, dict[str, float]] = {
    "anthropic/claude-haiku-4-5": {"input": 0.80, "output": 4.00},
    "anthropic/claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "anthropic/claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "anthropic/claude-sonnet-4-5-20250929": {"input": 3.00, "output": 15.00},
    "anthropic/claude-opus-4-6": {"input": 15.00, "output": 75.00},
    "openai/gpt-4o": {"input": 2.50, "output": 10.00},
    "openai/gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "google/gemini-2.0-flash": {"input": 0.10, "output": 0.40},
}
