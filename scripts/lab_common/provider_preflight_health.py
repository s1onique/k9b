"""Health response evaluation for provider preflight in k9b live labs.

This module provides the health response evaluation logic for provider preflight.
JSON classification logic is split to provider_preflight_json_classification.py.

Wire-format validation contract:
Provider health response body must be EXACTLY one clean JSON document.
Any prefix/suffix that is not whitespace constitutes contamination.

Envelope handling:
The curl wrapper emits a known diagnostic envelope around provider health JSON:
  - STDOUT_BLOCK prefix (optional)
  - Valid provider health JSON
  - STDERR_BLOCK marker (optional)
  - CURL_EXIT=<code>
  - HTTP_CODE=<code>

This envelope is NON-FATAL only when detected by _extract_provider_health_payload().
The strict parser (_classify_provider_health_body) validates wire-format FIRST.
Semantic evaluation happens ONLY after wire-format validation passes.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
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
from scripts.lab_common.provider_preflight_json_classification import (
    _format_json_contamination_detail,
)
from scripts.lab_common.provider_preflight_models import ProviderPreflightResult
from scripts.lab_common.provider_status import parse_provider_status_from_health_details

if TYPE_CHECKING:
    pass


@dataclass(frozen=True)
class ProviderHealthPayload:
    """Extracted provider health payload with envelope metadata."""

    json_body: str
    stderr_block: str
    curl_exit: int | None
    http_code: int | None
    envelope_detected: bool
    raw_suffix: str


def _debug_dump_provider_health_raw(raw_output: str) -> None:
    """Dump raw provider health output for debugging (opt-in via env var).

    GitHub Actions supports log grouping via workflow commands emitted to stdout.
    Enable with: K9B_PROVIDER_PREFLIGHT_DUMP_RAW=1
    """
    if os.environ.get("K9B_PROVIDER_PREFLIGHT_DUMP_RAW") != "1":
        return

    print("::group::k9b provider preflight raw output")
    print(raw_output)
    print("::endgroup::")


def _extract_provider_health_payload(raw_output: str) -> ProviderHealthPayload:
    """Extract provider health JSON from raw curl output with known envelope.

    The curl wrapper emits a known diagnostic envelope around provider health JSON.
    This function uses raw_decode to find where the JSON document ends, then
    parses the remaining envelope metadata. Known envelope patterns are NON-FATAL.
    """
    text = raw_output.strip()

    # Strip known wrapper prefix if present
    if text.startswith("STDOUT_BLOCK\n"):
        text = text.removeprefix("STDOUT_BLOCK\n").lstrip()

    decoder = json.JSONDecoder()

    try:
        _, end = decoder.raw_decode(text)
    except json.JSONDecodeError:
        _debug_dump_provider_health_raw(raw_output)
        return ProviderHealthPayload(
            json_body=text,
            stderr_block="",
            curl_exit=None,
            http_code=None,
            envelope_detected=False,
            raw_suffix="",
        )

    json_body = text[:end]
    suffix = text[end:].lstrip()

    if not suffix:
        return ProviderHealthPayload(
            json_body=json_body,
            stderr_block="",
            curl_exit=None,
            http_code=None,
            envelope_detected=False,
            raw_suffix="",
        )

    # Check if suffix starts with known envelope pattern
    known_envelope_prefixes = (
        "STDERR_BLOCK",
        "CURL_EXIT=",
        "HTTP_CODE=",
        "---CURL_",
        "RESOLVING_HOST=",
        "NO_RESPONSE_BODY",
    )
    suffix_starts_known = any(suffix.startswith(p) for p in known_envelope_prefixes)

    if not suffix_starts_known:
        _debug_dump_provider_health_raw(raw_output)
        return ProviderHealthPayload(
            json_body=raw_output.strip(),
            stderr_block="",
            curl_exit=None,
            http_code=None,
            envelope_detected=False,
            raw_suffix=suffix,
        )

    # Parse known envelope metadata
    curl_exit_match = re.search(r"\bCURL_EXIT=(\d+)\b", suffix)
    http_code_match = re.search(r"\bHTTP_CODE=(\d{3})\b", suffix)

    # Extract stderr block content (between STDERR_BLOCK marker and CURL_EXIT/HTTP_CODE)
    # Handle empty block case: STDERR_BLOCK\nCURL_EXIT=0
    stderr_block = ""
    stderr_match = re.search(
        r"STDERR_BLOCK\n(.*?)(?=\nCURL_EXIT=|\nHTTP_CODE=|\Z)", suffix, re.DOTALL
    )
    if stderr_match:
        stderr_block = stderr_match.group(1).strip()

    return ProviderHealthPayload(
        json_body=json_body,
        stderr_block=stderr_block,
        curl_exit=int(curl_exit_match.group(1)) if curl_exit_match else None,
        http_code=int(http_code_match.group(1)) if http_code_match else None,
        envelope_detected=True,
        raw_suffix="",
    )


def _find_first_json_start(raw: str) -> int | None:
    """Find the index of the first '{' or '[' in the string.

    Args:
        raw: The raw body string

    Returns:
        Index of first JSON start character, or None if not found
    """
    for idx, ch in enumerate(raw):
        if ch in "{[":
            return idx
    return None


def _suffix_starts_with_json_document(suffix: str) -> bool:
    """Check if suffix starts with a valid JSON document.

    Args:
        suffix: The trailing bytes after valid JSON prefix

    Returns:
        True if suffix starts with '{' or '[' (after stripping whitespace)
    """
    stripped = suffix.lstrip()
    return stripped.startswith("{") or stripped.startswith("[")


def _classify_provider_health_body(raw: str) -> tuple[str | None, object | None, str]:
    """Strict wire-format validation for provider health response body.

    Provider health response body must be EXACTLY one clean JSON document.
    Wire-format validation MUST happen before semantic health evaluation.

    Classification order:
    1. Empty/whitespace-only body -> provider_health_empty_body
    2. JSON + non-whitespace suffix that is valid JSON -> provider_health_invalid_json
    3. JSON + non-whitespace suffix (including curl metadata) -> provider_health_output_contaminated
    4. Non-whitespace prefix + JSON -> provider_health_output_contaminated
    5. Malformed JSON with no embedded JSON -> provider_health_invalid_json
    6. Exactly one clean JSON document -> (None, payload, "") for semantic evaluation

    Args:
        raw: The raw body string from curl response

    Returns:
        Tuple of (failure_class, payload_or_none, detail_message).
        If failure_class is None, payload contains the parsed JSON and evaluation proceeds.
    """
    if not raw.strip():
        return (
            FAILURE_PROVIDER_HEALTH_EMPTY_BODY,
            None,
            "Provider health response body was empty",
        )

    decoder = json.JSONDecoder()

    # Find first non-whitespace position
    first_non_ws = len(raw) - len(raw.lstrip())

    # Try to decode JSON starting at first non-whitespace
    try:
        payload, end = decoder.raw_decode(raw, first_non_ws)
    except json.JSONDecodeError:
        # JSON decode failed - check if there's JSON somewhere after the prefix
        json_start = _find_first_json_start(raw)
        if json_start is not None and json_start > first_non_ws:
            # Found JSON but after some non-whitespace prefix = contamination
            return (
                FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED,
                None,
                _format_json_contamination_detail(raw),
            )
        return (
            FAILURE_PROVIDER_HEALTH_INVALID_JSON,
            None,
            f"Invalid JSON response from /api/health/details (HTTP 200). "
            f"Body prefix (first 200 chars): {raw[:200]!r}",
        )

    # end is already an absolute index into raw (from raw_decode starting at first_non_ws)
    suffix_start = end
    suffix = raw[suffix_start:]

    # Skip whitespace-only suffix
    suffix_stripped = suffix.lstrip()

    if suffix_stripped:
        # Try to decode at suffix start - if it succeeds, this is concatenated JSON
        try:
            decoder.raw_decode(suffix_stripped)
            # Suffix is valid JSON - concatenated documents = invalid_json
            return (
                FAILURE_PROVIDER_HEALTH_INVALID_JSON,
                None,
                f"Invalid JSON response: concatenated JSON documents. "
                f"Body prefix (first 200 chars): {raw[:200]!r}",
            )
        except json.JSONDecodeError:
            # Suffix is not valid JSON - this is contamination (log output, curl metadata, etc.)
            return (
                FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED,
                None,
                f"Output contamination: trailing non-JSON data after valid JSON. {_format_json_contamination_detail(raw)}",
            )

    # Valid: exactly one clean JSON document with no prefix/suffix contamination
    # Leading whitespace is allowed and already skipped by raw_decode starting at first_non_ws
    # Non-whitespace prefix contamination is handled in the JSONDecodeError path
    return None, payload, ""


def _classify_raw_body_for_wire_format(
    raw_body: str,
) -> tuple[str | None, object | None, str]:
    """Classify raw body for wire-format validation.

    This classifies the RAW body before any envelope extraction.
    Any trailing curl metadata (CURL_EXIT, HTTP_CODE) is contamination.

    Args:
        raw_body: The raw body string from curl response

    Returns:
        Tuple of (failure_class, payload_or_none, detail_message).
        If failure_class is None, payload contains the parsed JSON and evaluation proceeds.
    """
    # Classify the raw body directly
    failure_class, payload, detail = _classify_provider_health_body(raw_body)

    if failure_class is not None:
        # Wire-format validation failed on raw body
        return failure_class, payload, detail

    # Wire-format passed on raw body - envelope metadata extraction
    # happens later in _evaluate_health_response if needed for diagnostics
    return None, payload, detail


def _evaluate_health_response(
    result: ProviderPreflightResult,
    curl_result: CurlResult,
    start: float,
    artifact_dir: Path,
    require_provider_configured: bool,
    require_provider_invocation_possible: bool,
) -> ProviderPreflightResult:
    """Evaluate a successful health response and determine provider state.

    Wire-format validation MUST happen before semantic health evaluation.
    The curl wrapper emits a known diagnostic envelope around provider health JSON:
      - STDOUT_BLOCK prefix (optional)
      - Valid provider health JSON
      - STDERR_BLOCK marker (optional)
      - CURL_EXIT=<code>
      - HTTP_CODE=<code>

    Known curl envelope suffixes are NON-FATAL - they are transport metadata.
    Unknown suffixes remain contamination.

    Step 1: Try to extract known curl envelope FIRST.
    Step 2: If envelope extraction succeeds, use extracted JSON body.
    Step 3: If no envelope, fall back to strict JSON validation.
    Step 4: Semantic provider-health evaluation after wire-format passes.
    """
    raw_body = curl_result.body

    # Step 1: Try known curl envelope extraction FIRST
    # This handles the common case where curl wrapper metadata is present
    envelope_payload = _extract_provider_health_payload(raw_body)

    if envelope_payload.envelope_detected:
        # Known envelope detected - use the extracted JSON body
        json_body = envelope_payload.json_body
        try:
            health_details = json.loads(json_body)
        except json.JSONDecodeError as e:
            result.failure_class = FAILURE_PROVIDER_HEALTH_INVALID_JSON
            result.message = f"Invalid JSON in envelope body: {e}"
            result.duration_seconds = time.time() - start
            _write_result(result, artifact_dir)
            return result
    else:
        # Step 2: No known envelope - fall back to strict JSON validation
        # This catches contamination from unknown suffixes
        failure_class, json_payload, detail = _classify_raw_body_for_wire_format(raw_body)

        if failure_class is not None:
            # Wire-format validation failed - return immediately, no semantic evaluation
            result.failure_class = failure_class
            result.message = detail
            result.duration_seconds = time.time() - start
            _write_result(result, artifact_dir)
            return result

        # Wire-format valid - parse JSON for semantic evaluation
        assert json_payload is not None, "payload should not be None when failure_class is None"

        # Handle the case where payload might be a string (json_body) or dict
        if isinstance(json_payload, str):
            health_details = json.loads(json_payload)
        elif isinstance(json_payload, dict):
            health_details = json_payload
        else:
            # This shouldn't happen with proper classification
            result.failure_class = FAILURE_PROVIDER_HEALTH_INVALID_JSON
            result.message = f"Unexpected payload type: {type(json_payload).__name__}"
            result.duration_seconds = time.time() - start
            _write_result(result, artifact_dir)
            return result

    # Step 4: Semantic provider-health evaluation
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
