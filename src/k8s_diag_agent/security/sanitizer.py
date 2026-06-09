"""Sanitization helpers for logs, prompts, and exported payloads."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

REDACTION_PLACEHOLDER = "<scrubbed>"
_SECRET_MANIFEST_RE = re.compile(r"kind\s*[:=]\s*Secret", re.IGNORECASE)
_PROMPT_SENSITIVE_PATTERNS = [
    # Catch standalone token variable names like KUBE_SECRET_TOKEN_abc123
    # This must come before token= patterns to catch full token references
    # NOTE: Does NOT use \b because underscore is a word character
    re.compile(r"(?i)TOKEN[A-Za-z0-9_]{5,}"),
    # Standard credential patterns
    re.compile(r"(?i)bearer\s+[A-Za-z0-9\-_.=]+"),
    re.compile(r"(?i)authorization\s*[:=]\s*\S+"),
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*\S+"),
    re.compile(r"(?i)client_secret\s*[:=]\s*\S+"),
    re.compile(r"(?i)access_token\s*[:=]\s*\S+"),
    re.compile(r"(?i)kubeconfig\b"),
    re.compile(r"(?i)token\s*[=:]\s*\S+"),
]
_SENSITIVE_KEYWORDS = (
    "token",
    "secret",
    "password",
    "auth",
    "authorization",
    "credential",
    "kubeconfig",
    "api_key",
    "apikey",
    "access_token",
    "client_secret",
)


# Known-safe token-count field names that should NOT be scrubbed.
# These are numeric budget/observability fields, not credentials.
_SAFE_TOKEN_COUNT_FIELDS = frozenset(
    (
        "max_tokens",
        "prompt_tokens",
        "prompt_tokens_estimate",
        "actual_prompt_tokens_estimate",
        "completion_tokens",
        "total_tokens",
        "token_count",
        "n_tokens",
        "timeout_seconds",
        "response_content_chars",
    )
)


def _is_safe_token_count_field(key: str) -> bool:
    """Check if key is a known-safe token-count or observability field."""
    if key in _SAFE_TOKEN_COUNT_FIELDS:
        return True
    # Allow fields ending in _tokens that are not credential-like
    if key.endswith("_tokens") and not key.startswith(("access_", "refresh_", "bearer_", "auth_")):
        return True
    # Allow fields containing tokens_estimate (prompt token estimation)
    if "tokens_estimate" in key:
        return True
    # Allow fields containing _max_tokens_ (e.g., openai_compatible_max_tokens_auto_drilldown)
    if "_max_tokens_" in key:
        return True
    # Allow fields ending with _max_tokens (e.g., openai_compatible_max_tokens)
    if key.endswith("_max_tokens"):
        return True
    return False


def _is_sensitive_key(key: str) -> bool:
    normalized = key.replace("-", "_").lower()
    # Allowlist check first - safe token-count fields are never scrubbed
    if _is_safe_token_count_field(normalized):
        return False
    return any(keyword in normalized for keyword in _SENSITIVE_KEYWORDS)


def _sanitize_string(value: str) -> str:
    if not value:
        return value
    sanitized = value
    if _SECRET_MANIFEST_RE.search(sanitized):
        return REDACTION_PLACEHOLDER
    for pattern in _PROMPT_SENSITIVE_PATTERNS:
        if pattern.search(sanitized):
            sanitized = pattern.sub(REDACTION_PLACEHOLDER, sanitized)
    return sanitized


def _is_secret_manifest(value: Mapping[str, Any]) -> bool:
    kind = value.get("kind")
    if not kind:
        return False
    return str(kind).strip().lower() == "secret"


def _sanitize_mapping(value: Mapping[str, Any], *, parent_key: str | None = None) -> dict[str, Any]:
    if _is_secret_manifest(value):
        metadata = value.get("metadata")
        return {
            "kind": str(value.get("kind") or "Secret"),
            "metadata": sanitize_payload(metadata) if isinstance(metadata, Mapping) else {},
            "redacted": "secret manifest",
        }
    sanitized: dict[str, Any] = {}
    for key, item in value.items():
        key_str = str(key)
        if _is_sensitive_key(key_str):
            sanitized[key_str] = REDACTION_PLACEHOLDER
            continue
        sanitized[key_str] = sanitize_payload(item, parent_key=key_str)
    return sanitized


def _sanitize_sequence(value: Iterable[Any]) -> Any:
    if isinstance(value, tuple):
        return tuple(sanitize_payload(item) for item in value)
    if isinstance(value, list):
        return [sanitize_payload(item) for item in value]
    if isinstance(value, set):
        return [sanitize_payload(item) for item in value]
    return [sanitize_payload(item) for item in value]


def sanitize_payload(value: Any, *, parent_key: str | None = None) -> Any:
    if isinstance(value, str):
        return _sanitize_string(value)
    if isinstance(value, Mapping):
        return _sanitize_mapping(value, parent_key=parent_key)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return _sanitize_sequence(value)
    return value


def sanitize_log_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    sanitized = sanitize_payload(entry)
    if isinstance(sanitized, Mapping):
        return dict(sanitized)
    return dict(entry)


def sanitize_prompt(prompt: str) -> str:
    sanitized = prompt
    for pattern in _PROMPT_SENSITIVE_PATTERNS:
        sanitized = pattern.sub(REDACTION_PLACEHOLDER, sanitized)
    if _SECRET_MANIFEST_RE.search(sanitized):
        sanitized = re.sub(r"(?is)^.*?kind\s*[:=]\s*Secret.*?(?:\n\s*\n|$)", "<scrubbed secret manifest>\n", sanitized)
    return sanitized


# Sentinel patterns for regression testing - these should NEVER appear in sanitized output
_SENTINEL_PATTERNS = (
    "KUBE_SECRET_TOKEN_abc123",
    "bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
    "api_key=sk-abcdefghijk",
    "client_secret=super_secret_value",
)


def _contains_sentinel(value: str | None) -> bool:
    """Check if a string contains any sentinel test patterns."""
    if not value:
        return False
    return any(sentinel in value for sentinel in _SENTINEL_PATTERNS)


def sanitize_execution_output(
    raw_output: str | None,
    error_summary: str | None,
    *,
    max_output_length: int = 512,
) -> tuple[str | None, str | None]:
    """Sanitize execution output for operator-facing display.

    This function prevents leakage of:
    - Raw exception text/traceback
    - Raw stderr/stdout content
    - Kubernetes API error bodies
    - LLM prompt fragments
    - Sensitive credentials or tokens

    Args:
        raw_output: Raw command output (may contain sensitive content)
        error_summary: Error message (may contain raw exception or stderr)
        max_output_length: Maximum length for raw_output before truncation

    Returns:
        A tuple of (sanitized_raw_output, sanitized_error_summary).
        Both values are sanitized and safe for operator display.
        Raw output is truncated to max_output_length.
    """
    sanitized_output: str | None = None
    sanitized_error: str | None = None

    # Sanitize raw_output BEFORE truncating to prevent credential pattern splitting
    if raw_output:
        # First apply sanitization to the full string to catch any credentials
        sanitized = sanitize_payload(raw_output)
        if isinstance(sanitized, str) and _SECRET_MANIFEST_RE.search(sanitized):
            sanitized = "<scrubbed>"
        elif isinstance(sanitized, str):
            # Apply all sensitive patterns iteratively
            for pattern in _PROMPT_SENSITIVE_PATTERNS:
                if pattern.search(sanitized):
                    sanitized = pattern.sub(REDACTION_PLACEHOLDER, sanitized)
        # Then truncate the already-sanitized string
        if sanitized and len(sanitized) > max_output_length:
            sanitized = sanitized[:max_output_length]
        sanitized_output = sanitized

    # Sanitize error_summary: this may contain raw exception messages, stderr, or Kubernetes error bodies
    if error_summary:
        sanitized_error = sanitize_payload(error_summary)
        if isinstance(sanitized_error, str) and _SECRET_MANIFEST_RE.search(sanitized_error):
            sanitized_error = "<scrubbed>"
        elif isinstance(sanitized_error, str):
            # Apply all sensitive patterns iteratively
            for pattern in _PROMPT_SENSITIVE_PATTERNS:
                if pattern.search(sanitized_error):
                    sanitized_error = pattern.sub(REDACTION_PLACEHOLDER, sanitized_error)

    return sanitized_output, sanitized_error


def sanitize_exception_message(exc: BaseException, max_length: int = 200) -> str:
    """Sanitize an exception message for operator-facing display.

    Args:
        exc: The exception to sanitize
        max_length: Maximum length for the sanitized message

    Returns:
        A sanitized exception type name with optional truncated message.
    """
    exc_type = type(exc).__name__
    exc_message = str(exc)

    # Apply sanitization to the message
    sanitized_message = sanitize_payload(exc_message)
    if isinstance(sanitized_message, str) and _SECRET_MANIFEST_RE.search(sanitized_message):
        sanitized_message = "<scrubbed>"
    elif isinstance(sanitized_message, str):
        for pattern in _PROMPT_SENSITIVE_PATTERNS:
            if pattern.search(sanitized_message):
                sanitized_message = pattern.sub(REDACTION_PLACEHOLDER, sanitized_message)

    # Build the sanitized message
    if sanitized_message and isinstance(sanitized_message, str) and sanitized_message != "<scrubbed>":
        # Truncate message if too long
        if len(sanitized_message) > max_length:
            sanitized_message = sanitized_message[: max_length - 3] + "..."
        return f"{exc_type}: {sanitized_message}"
    return exc_type


__all__ = [
    "REDACTION_PLACEHOLDER",
    "sanitize_payload",
    "sanitize_log_entry",
    "sanitize_prompt",
    "sanitize_execution_output",
    "sanitize_exception_message",
]
