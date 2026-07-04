"""Health response evaluation for provider preflight in k9b live labs.

This module provides the health response evaluation logic for provider preflight.
JSON classification logic is split to provider_preflight_json_classification.py.
Curl envelope parsing logic is split to provider_preflight_curl_envelope.py.

Wire-format validation contract:
Provider health response body consists of:
1. Optional leading whitespace
2. Valid provider health JSON document
3. Optional known successful curl wrapper envelope metadata (transport layer)

STDOUT_BLOCK prefix handling is performed before this classifier receives the
provider-health body. This classifier owns JSON + optional successful curl suffix
handling only.

Envelope handling:
The curl wrapper may emit a known diagnostic envelope around provider health JSON:
  - Valid provider health JSON
  - STDERR_BLOCK marker (optional)
  - CURL_EXIT=<code>
  - HTTP_CODE=<code>

Known successful curl envelope (CURL_EXIT=0, HTTP_CODE=200) is ACCEPTED as transport
envelope metadata. It is NOT provider-health JSON body contamination.

Contamination rules:
- Non-whitespace prefix before JSON -> contamination
- Concatenated JSON documents -> invalid_json
- Unknown non-whitespace suffix -> contamination
- Malformed JSON -> invalid_json
"""

from __future__ import annotations

import json
import os
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
from scripts.lab_common.provider_preflight_curl_envelope import parse_known_curl_envelope_suffix
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
    parses the remaining envelope metadata. Known successful envelope patterns
    (CURL_EXIT=0, HTTP_CODE=200) are NON-FATAL.

    Invalid or failed curl metadata (non-zero exit, non-200 HTTP code) is NOT
    accepted as envelope - it falls through to contamination detection.

    Note: The curl wrapper in provider_curl_helpers.py emits:
      - STDOUT_BLOCK prefix marker (---CURL_START--- in stdout stream)
      - Provider health JSON body
      - STDERR_BLOCK marker
      - CURL_EXIT=<code>
      - HTTP_CODE=<code>

    The marker-based parsing in _curl_service_pod/_curl_exec_pod already
    extracts body and metadata separately. The remaining envelope handling here
    processes the post-extraction output where:
      - STDERR_BLOCK appears AFTER the JSON body (not before)
      - CURL_EXIT and HTTP_CODE follow STDERR_BLOCK
    """
    text = raw_output.strip()

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

    # Try to parse as known successful curl envelope
    envelope = parse_known_curl_envelope_suffix(suffix)
    if envelope is not None:
        curl_exit, http_code, stderr_block = envelope
        return ProviderHealthPayload(
            json_body=json_body,
            stderr_block=stderr_block,
            curl_exit=curl_exit,
            http_code=http_code,
            envelope_detected=True,
            raw_suffix="",
        )

    # Not a known successful envelope - mark as raw (will be contamination)
    _debug_dump_provider_health_raw(raw_output)
    return ProviderHealthPayload(
        json_body=raw_output.strip(),
        stderr_block="",
        curl_exit=None,
        http_code=None,
        envelope_detected=False,
        raw_suffix=suffix,
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
    """Wire-format validation for provider health response body.

    Provider health body validation contract:
    - Empty/whitespace-only body -> provider_health_empty_body
    - Non-whitespace prefix + JSON -> provider_health_output_contaminated
    - JSON + non-whitespace suffix that is valid JSON -> provider_health_invalid_json
    - JSON + known successful curl envelope -> PASS (accepted transport metadata)
    - JSON + unknown non-whitespace suffix -> provider_health_output_contaminated
    - Malformed JSON with no embedded JSON -> provider_health_invalid_json
    - Exactly one clean JSON document (no prefix/suffix) -> (None, payload, "") for semantic evaluation

    Wire-format layers:
    1. Transport envelope extraction: Known successful curl metadata (CURL_EXIT=0, HTTP_CODE=200,
       STDERR_BLOCK) is ACCEPTED as transport envelope. Not provider-body contamination.
    2. JSON body classification: Valid JSON body passes to semantic evaluation.
    3. Semantic provider-health evaluation: Only proceeds after wire-format passes.

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

    # Skip whitespace-only suffix - this is valid (leading/trailing whitespace allowed)
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
            # Suffix is not valid JSON. Check if it's a known successful curl envelope.
            # Known successful curl envelope (CURL_EXIT=0, HTTP_CODE=200) is ACCEPTED
            # as transport envelope metadata - not provider-body contamination.
            envelope = parse_known_curl_envelope_suffix(suffix_stripped)
            if envelope is not None:
                # Known successful curl envelope - ACCEPTED
                return None, payload, ""
            # Not a known successful envelope - mark as contamination
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
    """Evaluate provider health response.

    Wire-format validation MUST happen before semantic evaluation.

    The curl wrapper may emit a known diagnostic envelope around provider health JSON:
      - STDOUT_BLOCK prefix (optional)
      - Valid provider health JSON
      - STDERR_BLOCK marker (optional)
      - CURL_EXIT=<code>
      - HTTP_CODE=<code>

    Known successful curl envelope (CURL_EXIT=0, HTTP_CODE=200) is ACCEPTED as transport
    envelope metadata. Semantic evaluation proceeds with the valid JSON body.

    Step 1: Wire-format validation on raw body (includes curl envelope extraction).
    Step 2: Semantic provider-health evaluation only for valid clean JSON.
    """
    raw_body = curl_result.body

    # Step 1: Wire-format validation MUST happen BEFORE any semantic evaluation.
    # This includes accepting known successful curl envelope as transport metadata.
    failure_class, json_payload, detail = _classify_raw_body_for_wire_format(raw_body)

    if failure_class is not None:
        # Wire-format validation failed - return immediately, no semantic evaluation.
        # Semantic failures like provider_disabled_required must never override
        # contaminated transport/wire output.
        result.failure_class = failure_class
        result.message = detail
        result.duration_seconds = time.time() - start
        _write_result(result, artifact_dir)
        return result

    # Wire-format passed - parse JSON for semantic evaluation
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

    # Step 2: Semantic provider-health evaluation
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
