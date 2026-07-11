"""Sanitization helpers for logs, prompts, and exported payloads.

This module delegates sensitive-text redaction to the canonical redaction policy
defined in k8s_diag_agent.security.redaction_policy.

For simple string redaction, it uses redact_sensitive_text() directly.
For structured data sanitization, it applies the policy patterns.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from k8s_diag_agent.security.redaction_policy import (
    REDACTION_PATTERNS as _REDACTION_PATTERNS,
)

# REDACTION_PLACEHOLDER is imported from the policy module for consistency
from k8s_diag_agent.security.redaction_policy import REDACTION_PLACEHOLDER as _REDACTION_PLACEHOLDER
from k8s_diag_agent.security.redaction_policy import redact_sensitive_text as _raw_policy_redact

# Re-export for backward compatibility
REDACTION_PLACEHOLDER: str = str(_REDACTION_PLACEHOLDER)


def _policy_redact(value: str) -> str:
    """Typed wrapper around the shared redaction policy for file-path mypy runs."""
    return str(_raw_policy_redact(value))


def _contains_sensitive_material(value: str | None) -> bool:
    """Return True if ``value`` still contains any canonical sensitive pattern.

    Used as the fail-closed guard after redaction: if any redaction pattern
    still matches the post-redaction text, the redaction was incomplete and
    the caller must not trust the result.

    The canonical detector catches every pattern defined in
    :data:`k8s_diag_agent.security.redaction_policy.REDACTION_PATTERNS`,
    including opaque sentinel identifiers like ``KUBE_SECRET_TOKEN_abc123``
    that do not appear in a ``key=value`` assignment shape.
    """
    if not value:
        return False
    return any(pattern.search(value) for pattern in _REDACTION_PATTERNS)


def _contains_sensitive_material_recursive(value: Any) -> bool:
    """Recursively scan ``value`` (mapping / sequence / str) for sensitive patterns.

    Used as the final defensive assertion right before serialization. If any
    nested string still contains a canonical sensitive pattern the payload
    is considered unsafe.
    """
    if isinstance(value, str):
        return _contains_sensitive_material(value)
    if isinstance(value, Mapping):
        return any(_contains_sensitive_material_recursive(v) for v in value.values())
    if isinstance(value, (list, tuple, set, frozenset)) and not isinstance(value, (bytes, bytearray)):
        return any(_contains_sensitive_material_recursive(item) for item in value)
    return False


def redact_and_bound(value: str, *, max_length: int) -> str:
    """Redact ``value`` using the canonical policy, fail closed if unsafe.

    This is the canonical "redact, validate, then bound" operation for all
    text surfaces that cross the operator / LLM / projection boundary:

    1. Apply :func:`k8s_diag_agent.security.redaction_policy.redact_sensitive_text`
       so known credential-shaped content is replaced by ``REDACTION_PLACEHOLDER``.
    2. Re-scan the redacted text. If the canonical detector still considers
       it unsafe (because no pattern matched a bare opaque token like
       ``KUBE_SECRET_TOKEN_abc123``), return ``REDACTION_PLACEHOLDER`` and do
       not expose a truncation-boundary fragment of the credential.
    3. Bound the result to ``max_length`` characters.

    Truncation must always happen *after* redaction so that a credential
    straddling the truncation boundary cannot leak its suffix.
    """
    if not value:
        return value
    redacted = _policy_redact(value)
    if _contains_sensitive_material(redacted):
        # Fail closed: the canonical detector still sees a sensitive
        # pattern, so we drop the entire surface rather than expose a
        # partial credential at the truncation boundary.
        return REDACTION_PLACEHOLDER
    if len(redacted) > max_length:
        return redacted[:max_length]
    return redacted


_SECRET_MANIFEST_RE = re.compile(r"kind\s*[:=]\s*Secret", re.IGNORECASE)

# Sentinel patterns for regression testing - these should NEVER appear in sanitized output
_SENTINEL_PATTERNS = (
    "KUBE_SECRET_TOKEN_abc123",
    "bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
    "api_key=sk-abcdefghijk",
    "client_secret=super_secret_value",
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

# Sensitive keywords for key-based scrubbing
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
    """Check if a key contains sensitive keywords."""
    normalized = key.replace("-", "_").lower()
    # Allowlist check first - safe token-count fields are never scrubbed
    if _is_safe_token_count_field(normalized):
        return False
    return any(keyword in normalized for keyword in _SENSITIVE_KEYWORDS)


def _sanitize_string(value: str) -> str:
    """Sanitize a string value using the shared policy."""
    if not value:
        return value
    if _SECRET_MANIFEST_RE.search(value):
        return REDACTION_PLACEHOLDER
    # Use the shared policy for redaction
    return _policy_redact(value)


def _is_secret_manifest(value: Mapping[str, Any]) -> bool:
    """Check if a mapping represents a Kubernetes Secret manifest."""
    kind = value.get("kind")
    if not kind:
        return False
    return str(kind).strip().lower() == "secret"


def _sanitize_mapping(value: Mapping[str, Any], *, parent_key: str | None = None) -> dict[str, Any]:
    """Sanitize a mapping (dict-like object)."""
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
    """Sanitize a sequence (list, tuple, set)."""
    if isinstance(value, tuple):
        return tuple(sanitize_payload(item) for item in value)
    if isinstance(value, list):
        return [sanitize_payload(item) for item in value]
    if isinstance(value, set):
        return [sanitize_payload(item) for item in value]
    return [sanitize_payload(item) for item in value]


def sanitize_payload(value: Any, *, parent_key: str | None = None) -> Any:
    """Sanitize a value for safe logging/display.

    This function delegates to the shared redaction policy for string values.

    Args:
        value: The value to sanitize
        parent_key: Optional parent key name for context

    Returns:
        The sanitized value safe for logging/display
    """
    if isinstance(value, str):
        return _sanitize_string(value)
    if isinstance(value, Mapping):
        return _sanitize_mapping(value, parent_key=parent_key)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return _sanitize_sequence(value)
    return value


def sanitize_log_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Sanitize a log entry for operator-facing display."""
    sanitized = sanitize_payload(entry)
    if isinstance(sanitized, Mapping):
        return dict(sanitized)
    return dict(entry)


def sanitize_prompt(prompt: str) -> str:
    """Sanitize a prompt string using the shared policy."""
    sanitized = _policy_redact(prompt)
    if _SECRET_MANIFEST_RE.search(sanitized):
        return "<scrubbed secret manifest>"
    return sanitized


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

    The redact, validate, then bound sequence is delegated to
    :func:`redact_and_bound`, which guarantees that if the canonical
    detector still considers the post-redaction text unsafe (for
    example, because an opaque-token tail like ``+/def==`` survived
    redaction), the entire surface is replaced by the placeholder
    instead of leaking a partial credential.

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

    # Sanitize raw_output BEFORE truncating to prevent credential
    # pattern splitting at the truncation boundary.
    if raw_output:
        # Belt-and-braces: the SharedPolicy handles the Secret manifest
        # shape (``kind: Secret``) before the canonical detector scans.
        sanitized = _policy_redact(raw_output)
        if _SECRET_MANIFEST_RE.search(sanitized):
            sanitized = REDACTION_PLACEHOLDER
        # Run the canonical redact-and-bound flow. This re-scans the
        # post-redaction text and bounds the result. If redaction
        # leaves residual sensitive material (e.g., an opaque-token
        # tail that the regex missed), ``redact_and_bound`` fail-closes
        # the surface to REDACTION_PLACEHOLDER.
        sanitized_output = redact_and_bound(
            sanitized or "",
            max_length=max_output_length,
        ) or None

    # Sanitize error_summary using the canonical redact-and-bound flow
    # so any tail leaks are closed too.
    if error_summary:
        sanitized_error_candidate = _policy_redact(error_summary)
        if _SECRET_MANIFEST_RE.search(sanitized_error_candidate):
            sanitized_error_candidate = REDACTION_PLACEHOLDER
        sanitized_error = redact_and_bound(
            sanitized_error_candidate or "",
            max_length=max_output_length,
        ) or None

    return sanitized_output, sanitized_error


def sanitize_exception_message(exc: BaseException, max_length: int = 200) -> str:
    """Sanitize an exception message for operator-facing display.

    The fail-closed ``redact_and_bound`` helper is invoked with
    ``max_length + 1`` so a sanitized message that is exactly at the
    limit can be re-sliced to ``max_length - 3`` and have the stable
    ``...`` ellipsis appended. The bounded length must therefore be
    preserved on the output surface, and the overlong branch must be
    reachable.

    Args:
        exc: The exception to sanitize
        max_length: Maximum length for the sanitized message

    Returns:
        A sanitized exception type name with optional truncated message.
    """
    exc_type = type(exc).__name__
    exc_message = str(exc)

    # Apply sanitization using the shared policy
    sanitized_message = _policy_redact(exc_message)
    if _SECRET_MANIFEST_RE.search(sanitized_message):
        sanitized_message = REDACTION_PLACEHOLDER

    # Probe one extra character so the overlong branch below can fire
    # when ``redact_and_bound`` returns the maximum length exactly.
    # This preserves the stable ``...`` surface marker.
    sanitized_message = redact_and_bound(
        sanitized_message or "",
        max_length=max_length + 1,
    )

    if sanitized_message and sanitized_message != REDACTION_PLACEHOLDER:
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
