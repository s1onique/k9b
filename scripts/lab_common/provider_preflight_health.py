"""Health response evaluation for provider preflight in k9b live labs.

This module provides the health response evaluation and JSON parse failure
classification logic. It is split from provider_preflight.py to keep file sizes
under LLM-friendly limits.

Classification contract:
1. First attempt strict json.loads(isolated_body).
2. If it succeeds: evaluate provider health semantics normally.
3. If it fails:
   - if body is empty or whitespace: provider_health_empty_body
   - run raw_decode only as a diagnostic probe.
4. If raw_decode finds valid JSON prefix plus trailing bytes:
   - inspect trailing suffix
   - classify as provider_health_output_contaminated ONLY if suffix contains
     known framing/curl metadata patterns:
     * CURL_EXIT=
     * HTTP_CODE=
     * ---CURL_
     * STDERR_BLOCK
     * known write-out keys emitted by this harness
   - otherwise classify as provider_health_invalid_json
5. Genuinely malformed JSON remains provider_health_invalid_json.
6. Messages include bounded previews only (body prefix, trailing suffix prefix).
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.lab_common.constants import (
    FAILURE_PROVIDER_DISABLED_REQUIRED,
    FAILURE_PROVIDER_HEALTH_EMPTY_BODY,
    FAILURE_PROVIDER_HEALTH_INVALID_JSON,
    FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED,
    FAILURE_PROVIDER_NOT_INITIALIZED,
    FAILURE_PROVIDER_UNAVAILABLE,
)
from scripts.lab_common.provider_curl_helpers import CurlResult
from scripts.lab_common.provider_preflight_models import ProviderPreflightResult
from scripts.lab_common.provider_status import parse_provider_status_from_health_details

if TYPE_CHECKING:
    pass


# Known curl/framing metadata patterns that indicate output contamination
# These are patterns emitted by the curl harness in provider_curl_helpers.py
_CURL_FRAMING_PATTERNS = (
    r"^CURL_EXIT=\d+",  # curl exit code
    r"^HTTP_CODE=\d+",  # HTTP response code
    r"^---CURL_",  # framing marker from curl harness
    r"^STDERR_BLOCK",  # stderr block marker
    r"^RESOLVING_HOST=",  # DNS resolution diagnostic
    r"^NO_RESPONSE_BODY$",  # empty body marker
)


def _looks_like_curl_framing_suffix(suffix: str) -> bool:
    """Check if suffix matches known curl/framing metadata patterns.

    This prevents misclassifying arbitrary trailing bytes as curl output
    contamination. Only known metadata patterns (CURL_EXIT=, HTTP_CODE=,
    ---CURL_, STDERR_BLOCK, etc.) should trigger output_contaminated.

    Args:
        suffix: The trailing bytes after valid JSON prefix

    Returns:
        True if suffix looks like curl/framing metadata
    """
    if not suffix:
        return False

    # Strip leading whitespace to handle newlines between JSON and metadata
    stripped = suffix.lstrip()
    if not stripped:
        return False

    # Check against known patterns
    for pattern in _CURL_FRAMING_PATTERNS:
        if re.match(pattern, stripped, re.MULTILINE):
            return True

    return False


def _classify_json_parse_failure(body: str, exc: json.JSONDecodeError) -> tuple[str, str, str | None]:
    """Classify a JSON parse failure with diagnostic probe.

    Uses raw_decode to determine if the failure is due to:
    1. Empty body -> empty_body
    2. Valid JSON + known curl/framing metadata (contamination) -> output_contaminated
    3. Valid JSON + arbitrary trailing bytes -> invalid_json
    4. Genuinely invalid JSON -> invalid_json

    Args:
        body: The raw body string that failed to parse
        exc: The JSONDecodeError that was raised

    Returns:
        Tuple of (failure_class, message, trailing_suffix_preview)
    """
    # Check for empty body
    if not body or not body.strip():
        return (
            FAILURE_PROVIDER_HEALTH_EMPTY_BODY,
            "Empty response body from /api/health/details",
            None,
        )

    # Use raw_decode to probe for valid JSON prefix with trailing bytes
    # This distinguishes contamination (valid JSON + known curl metadata)
    # from arbitrary extra data (valid JSON + unknown trailing bytes)
    try:
        decoded, end_index = json.JSONDecoder().raw_decode(body)
        remaining = body[end_index:].strip()

        if remaining:
            # Valid JSON prefix with trailing bytes
            # Check if trailing suffix looks like known curl/framing metadata
            if _looks_like_curl_framing_suffix(remaining):
                # This is genuine output contamination (curl metadata appended)
                trailing_preview = remaining[:100]  # Bounded preview
                return (
                    FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED,
                    f"JSON parse error: valid JSON followed by known curl/framing metadata "
                    f"(output framing contamination). Trailing suffix preview (first 100 chars): {trailing_preview!r}",
                    trailing_preview,
                )
            else:
                # Arbitrary trailing bytes (not known curl metadata)
                # This is invalid JSON, not contamination
                body_prefix = body[:200]
                return (
                    FAILURE_PROVIDER_HEALTH_INVALID_JSON,
                    f"Invalid JSON response from /api/health/details (HTTP 200). "
                    f"JSON parse error: extra data after valid JSON object. "
                    f"Body prefix (first 200 chars): {body_prefix!r}",
                    None,
                )
    except (json.JSONDecodeError, ValueError):
        pass  # Not valid JSON prefix, fall through to invalid_json

    # Genuinely invalid JSON (malformed, not just extra data)
    json_error_msg = f"line {exc.lineno}, col {exc.colno}: {exc.msg}" if hasattr(exc, 'lineno') else str(exc)
    body_prefix = body[:200]
    return (
        FAILURE_PROVIDER_HEALTH_INVALID_JSON,
        f"Invalid JSON response from /api/health/details (HTTP 200). "
        f"JSON parse error: {json_error_msg}. "
        f"Body prefix (first 200 chars): {body_prefix!r}",
        None,
    )


def _evaluate_health_response(
    result: ProviderPreflightResult,
    curl_result: CurlResult,
    start: float,
    artifact_dir: Path,
    require_provider_configured: bool,
    require_provider_invocation_possible: bool,
) -> ProviderPreflightResult:
    """Evaluate a successful health response and determine provider state."""
    try:
        health_details = json.loads(curl_result.body)
    except json.JSONDecodeError as exc:
        # Enhanced diagnostics: use raw_decode probe to classify the failure
        # This distinguishes:
        # 1. Empty body -> provider_health_empty_body
        # 2. Valid JSON + known curl metadata -> provider_health_output_contaminated
        # 3. Valid JSON + arbitrary trailing bytes -> provider_health_invalid_json
        # 4. Genuinely invalid JSON -> provider_health_invalid_json
        failure_class, message, _ = _classify_json_parse_failure(curl_result.body, exc)
        result.failure_class = failure_class
        result.message = message
        result.duration_seconds = time.time() - start
        _write_result(result, artifact_dir)
        return result

    result.parsed_status = parse_provider_status_from_health_details(health_details)

    result.provider_enabled = result.parsed_status.provider_enabled
    result.provider_configured = result.parsed_status.provider_configured
    result.provider_invocation_attempted = result.parsed_status.provider_invocation_attempted
    result.provider_name = result.parsed_status.provider_name
    result.provider_status = result.parsed_status.provider_status
    result.provider_phase = result.parsed_status.provider_phase
    result.diagnosis_provider_enabled = result.parsed_status.diagnosis_provider_enabled

    primary_failure = health_details.get("primary_failure_class", "")

    result = _evaluate_provider_state(
        result=result,
        primary_failure=primary_failure,
        require_provider_configured=require_provider_configured,
        require_provider_invocation_possible=require_provider_invocation_possible,
    )

    result.duration_seconds = time.time() - start
    _write_result(result, artifact_dir)
    return result


def _evaluate_provider_state(
    result: ProviderPreflightResult,
    primary_failure: str,
    require_provider_configured: bool,
    require_provider_invocation_possible: bool,
) -> ProviderPreflightResult:
    """Evaluate provider state and determine pass/fail."""
    if primary_failure == "dependency_provider_connection_failed":
        result.failure_class = FAILURE_PROVIDER_UNAVAILABLE
        result.message = "Diagnosis provider unavailable: dependency_provider_connection_failed"
        result.passed = False
        return result

    if not result.provider_enabled and require_provider_configured:
        result.failure_class = FAILURE_PROVIDER_DISABLED_REQUIRED
        result.message = "Diagnosis provider disabled but required"
        result.passed = False
        return result

    if not result.provider_configured and require_provider_configured:
        result.failure_class = FAILURE_PROVIDER_UNAVAILABLE
        result.message = "Diagnosis provider not configured"
        result.passed = False
        return result

    if result.provider_phase in ("not_initialized", "unknown"):
        if require_provider_invocation_possible:
            result.failure_class = FAILURE_PROVIDER_NOT_INITIALIZED
            result.message = f"Diagnosis provider not initialized (phase={result.provider_phase})"
            result.passed = False
            return result

    if result.provider_status in ("unavailable", "failed", "error"):
        result.failure_class = FAILURE_PROVIDER_UNAVAILABLE
        result.message = f"Diagnosis provider unavailable (status={result.provider_status})"
        result.passed = False
        return result

    result.passed = True
    result.message = "Provider preflight passed"
    result.failure_class = None
    return result


def _write_result(result: ProviderPreflightResult, artifact_dir: Path) -> None:
    """Write preflight result to artifact directory."""

    result_path = artifact_dir / "provider-preflight-result.json"
    with open(result_path, "w") as f:
        json.dump(result.to_dict(), f, indent=2)
