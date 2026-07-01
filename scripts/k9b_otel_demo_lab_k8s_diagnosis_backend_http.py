"""Backend HTTP helpers for P4c K8s diagnosis phase.

Compatibility façade; implementation lives in focused modules:
- k9b_otel_demo_lab_k8s_diagnosis_backend_http_contracts: contracts only
- k9b_otel_demo_lab_k8s_diagnosis_backend_http_classify: failure classification
- k9b_otel_demo_lab_k8s_diagnosis_backend_http_parse: response parsing
- k9b_otel_demo_lab_k8s_diagnosis_backend_http_fetch: fetch orchestration

This module provides the curl_backend_exec() function which is shared across
modules, and thin re-exports for backward compatibility.
"""

from __future__ import annotations

import shlex
import subprocess

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
    FAILURE_BACKEND_INCIDENT_FETCH_CONTRACT_ERROR,
    FAILURE_BACKEND_INCIDENT_FETCH_HTTP_ERROR,
    FAILURE_BACKEND_INCIDENT_FETCH_INVALID_JSON,
    FAILURE_BACKEND_INCIDENT_FETCH_NOT_FOUND,
    FAILURE_BACKEND_INCIDENT_FETCH_TRANSPORT_ERROR,
    FAILURE_TARGETED_INVOCATION_HTTP_ERROR,
    FAILURE_TARGETED_INVOCATION_INVALID_JSON,
    FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
    FAILURE_TARGETED_LOOP_BACKEND_EMPTY_REPLY,
    FAILURE_TARGETED_LOOP_NOT_ELIGIBLE,
    BackendIncidentDetail,
    BackendIncidentFetchResult,
    TargetedDiagnosisInvocationResult,
)
from scripts.lab_common.constants import (
    DEFAULT_K9B_BACKEND_CONTAINER,
    DEFAULT_K9B_BACKEND_DEPLOYMENT,
    PREFLIGHT_RETRY_CONNECT_TIMEOUT,
    PREFLIGHT_RETRY_MAX_TIME,
)
from scripts.lab_common.provider_curl_helpers import CurlResult


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
        CurlResult with detailed diagnostics. curl_rc is always an integer
        (not None) when curl was executed, even on failure. curl_rc=None
        is reserved for the distinct case where curl was not executed
        (e.g., due to subprocess.TimeoutExpired exception).
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
        # curl was NOT executed due to exception - this is the ONLY case where curl_rc=None
        return CurlResult(
            success=False,
            body="Exec timeout",
            http_code=0,
            curl_rc=None,  # curl was not executed
            stderr="Timeout expired during kubectl exec",
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
                # Failed to parse curl_rc - this shouldn't happen if curl ran
                # but we handle it gracefully
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

    # If curl_rc is still None after parsing, curl was not executed properly
    # This is distinct from curl_rc=0 (success) or curl_rc!=0 (curl error)
    if curl_rc is None:
        return CurlResult(
            success=False,
            body=body,
            http_code=http_code,
            curl_rc=None,  # curl was not executed properly
            stderr=f"{stderr}; parse error: CURL_EXIT marker not found".strip(),
        )

    success = curl_rc == 0 and 200 <= http_code < 400

    return CurlResult(
        success=success,
        body=body,
        http_code=http_code,
        curl_rc=curl_rc,
        stderr=stderr,
    )


# Re-export for backward compatibility
from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http_fetch import (
    fetch_backend_incident_detail,
    fetch_backend_incident_detail_result,
    invoke_targeted_automatic_diagnosis_loop,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_urls import (
    _build_backend_url,
    _build_targeted_diagnosis_url,
)

__all__ = [
    "BackendIncidentDetail",
    "BackendIncidentFetchResult",
    "TargetedDiagnosisInvocationResult",
    "_build_backend_url",
    "_build_targeted_diagnosis_url",
    "curl_backend_exec",
    "fetch_backend_incident_detail",
    "fetch_backend_incident_detail_result",
    "invoke_targeted_automatic_diagnosis_loop",
    # Re-exported failure constants for convenience
    "FAILURE_BACKEND_INCIDENT_FETCH_CONTRACT_ERROR",
    "FAILURE_BACKEND_INCIDENT_FETCH_HTTP_ERROR",
    "FAILURE_BACKEND_INCIDENT_FETCH_INVALID_JSON",
    "FAILURE_BACKEND_INCIDENT_FETCH_NOT_FOUND",
    "FAILURE_BACKEND_INCIDENT_FETCH_TRANSPORT_ERROR",
    "FAILURE_TARGETED_INVOCATION_HTTP_ERROR",
    "FAILURE_TARGETED_INVOCATION_INVALID_JSON",
    "FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR",
    "FAILURE_TARGETED_LOOP_BACKEND_EMPTY_REPLY",
    "FAILURE_TARGETED_LOOP_NOT_ELIGIBLE",
]
