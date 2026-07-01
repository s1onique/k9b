"""Backend HTTP helpers for P4c K8s diagnosis phase.

This module provides HTTP communication helpers for backend-targeted diagnosis:
1. curl_backend_exec: Execute curl via kubectl exec
2. fetch_backend_incident_detail: GET incident from backend
3. invoke_targeted_automatic_diagnosis_loop: POST to trigger one-pass diagnosis

Architecture:
- Uses kubectl exec against deploy/k9b-backend -c backend for backend-local HTTP
- Does NOT rely on scheduler periodic automatic diagnosis loop
- Targets POST /api/incidents/{incident_id}/automatic-diagnosis-loop/one-pass
"""

from __future__ import annotations

import json
import shlex
import subprocess
import time
import urllib.parse

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
    FAILURE_TARGETED_INVOCATION_HTTP_ERROR,
    FAILURE_TARGETED_INVOCATION_INVALID_JSON,
    FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
    BackendIncidentDetail,
    TargetedDiagnosisInvocationResult,
)
from scripts.lab_common.constants import (
    DEFAULT_K9B_BACKEND_CONTAINER,
    DEFAULT_K9B_BACKEND_DEPLOYMENT,
    DEFAULT_K9B_BACKEND_PORT,
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
