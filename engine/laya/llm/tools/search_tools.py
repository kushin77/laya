# Copyright 2026 Aayush Chawla
# SPDX-License-Identifier: Apache-2.0

"""Semantic search tool implementation."""

from __future__ import annotations

from typing import Any

from laya.db.chromadb_store import memory_search
from laya.llm.tools.constants import (
    SEMANTIC_SEARCH_DEFAULT,
    SEMANTIC_SEARCH_MAX,
    parse_iso_to_timestamp,
)


async def semantic_search(
    query: str,
    n_results: int = SEMANTIC_SEARCH_DEFAULT,
    space_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    """Perform semantic search across all stored content."""
    filters: list[dict[str, Any]] = []
    if space_id:
        filters.append({"space_id": space_id})

    date_from_ts = parse_iso_to_timestamp(date_from)
    date_to_ts = parse_iso_to_timestamp(date_to, end_of_day=True)
    if date_from_ts is not None:
        filters.append({"timestamp": {"$gte": date_from_ts}})
    if date_to_ts is not None:
        filters.append({"timestamp": {"$lte": date_to_ts}})

    where: dict[str, Any] | None = None
    if len(filters) == 1:
        where = filters[0]
    elif len(filters) > 1:
        where = {"$and": filters}

    results = await memory_search(query, n_results=min(n_results, SEMANTIC_SEARCH_MAX), where=where)

    return {
        "results": [
            {
                "id": r["id"],
                "content": r["document"][:500],
                "content_type": r["metadata"].get("content_type", "unknown"),
                "source_platform": r["metadata"].get("source_platform", ""),
                "distance": r.get("distance"),
            }
            for r in results
        ],
        "count": len(results),
    }


def get_read_definitions() -> list[dict]:
    """OpenAI function-calling schemas for the cross-content search tools."""
    return [
        {
            "type": "function",
            "function": {
                "name": "semantic_search",
                "description": (
                    "Perform a semantic (meaning-based) search across all stored content. "
                    "Use this when keyword search isn't enough and you need conceptual matching."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language search query.",
                        },
                        "n_results": {
                            "type": "integer",
                            "description": "Number of results (default 10).",
                            "default": 10,
                        },
                        "date_from": {
                            "type": "string",
                            "description": (
                                "ISO 8601 date or datetime for the start of a time range "
                                "filter (inclusive). Omit if no temporal intent."
                            ),
                        },
                        "date_to": {
                            "type": "string",
                            "description": (
                                "ISO 8601 date or datetime for the end of a time range "
                                "filter (inclusive). Omit if no temporal intent."
                            ),
                        },
                    },
                    "required": ["query"],
                },
            },
        },
    ]
