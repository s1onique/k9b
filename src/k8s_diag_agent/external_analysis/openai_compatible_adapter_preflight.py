"""Preflight helpers for llamacpp adapter.

This module extracts preflight check message building from openai_compatible_adapter.py,
providing focused helpers for building operator-grade diagnostic messages.
"""

from __future__ import annotations


def build_missing_base_url_message() -> str:
    """Build operator message for missing base URL configuration."""
    return (
        "Review enrichment is enabled but no OpenAI-compatible base URL is configured. "
        "Set K9B_EXTERNAL_ANALYSIS_BASE_URL, for example http://llm.k9b.svc.cluster.local:8080/v1, "
        "or disable review enrichment. Legacy LLAMA_CPP_BASE_URL is still accepted but deprecated."
    )


def build_missing_model_message() -> str:
    """Build operator message for missing model configuration."""
    return (
        "Review enrichment is enabled but no model is configured. "
        "Set K9B_EXTERNAL_ANALYSIS_MODEL to the model name, for example Qwen/Qwen2.5-Coder-7B-Instruct. "
        "Legacy LLAMA_CPP_MODEL is still accepted but deprecated."
    )


def build_config_error_message(error_msg: str) -> str:
    """Build operator message for general config error."""
    return (
        f"Review enrichment provider configuration failed: {error_msg}. "
        "Check K9B_EXTERNAL_ANALYSIS_BASE_URL and K9B_EXTERNAL_ANALYSIS_MODEL settings. "
        "Health run will continue without LLM enrichment."
    )


def parse_config_error_reason(error_msg: str) -> tuple[str, str]:
    """Parse config error message to determine specific reason and operator message.

    Returns:
        Tuple of (reason_code, operator_message)
    """
    if "K9B_EXTERNAL_ANALYSIS_BASE_URL" in error_msg or "base_url" in error_msg.lower():
        return "missing_base_url", build_missing_base_url_message()
    elif "K9B_EXTERNAL_ANALYSIS_MODEL" in error_msg or "model" in error_msg.lower():
        return "missing_model", build_missing_model_message()
    else:
        return "config_error", build_config_error_message(error_msg)


def build_provider_unavailable_message() -> str:
    """Build operator message when HTTP provider cannot be initialized."""
    return (
        "Review enrichment is enabled but the OpenAI-compatible provider could not be initialized. "
        "Check K9B_EXTERNAL_ANALYSIS_BASE_URL and ensure the model server is reachable. "
        "Health run will continue without LLM enrichment."
    )


def build_success_message(base_url: str, model: str) -> str:
    """Build operator message for successful provider configuration."""
    return f"OpenAI-compatible provider configured: {base_url} with model {model}."
