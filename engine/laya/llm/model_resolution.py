# Copyright 2026 Aayush Chawla
# SPDX-License-Identifier: Apache-2.0

"""Model/provider resolution for LLM calls: role→model lookup, space overrides,
custom-provider (LMStudio/Ollama/OpenAI-compatible) resolution, and the
context-window-safe max_output_tokens ceiling.

Split out of llm/client.py (#21).
"""

from typing import Any

from laya.config import load_settings

# ── max_tokens context-window safety ─────────────────────────────────────
# The lenient DEFAULT_MAX_TOKENS (65536, defined in llm/client.py) is deliberately
# high so structured output never truncates. But strict servers 400 when it exceeds
# what they can serve: vLLM rejects `prompt + max_tokens > max_model_len`;
# OpenAI/Anthropic reject `max_tokens` above the model's max output (e.g.
# 65536*2=131072 from the truncation-retry exceeds even Opus's 128K cap). Local
# servers (LMStudio/Ollama) clamp silently and don't need this. We clamp ourselves
# so the same value is safe everywhere.
_OUTPUT_MARGIN = 512   # headroom left below the context window for the prompt estimate
_MIN_OUTPUT = 512      # never clamp output below this, even on a near-full context


async def _get_space_model(role: str, space_id: str) -> str | None:
    """Look up a space-specific model override for the given role.

    Returns None if the space has no override for this role.
    """
    import sqlite3

    from laya.db.sqlite import get_db

    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            f"SELECT {role}_model FROM spaces WHERE space_id = ?",
            (space_id,),
        )
    except sqlite3.OperationalError:
        # Role doesn't have a per-space column (e.g. group_summary)
        return None
    if rows and rows[0][f"{role}_model"]:
        return rows[0][f"{role}_model"]
    return None


async def _get_space_api_key(provider: str, space_id: str) -> str | None:
    """Look up a space-specific API key for the given provider.

    Returns None if the space has no key override for this provider.
    """
    from laya.db.sqlite import get_db
    from laya.security.keychain import get_space_api_key

    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT key_ref FROM space_api_keys WHERE space_id = ? AND provider = ?",
        (space_id, provider),
    )
    if rows:
        return get_space_api_key(rows[0]["key_ref"])
    return None


def _get_model_for_role(role: str) -> str:
    """Look up the configured model for a given role (router, stager, chat).

    Adds provider prefix if not already present.
    Roles that share a model with another role (e.g. group_summary → router)
    fall back to that role's model before the global default.
    """
    _ROLE_FALLBACKS = {
        "group_summary": "router",
    }

    settings = load_settings()
    models = settings.get("models", {})
    model_name = models.get(role)

    if not model_name and role in _ROLE_FALLBACKS:
        model_name = models.get(_ROLE_FALLBACKS[role])

    if not model_name:
        model_name = "claude-haiku-4-5"

    if "/" in model_name:
        return model_name

    return _add_provider_prefix(model_name)


def _add_provider_prefix(model_name: str) -> str:
    """Add provider prefix to a model name if not already present."""
    if "/" in model_name:
        return model_name
    if model_name.startswith("claude"):
        return f"anthropic/{model_name}"
    elif model_name.startswith(("gpt", "o1", "o3", "o4")):
        return f"openai/{model_name}"
    elif model_name.startswith("gemini"):
        return f"gemini/{model_name}"
    return model_name


def _resolve_custom_provider(model: str) -> tuple[str, dict[str, Any]] | None:
    """Check if a model string references a custom provider.

    Custom provider models use format: {provider_id}/{model_name}
    e.g., "lmstudio-local/qwen2.5-7b-instruct"

    Returns (litellm_model_string, extra_kwargs) or None if not a custom provider.
    """
    if "/" not in model:
        return None

    prefix = model.split("/")[0]

    # Skip known cloud provider prefixes
    if prefix in ("anthropic", "openai", "gemini", "openrouter", "ollama"):
        return None

    from laya.llm.providers import get_custom_provider, _get_provider_api_key

    provider = get_custom_provider(prefix)
    if not provider:
        return None

    model_name = model.split("/", 1)[1]
    ptype = provider.get("provider_type", "openai_compatible")
    base_url = provider["base_url"].rstrip("/")

    extra: dict[str, Any] = {
        "timeout": float(provider.get("default_timeout", 120)),
    }

    if ptype == "ollama":
        litellm_model = f"ollama/{model_name}"
        extra["api_base"] = base_url
    else:
        # Both lmstudio and openai_compatible use OpenAI-compat endpoint
        litellm_model = f"openai/{model_name}"
        extra["api_base"] = f"{base_url}/v1"

    # API key from keychain (optional for local providers)
    api_key = _get_provider_api_key(provider)
    if api_key:
        extra["api_key"] = api_key
    else:
        extra["api_key"] = "not-needed"  # LiteLLM requires a non-empty value

    return litellm_model, extra


def _get_custom_provider_meta(model: str) -> dict | None:
    """Get capability metadata for a custom provider model."""
    if "/" not in model:
        return None
    prefix = model.split("/")[0]
    if prefix in ("anthropic", "openai", "gemini", "openrouter", "ollama"):
        return None
    from laya.llm.providers import get_custom_provider

    provider = get_custom_provider(prefix)
    if not provider:
        return None
    ptype = provider.get("provider_type", "openai_compatible")
    caps = provider.get("capabilities_override", {})
    return {
        "provider_type": ptype,
        "supports_structured_output": caps.get("supports_structured_output", ptype == "lmstudio"),
        "supports_tool_calling": caps.get("supports_tool_calling", ptype == "lmstudio"),
        # Whether this provider may serve reasoning/"thinking" models (Qwen3, DeepSeek-R1,
        # etc.). When true we disable thinking for structured-output calls — see llm_call.
        "supports_reasoning": caps.get("supports_reasoning", ptype == "lmstudio"),
    }


def _estimate_prompt_tokens(messages: list[dict], model: str) -> int:
    """Best-effort prompt token count for context-window math. Prefers LiteLLM's
    tokenizer; falls back to the chars/4 heuristic also used in llm_call_streaming."""
    try:
        import litellm

        return int(litellm.token_counter(model=model, messages=messages))
    except Exception:
        return sum(len(str(m.get("content", ""))) for m in messages) // 4


async def _resolve_max_output_ceiling(
    litellm_model: str,
    original_model: str,
    is_custom: bool,
    messages: list[dict],
) -> int | None:
    """Max output tokens this model/server will accept, or None when it can't be
    determined (then we don't clamp and rely on the server's own behavior)."""
    # Cloud models LiteLLM knows about: cap at the model's max OUTPUT tokens.
    if not is_custom:
        try:
            import litellm

            info = litellm.get_model_info(litellm_model) or {}
            out = info.get("max_output_tokens") or info.get("max_tokens")
            return out if isinstance(out, int) and out > 0 else None
        except Exception:
            return None

    # Custom/local providers: cap at (discovered context window − prompt estimate).
    # Populated for LMStudio (native API) and vLLM (max_model_len); None elsewhere.
    try:
        from laya.llm.providers import discover_models_cached, get_custom_provider

        provider = get_custom_provider(original_model.split("/")[0])
        if not provider:
            return None
        models = await discover_models_cached(provider)
        window = next(
            (m.max_context_length for m in models
             if m.key == original_model and m.max_context_length),
            None,
        )
        if not window:
            return None
        prompt_est = _estimate_prompt_tokens(messages, litellm_model)
        return max(window - prompt_est - _OUTPUT_MARGIN, _MIN_OUTPUT)
    except Exception:
        return None
