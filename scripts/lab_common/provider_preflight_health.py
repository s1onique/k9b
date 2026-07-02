"""Health response evaluation for provider preflight in k9b live labs.

This module provides the health response evaluation logic for provider preflight.
JSON classification logic is split to provider_preflight_json_classification.py.

Envelope handling:
The curl wrapper emits a known diagnostic envelope around provider health JSON:
  - STDOUT_BLOCK prefix (optional)
  - Valid provider health JSON
  - STDERR_BLOCK marker (optional)
  - CURL_EXIT=<code>
  - HTTP_CODE=<code>

This envelope is NON-FATAL: valid JSON + known envelope suffix → extract and parse.
Unknown contamination → provider_health_output_contaminated (hard failure).
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


def _evaluate_health_response(
    result: ProviderPreflightResult,
    curl_result: CurlResult,
    start: float,
    artifact_dir: Path,
    require_provider_configured: bool,
    require_provider_invocation_possible: bool,
) -> ProviderPreflightResult:
    """Evaluate a successful health response and determine provider state.

    This function handles the known curl wrapper envelope pattern where provider
    health JSON may be followed by metadata like CURL_EXIT=, HTTP_CODE=, and
    STDERR_BLOCK markers. Known envelope patterns are extracted and not treated
    as contamination.
    """
    try:
        health_details = json.loads(curl_result.body)
    except json.JSONDecodeError as exc:
        # JSON parse failed - try envelope extraction first
        payload = _extract_provider_health_payload(curl_result.body)

        if payload.envelope_detected:
            try:
                health_details = json.loads(payload.json_body)
            except json.JSONDecodeError:
                json_error_msg = (
                    f"line {exc.lineno}, col {exc.colno}: {exc.msg}"
                    if hasattr(exc, "lineno") else str(exc)
                )
                result.failure_class = FAILURE_PROVIDER_HEALTH_INVALID_JSON
                result.message = (
                    f"Invalid JSON response from /api/health/details (HTTP 200). "
                    f"JSON parse error: {json_error_msg}. "
                    f"Body prefix (first 200 chars): {payload.json_body[:200]!r}"
                )
                result.duration_seconds = time.time() - start
                _write_result(result, artifact_dir)
                return result
        else:
            if payload.raw_suffix:
                contamination_detail = _format_json_contamination_detail(
                    curl_result.body
                )
                result.failure_class = FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED
                result.message = (
                    f"JSON parse error: valid JSON found but output contains "
                    f"non-JSON prefix/suffix (output contamination). "
                    f"{contamination_detail}"
                )
            else:
                json_error_msg = (
                    f"line {exc.lineno}, col {exc.colno}: {exc.msg}"
                    if hasattr(exc, "lineno") else str(exc)
                )
                result.failure_class = FAILURE_PROVIDER_HEALTH_INVALID_JSON
                result.message = (
                    f"Invalid JSON response from /api/health/details (HTTP 200). "
                    f"JSON parse error: {json_error_msg}. "
                    f"Body prefix (first 200 chars): {curl_result.body[:200]!r}"
                )
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
