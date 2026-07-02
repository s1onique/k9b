"""JSON classification logic for provider preflight.

This module provides functions to classify JSON parse failures and detect
contamination vs invalid JSON patterns. Split from provider_preflight_health.py
to keep file sizes under LLM-friendly limits.
"""

from __future__ import annotations

import json
import re

from scripts.lab_common.constants import (
    FAILURE_PROVIDER_HEALTH_EMPTY_BODY,
    FAILURE_PROVIDER_HEALTH_INVALID_JSON,
    FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED,
)


def _format_json_contamination_detail(output: str, *, limit: int = 200) -> str:
    """Format JSON contamination diagnostic details using raw_decode.

    Args:
        output: The raw body string that contains JSON + contamination
        limit: Maximum characters for each part

    Returns:
        A string describing non-JSON prefix/suffix with bounded snippets
    """
    body = output or ""
    stripped = body.lstrip()
    leading_len = len(body) - len(stripped)

    decoder = json.JSONDecoder()

    try:
        _, end = decoder.raw_decode(stripped)
    except json.JSONDecodeError:
        return f"Body prefix (first {limit} chars): {body[:limit]!r}"

    json_start = leading_len
    json_end = leading_len + end

    prefix = body[:json_start].strip()
    suffix = body[json_end:].strip()

    parts: list[str] = []

    if prefix:
        parts.append(f"Non-JSON prefix (first {limit} chars): {prefix[:limit]!r}")

    if suffix:
        parts.append(f"Non-JSON suffix (first {limit} chars): {suffix[:limit]!r}")

    if not parts:
        parts.append(f"Body prefix (first {limit} chars): {body[:limit]!r}")

    return "; ".join(parts)


def _extract_clean_or_contaminated_json(
    text: str,
) -> tuple[dict[str, object] | None, str | None]:
    """Return parsed provider health JSON, or a specific failure reason."""
    stripped = text.strip()
    if not stripped:
        return None, FAILURE_PROVIDER_HEALTH_INVALID_JSON

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        pass
    else:
        if isinstance(parsed, dict):
            return parsed, None
        return None, FAILURE_PROVIDER_HEALTH_INVALID_JSON

    decoder = json.JSONDecoder()

    # Case 1: valid JSON object starts at position 0 but has trailing content.
    try:
        parsed, end_idx = decoder.raw_decode(stripped)
    except json.JSONDecodeError:
        parsed = None
        end_idx = 0

    if isinstance(parsed, dict):
        suffix = stripped[end_idx:].strip()
        if not suffix:
            return parsed, None

        # Adjacent JSON documents are malformed JSON, not log contamination.
        if suffix[0] in "{[\"-0123456789":
            return None, FAILURE_PROVIDER_HEALTH_INVALID_JSON

        return None, FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED

    # Case 2: valid JSON object appears after log prefix or as array.
    for idx, char in enumerate(stripped):
        if char not in "{[":
            continue

        try:
            parsed, end_idx = decoder.raw_decode(stripped[idx:])
        except json.JSONDecodeError:
            continue

        if not isinstance(parsed, dict):
            continue

        prefix = stripped[:idx].strip()
        suffix = stripped[idx + end_idx :].strip()

        if not prefix and not suffix:
            return parsed, None

        # Check if prefix is complete JSON value followed by more JSON.
        if prefix:
            try:
                decoder.raw_decode(prefix)
                return None, FAILURE_PROVIDER_HEALTH_INVALID_JSON
            except (json.JSONDecodeError, ValueError):
                pass

        # Check if suffix itself is valid JSON (adjacent JSON documents).
        if suffix:
            try:
                json.loads(suffix)
                return None, FAILURE_PROVIDER_HEALTH_INVALID_JSON
            except json.JSONDecodeError:
                pass

            if suffix[0] in "{[\"-0123456789]":
                return None, FAILURE_PROVIDER_HEALTH_INVALID_JSON

        return None, FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED

    return None, FAILURE_PROVIDER_HEALTH_INVALID_JSON


def _looks_like_curl_framing_suffix(suffix: str) -> bool:
    """Check if suffix matches known curl/framing metadata patterns.

    Args:
        suffix: The trailing bytes after valid JSON prefix

    Returns:
        True if suffix looks like curl/framing metadata
    """
    if not suffix:
        return False

    stripped = suffix.lstrip()
    if not stripped:
        return False

    for pattern in (
        r"^CURL_EXIT=\d+",
        r"^HTTP_CODE=\d+",
        r"^---CURL_",
        r"^STDERR_BLOCK",
        r"^RESOLVING_HOST=",
        r"^NO_RESPONSE_BODY$",
    ):
        if re.match(pattern, stripped, re.MULTILINE):
            return True

    return False


def _classify_json_parse_failure(
    body: str, exc: json.JSONDecodeError
) -> tuple[str, str, str | None]:
    """Classify a JSON parse failure with diagnostic probe.

    Args:
        body: The raw body string that failed to parse
        exc: The JSONDecodeError that was raised

    Returns:
        Tuple of (failure_class, message, trailing_suffix_preview)
    """
    if not body or not body.strip():
        return (
            FAILURE_PROVIDER_HEALTH_EMPTY_BODY,
            "Empty response body from /api/health/details",
            None,
        )

    _, failure_reason = _extract_clean_or_contaminated_json(body)

    if failure_reason == FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED:
        contamination_detail = _format_json_contamination_detail(body)
        return (
            FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED,
            f"JSON parse error: valid JSON found but output contains non-JSON "
            f"prefix/suffix (output contamination). {contamination_detail}",
            None,
        )

    json_error_msg = (
        f"line {exc.lineno}, col {exc.colno}: {exc.msg}"
        if hasattr(exc, "lineno") else str(exc)
    )
    body_prefix = body[:200]
    return (
        FAILURE_PROVIDER_HEALTH_INVALID_JSON,
        f"Invalid JSON response from /api/health/details (HTTP 200). "
        f"JSON parse error: {json_error_msg}. "
        f"Body prefix (first 200 chars): {body_prefix!r}",
        None,
    )
