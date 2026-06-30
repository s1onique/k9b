"""Payload construction for OpenAI-compatible provider."""
from __future__ import annotations

from typing import Any

from .openai_compatible_provider_config import (
    _SYSTEM_INSTRUCTIONS,
    OpenAICompatibleProviderConfig,
)


def build_payload(
    prompt: str,
    config: OpenAICompatibleProviderConfig,
    *,
    system_instructions: str | None = None,
    max_tokens: int | None = None,
    response_format_json: bool = False,
) -> dict[str, Any]:
    """Build request payload for OpenAI-compatible chat completions API."""
    system = system_instructions if system_instructions is not None else _SYSTEM_INSTRUCTIONS
    payload: dict[str, Any] = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if response_format_json:
        payload["response_format"] = {"type": "json_object"}
    # Apply generation settings from config (only non-None values)
    if config.temperature is not None:
        payload["temperature"] = config.temperature
    if config.top_p is not None:
        payload["top_p"] = config.top_p
    if config.top_k is not None:
        payload["top_k"] = config.top_k
    if config.repeat_penalty is not None:
        payload["repeat_penalty"] = config.repeat_penalty
    if config.seed is not None:
        payload["seed"] = config.seed
    if config.stop is not None:
        payload["stop"] = list(config.stop)
    # Disable thinking mode for Qwen-based models
    payload["chat_template_kwargs"] = {
        "enable_thinking": config.enable_thinking
    }
    return payload


def build_request_headers(config: OpenAICompatibleProviderConfig) -> dict[str, str]:
    """Build HTTP headers for OpenAI-compatible request."""
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    return headers


__all__ = [
    "build_payload",
    "build_request_headers",
]
