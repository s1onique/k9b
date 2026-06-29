"""OpenAI-compatible URL construction helpers.

This module provides URL normalization for OpenAI-compatible API endpoints,
supporting various provider base URL formats (OpenRouter, llama.cpp servers, etc.).
"""

from __future__ import annotations


def build_chat_completions_url(base_url: str) -> str:
    """Build a normalized chat completions URL from a base URL.

    Handles three forms of base URLs:
    - Provider API root: https://openrouter.ai/api -> https://openrouter.ai/api/v1/chat/completions
    - API version root: https://openrouter.ai/api/v1 -> https://openrouter.ai/api/v1/chat/completions
    - Full chat completions endpoint: https://openrouter.ai/api/v1/chat/completions -> https://openrouter.ai/api/v1/chat/completions

    This normalizes URLs to prevent duplicate /v1/v1/ paths when users configure
    the base URL with an SDK-style /v1 suffix while the provider also appends /v1/chat/completions.

    Args:
        base_url: The provider's base URL (may or may not include /v1 or /chat/completions)

    Returns:
        Normalized chat completions URL: {base}/v1/chat/completions
    """
    base = base_url.strip().rstrip("/")

    # Already has /chat/completions - return as-is
    if base.endswith("/chat/completions"):
        return base

    # Already has /v1 suffix - append just /chat/completions
    if base.endswith("/v1"):
        return f"{base}/chat/completions"

    # Provider API root - append /v1/chat/completions
    return f"{base}/v1/chat/completions"


__all__ = [
    "build_chat_completions_url",
]
