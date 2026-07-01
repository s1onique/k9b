#!/usr/bin/env python3
"""Backend-targeted diagnosis helpers for P4c K8s diagnosis phase.

This module provides functions for:
1. Confirming incident exists in backend via kubectl exec
2. Invoking targeted one-pass diagnosis loop endpoint
3. Polling backend for persisted diagnosis state
4. Structured failure classification

Architecture:
- Uses kubectl exec against deploy/k9b-backend -c backend for backend-local HTTP
- Does NOT rely on scheduler periodic automatic diagnosis loop
- Targets POST /api/incidents/{incident_id}/automatic-diagnosis-loop/one-pass
- Do NOT use /diagnosis-loop/one-pass for OTel P4c; it is not the automatic collector path
- Validates via GET /api/incidents/{incident_id}
"""

from __future__ import annotations

import json
import shlex
import subprocess
import time
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from scripts.lab_common.constants import (
    DEFAULT_K9B_BACKEND_CONTAINER,
    DEFAULT_K9B_BACKEND_DEPLOYMENT,
    DEFAULT_K9B_BACKEND_PORT,
    PREFLIGHT_RETRY_CONNECT_TIMEOUT,
    PREFLIGHT_RETRY_MAX_TIME,
)
from scripts.lab_common.provider_curl_helpers import CurlResult

# =============================================================================
# Failure Reason Constants
# =============================================================================

FAILURE_TARGETED_INVOCATION_HTTP_ERROR = "targeted_automatic_diagnosis_invocation_http_error"
FAILURE_TARGETED_INVOCATION_INVALID_JSON = "targeted_automatic_diagnosis_invocation_invalid_json"
FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR = "targeted_automatic_diagnosis_invocation_transport_error"
FAILURE_TARGETED_LOOP_NOT_COMPLETED = "targeted_automatic_diagnosis_loop_not_completed"
FAILURE_TARGETED_NO_PASS_ARTIFACTS = "targeted_automatic_diagnosis_no_pass_artifacts"
FAILURE_TARGETED_REVIEW_PACKET_MISSING = "targeted_automatic_diagnosis_review_packet_missing"
FAILURE_TARGETED_INSUFFICIENT_PASSES = "targeted_automatic_diagnosis_insufficient_passes"

# =============================================================================
# Result Types
# =============================================================================


@dataclass
class BackendIncidentDetail:
    """Incident detail fetched from backend via GET /api/incidents/{id}."""

    incident_id: str
    status: str
    evidence_count: int
    review_packet_status: str | None
    loop_summary_status: str | None
    review_available: bool
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, incident_id: str, data: dict[str, Any]) -> BackendIncidentDetail:
        """Parse incident detail from backend API response."""
        review_packet = data.get("review_packet", {}) or {}
        loop_summary = data.get("automatic_diagnosis_loop_summary", {}) or {}
        review = data.get("automatic_diagnosis_review", {}) or {}

        return cls(
            incident_id=incident_id,
            status=data.get("status", "unknown"),
            evidence_count=data.get("evidence_count", 0),
            review_packet_status=review_packet.get("status") if isinstance(review_packet, dict) else None,
            loop_summary_status=loop_summary.get("status") if isinstance(loop_summary, dict) else None,
            review_available=review.get("available", False) if isinstance(review, dict) else False,
            raw=data,
        )

    def to_compact_log(self) -> str:
        """Return compact diagnostic log string."""
        return (
            f"incident_id={self.incident_id} "
            f"status={self.status} "
            f"evidence_count={self.evidence_count} "
            f"review_packet.status={self.review_packet_status or 'null'} "
            f"loop_summary.status={self.loop_summary_status or 'null'} "
            f"review_available={self.review_available}"
        )


@dataclass
class TargetedDiagnosisInvocationResult:
    """Result of invoking the targeted diagnosis-loop one-pass endpoint."""

    success: bool
    http_status: int
    body: str
    json_parsed: bool
    response_data: dict[str, Any] = field(default_factory=dict)
    error_class: str | None = None
    error_detail: str | None = None
    curl_rc: int | None = None
    stderr_prefix: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for evidence."""
        return {
            "success": self.success,
            "http_status": self.http_status,
            "json_parsed": self.json_parsed,
            "error_class": self.error_class,
            "error_detail": self.error_detail,
            "curl_rc": self.curl_rc,
        }


@dataclass
class TargetedDiagnosisPollResult:
    """Result of polling backend for diagnosis state."""

    success: bool
    final_status: str
    loop_summary_status: str | None
    review_available: bool
    attempts: int
    max_attempts: int
    final_detail: BackendIncidentDetail | None = None
    failure_reason: str | None = None
    error_detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for evidence."""
        return {
            "success": self.success,
            "final_status": self.final_status,
            "loop_summary_status": self.loop_summary_status,
            "review_available": self.review_available,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "failure_reason": self.failure_reason,
            "error_detail": self.error_detail,
        }


# =============================================================================
# Core Helpers
# =============================================================================


def curl_backend_exec(
    kubeconfig: str,
    namespace: str,
    target_url: str,
    timeout_seconds: int = 30,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: str | None = None,
) -> CurlResult:
    """Curl a URL from inside the backend pod via kubectl exec.

    Security hardening:
    - Uses shlex.quote() for shell-safe URL and header interpolation
    - Uses line-based parsing (CURL_EXIT=, HTTP_CODE= markers) to isolate
      curl metadata from response body

    Args:
        kubeconfig: Path to kubeconfig
        namespace: k9b namespace
        target_url: URL to curl (e.g., http://localhost:8080/api/incidents/{id})
        timeout_seconds: Timeout for curl
        method: HTTP method (GET or POST)
        headers: Additional headers
        body: Request body for POST requests

    Returns:
        CurlResult with detailed diagnostics
    """
    headers = headers or {}

    # Quote URL for shell safety
    quoted_url = shlex.quote(target_url)

    # Build header flags with proper quoting
    header_flags = " ".join(
        f"-H {shlex.quote(f'{k}: {v}')}" for k, v in headers.items()
    )

    # Build curl command
    method_flag = "-X POST" if method == "POST" else ""
    body_flag = f"--data {shlex.quote(body)}" if body else ""
    curl_cmd = f"curl -sS -o /tmp/resp.txt -w '%{{http_code}}' \
    --connect-timeout {PREFLIGHT_RETRY_CONNECT_TIMEOUT} \
    --max-time {PREFLIGHT_RETRY_MAX_TIME} \
    {method_flag} \
    {header_flags} \
    {body_flag} \
    {quoted_url}"

    exec_cmd = [
        "kubectl", "--kubeconfig", kubeconfig, "exec",
        "-n", namespace,
        f"deploy/{DEFAULT_K9B_BACKEND_DEPLOYMENT}",
        "-c", DEFAULT_K9B_BACKEND_CONTAINER,
        "--",
        "sh", "-c",
        f"""
code=$({curl_cmd})
curl_rc=$?
echo CURL_EXIT=$curl_rc
echo HTTP_CODE=$code
cat /tmp/resp.txt 2>/dev/null || true
exit 0
""",
    ]

    try:
        exec_result = subprocess.run(
            exec_cmd, capture_output=True, text=True, timeout=timeout_seconds + 5
        )
    except subprocess.TimeoutExpired:
        return CurlResult(
            success=False,
            body="Exec timeout",
            http_code=0,
            curl_rc=None,
            stderr="Timeout expired",
        )

    # Parse output
    http_code = 0
    curl_rc: int | None = None
    body_parts: list[str] = []

    for line in exec_result.stdout.split("\n"):
        if "CURL_EXIT=" in line:
            try:
                curl_rc = int(line.split("CURL_EXIT=")[1].strip())
            except (ValueError, IndexError):
                pass
        elif "HTTP_CODE=" in line:
            try:
                http_code = int(line.split("HTTP_CODE=")[1].strip())
            except (ValueError, IndexError):
                pass
        else:
            body_parts.append(line)

    body = "\n".join(body_parts)
    stderr = exec_result.stderr[:200] if exec_result.stderr else ""

    success = curl_rc == 0 and 200 <= http_code < 400

    return CurlResult(
        success=success,
        body=body,
        http_code=http_code,
        curl_rc=curl_rc,
        stderr=stderr,
    )


def fetch_backend_incident_detail(
    kubeconfig: str,
    namespace: str,
    incident_id: str,
    backend_port: int = DEFAULT_K9B_BACKEND_PORT,
) -> BackendIncidentDetail | None:
    """Fetch incident detail from backend via kubectl exec.

    Args:
        kubeconfig: Path to kubeconfig
        namespace: k9b namespace
        incident_id: Incident ID to fetch
        backend_port: Backend port (default: 8080)

    Returns:
        BackendIncidentDetail or None on failure
    """
    encoded_id = urllib.parse.quote(incident_id, safe="")
    url = f"http://localhost:{backend_port}/api/incidents/{encoded_id}"

    curl_result = curl_backend_exec(
        kubeconfig=kubeconfig,
        namespace=namespace,
        target_url=url,
        timeout_seconds=30,
    )

    if curl_result.http_code == 0 or curl_result.curl_rc != 0:
        return None

    try:
        data = json.loads(curl_result.body)
        return BackendIncidentDetail.from_dict(incident_id, data)
    except json.JSONDecodeError:
        return None


def invoke_targeted_automatic_diagnosis_loop(
    kubeconfig: str,
    namespace: str,
    incident_id: str,
    backend_port: int = DEFAULT_K9B_BACKEND_PORT,
) -> TargetedDiagnosisInvocationResult:
    """Invoke the targeted automatic diagnosis-loop one-pass endpoint.

    Targets: POST /api/incidents/{incident_id}/automatic-diagnosis-loop/one-pass

    This endpoint wraps collect_automatic_diagnosis_evidence() and uses the
    REAL automatic diagnosis loop collector. Do NOT use /diagnosis-loop/one-pass;
    it is not the automatic collector path.

    Args:
        kubeconfig: Path to kubeconfig
        namespace: k9b namespace
        incident_id: Incident ID to diagnose
        backend_port: Backend port (default: 8080)

    Returns:
        TargetedDiagnosisInvocationResult with invocation details
    """
    encoded_id = urllib.parse.quote(incident_id, safe="")
    url = f"http://localhost:{backend_port}/api/incidents/{encoded_id}/automatic-diagnosis-loop/one-pass"

    headers = {"Content-Type": "application/json"}

    # Minimal request body - the backend will handle diagnosis
    request_body = json.dumps({
        "run_id": f"p4c-target-{int(time.time())}",
        "diagnosis_report": {
            "diagnosis": {
                "recommended_investigations": []
            }
        }
    })

    curl_result = curl_backend_exec(
        kubeconfig=kubeconfig,
        namespace=namespace,
        target_url=url,
        timeout_seconds=60,
        method="POST",
        headers=headers,
        body=request_body,
    )

    # Classify failure
    if curl_result.http_code == 0 or (curl_result.curl_rc is not None and curl_result.curl_rc != 0):
        return TargetedDiagnosisInvocationResult(
            success=False,
            http_status=curl_result.http_code,
            body=curl_result.body[:500],
            json_parsed=False,
            error_class=FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
            error_detail=f"Transport error: curl_rc={curl_result.curl_rc}, http_code={curl_result.http_code}",
            curl_rc=curl_result.curl_rc,
            stderr_prefix=curl_result.stderr[:100],
        )

    # Check for non-2xx
    if curl_result.http_code < 200 or curl_result.http_code >= 300:
        return TargetedDiagnosisInvocationResult(
            success=False,
            http_status=curl_result.http_code,
            body=curl_result.body[:500],
            json_parsed=False,
            error_class=FAILURE_TARGETED_INVOCATION_HTTP_ERROR,
            error_detail=f"HTTP {curl_result.http_code}",
            curl_rc=curl_result.curl_rc,
            stderr_prefix=curl_result.stderr[:100],
        )

    # Try to parse JSON
    try:
        response_data = json.loads(curl_result.body)
        return TargetedDiagnosisInvocationResult(
            success=True,
            http_status=curl_result.http_code,
            body=curl_result.body,
            json_parsed=True,
            response_data=response_data,
        )
    except json.JSONDecodeError as e:
        return TargetedDiagnosisInvocationResult(
            success=False,
            http_status=curl_result.http_code,
            body=curl_result.body[:500],
            json_parsed=False,
            error_class=FAILURE_TARGETED_INVOCATION_INVALID_JSON,
            error_detail=f"JSON parse error: {e}",
            curl_rc=curl_result.curl_rc,
            stderr_prefix=curl_result.stderr[:100],
        )


def poll_backend_diagnosis_state(
    kubeconfig: str,
    namespace: str,
    incident_id: str,
    max_attempts: int = 12,
    poll_interval_seconds: float = 5.0,
    backend_port: int = DEFAULT_K9B_BACKEND_PORT,
    log_callback: Callable[[str], None] | None = None,
) -> TargetedDiagnosisPollResult:
    """Poll backend incident detail until diagnosis completes.

    Args:
        kubeconfig: Path to kubeconfig
        namespace: k9b namespace
        incident_id: Incident ID to poll
        max_attempts: Maximum poll attempts (default: 12 * 5s = 60s)
        poll_interval_seconds: Interval between polls (default: 5s)
        backend_port: Backend port (default: 8080)
        log_callback: Optional callback for logging each poll attempt

    Returns:
        TargetedDiagnosisPollResult with final state
    """
    for attempt in range(1, max_attempts + 1):
        # Fetch current incident detail
        detail = fetch_backend_incident_detail(
            kubeconfig=kubeconfig,
            namespace=namespace,
            incident_id=incident_id,
            backend_port=backend_port,
        )

        if detail is None:
            # Transport error - continue polling
            if log_callback:
                log_callback(
                    f"P4c diagnosis poll {attempt}/{max_attempts}: "
                    f"transport error fetching incident detail"
                )
        else:
            # Log compact status
            if log_callback:
                log_callback(
                    f"P4c diagnosis poll {attempt}/{max_attempts}: "
                    f"incident.status={detail.status} "
                    f"loop_summary.status={detail.loop_summary_status or 'null'} "
                    f"review_available={detail.review_available}"
                )

            # Check for completion
            loop_status = detail.loop_summary_status
            if loop_status == "completed":
                return TargetedDiagnosisPollResult(
                    success=True,
                    final_status=detail.status,
                    loop_summary_status=loop_status,
                    review_available=detail.review_available,
                    attempts=attempt,
                    max_attempts=max_attempts,
                    final_detail=detail,
                )

            # Also accept review_available as completion signal
            if detail.review_available:
                return TargetedDiagnosisPollResult(
                    success=True,
                    final_status=detail.status,
                    loop_summary_status=loop_status,
                    review_available=True,
                    attempts=attempt,
                    max_attempts=max_attempts,
                    final_detail=detail,
                )

        # Wait before next poll
        if attempt < max_attempts:
            time.sleep(poll_interval_seconds)

    # Timeout - return failure state
    final_detail = fetch_backend_incident_detail(
        kubeconfig=kubeconfig,
        namespace=namespace,
        incident_id=incident_id,
        backend_port=backend_port,
    )

    return TargetedDiagnosisPollResult(
        success=False,
        final_status=final_detail.status if final_detail else "unknown",
        loop_summary_status=final_detail.loop_summary_status if final_detail else None,
        review_available=final_detail.review_available if final_detail else False,
        attempts=max_attempts,
        max_attempts=max_attempts,
        final_detail=final_detail,
        failure_reason=FAILURE_TARGETED_LOOP_NOT_COMPLETED,
        error_detail=f"Polling timeout after {max_attempts} attempts",
    )


def check_pass_artifacts_in_backend(
    kubeconfig: str,
    namespace: str,
    incident_id: str,
    min_required_passes: int = 2,
    backend_port: int = DEFAULT_K9B_BACKEND_PORT,
) -> tuple[bool, int, list[str]]:
    """Check if pass artifacts exist for an incident in backend.

    Args:
        kubeconfig: Path to kubeconfig
        namespace: k9b namespace
        incident_id: Incident ID to check
        min_required_passes: Minimum required passes (default: 2)
        backend_port: Backend port (default: 8080)

    Returns:
        Tuple of (has_sufficient_passes, pass_count, pass_run_ids)
    """
    detail = fetch_backend_incident_detail(
        kubeconfig=kubeconfig,
        namespace=namespace,
        incident_id=incident_id,
        backend_port=backend_port,
    )

    if detail is None:
        return False, 0, []

    # Check loop summary for pass count
    loop_summary = detail.raw.get("automatic_diagnosis_loop_summary", {}) or {}

    # Try to extract pass count from various fields
    pass_count = 0
    pass_run_ids: list[str] = []

    # Check pass_run_ids in loop summary
    if "pass_run_ids" in loop_summary:
        pass_run_ids = loop_summary["pass_run_ids"] or []
        pass_count = len(pass_run_ids)
    elif "pass_count" in loop_summary:
        pass_count = loop_summary["pass_count"] or 0

    # Check incident for pass artifacts info
    if pass_count == 0 and "pass_run_ids" in detail.raw:
        pass_run_ids = detail.raw["pass_run_ids"] or []
        pass_count = len(pass_run_ids)

    has_sufficient = pass_count >= min_required_passes

    return has_sufficient, pass_count, pass_run_ids
