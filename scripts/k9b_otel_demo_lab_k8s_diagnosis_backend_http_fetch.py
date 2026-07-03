"""Backend incident fetch orchestration for OTel demo lab.

This module extracts the fetch orchestration logic from
k9b_otel_demo_lab_k8s_diagnosis_backend_http.py.

It orchestrates the fetch workflow:
1. Execute curl via kubectl exec
2. Classify failure modes using classify helpers
3. Parse response using parse helpers
4. Return rich BackendIncidentFetchResult
"""

from __future__ import annotations

import json
import time
from typing import Any

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
    FAILURE_BACKEND_INCIDENT_FETCH_CONTRACT_ERROR,
    FAILURE_BACKEND_INCIDENT_FETCH_HTTP_ERROR,
    FAILURE_BACKEND_INCIDENT_FETCH_INVALID_JSON,
    FAILURE_BACKEND_INCIDENT_FETCH_NOT_FOUND,
    FAILURE_BACKEND_INCIDENT_FETCH_TRANSPORT_ERROR,
    FAILURE_TARGETED_INVOCATION_HTTP_ERROR,
    FAILURE_TARGETED_INVOCATION_INVALID_JSON,
    FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
    FAILURE_TARGETED_LOOP_NOT_ELIGIBLE,
    BackendIncidentDetail,
    BackendIncidentFetchResult,
    TargetedDiagnosisInvocationResult,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http_classify import (
    classify_backend_fetch_failure,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http_parse import (
    extract_backend_incident_detail_json,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_urls import (
    _build_backend_url,
    _build_targeted_diagnosis_url,
)
from scripts.lab_common.constants import DEFAULT_K9B_BACKEND_PORT


def fetch_backend_incident_detail_result(
    kubeconfig: str,
    namespace: str,
    incident_id: str,
    backend_port: int = DEFAULT_K9B_BACKEND_PORT,
) -> BackendIncidentFetchResult:
    """Fetch incident detail from backend with precise failure classification.

    This function provides richer diagnostics than fetch_backend_incident_detail()
    by returning a BackendIncidentFetchResult with precise error classification.

    Uses namespace-qualified Kubernetes Service DNS to ensure the backend
    is reachable from any namespace.

    Args:
        kubeconfig: Path to kubeconfig
        namespace: k9b namespace
        incident_id: Incident ID to fetch
        backend_port: Backend port (default: 8080)

    Returns:
        BackendIncidentFetchResult with detailed diagnostics and error classification.
    """
    # Lazy import to avoid circular dependency
    from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http import curl_backend_exec

    url, api_path, encoded_id = _build_backend_url(namespace, incident_id, backend_port)

    curl_result = curl_backend_exec(
        kubeconfig=kubeconfig,
        namespace=namespace,
        target_url=url,
        timeout_seconds=30,
    )

    # Capture body and stderr prefixes for diagnostics (bounded)
    body_prefix = curl_result.body[:200] if curl_result.body else ""
    stderr_prefix = curl_result.stderr[:200] if curl_result.stderr else ""

    # Step 0: Check if curl was executed (curl_rc should not be None if curl ran)
    # If curl_rc is None, it means curl_backend_exec hit an exception
    if curl_result.curl_rc is None:
        return BackendIncidentFetchResult(
            success=False,
            error_class=FAILURE_BACKEND_INCIDENT_FETCH_TRANSPORT_ERROR,
            error_detail=f"Transport error: curl not executed, exec timeout or exception. stderr={curl_result.stderr[:100]!r}",
            http_status=curl_result.http_code,
            curl_rc=None,  # Intentionally None - curl was not executed
            url=url,
            api_path=api_path,
            encoded_incident_id=encoded_id,
            body_prefix=body_prefix,
            stderr_prefix=stderr_prefix,
        )

    # Step 1: Transport error (http_code=0 or nonzero curl_rc)
    if curl_result.http_code == 0 or curl_result.curl_rc != 0:
        error_class, error_detail = classify_backend_fetch_failure(curl_result)
        return BackendIncidentFetchResult(
            success=False,
            error_class=error_class,
            error_detail=error_detail,
            http_status=curl_result.http_code,
            curl_rc=curl_result.curl_rc,
            url=url,
            api_path=api_path,
            encoded_incident_id=encoded_id,
            body_prefix=body_prefix,
            stderr_prefix=stderr_prefix,
        )

    # Step 2: HTTP error - check for 404 not found
    if curl_result.http_code == 404:
        return BackendIncidentFetchResult(
            success=False,
            error_class=FAILURE_BACKEND_INCIDENT_FETCH_NOT_FOUND,
            error_detail="Incident not found: HTTP 404",
            http_status=curl_result.http_code,
            curl_rc=curl_result.curl_rc,
            url=url,
            api_path=api_path,
            encoded_incident_id=encoded_id,
            body_prefix=body_prefix,
            stderr_prefix=stderr_prefix,
        )

    # Step 3: Other non-2xx HTTP errors
    if curl_result.http_code < 200 or curl_result.http_code >= 300:
        return BackendIncidentFetchResult(
            success=False,
            error_class=FAILURE_BACKEND_INCIDENT_FETCH_HTTP_ERROR,
            error_detail=f"HTTP error: {curl_result.http_code}",
            http_status=curl_result.http_code,
            curl_rc=curl_result.curl_rc,
            url=url,
            api_path=api_path,
            encoded_incident_id=encoded_id,
            body_prefix=body_prefix,
            stderr_prefix=stderr_prefix,
        )

    # Step 4: 2xx response - parse JSON
    incident, json_error, contract_error = extract_backend_incident_detail_json(
        body=curl_result.body,
        incident_id=incident_id,
    )

    if json_error is not None:
        return BackendIncidentFetchResult(
            success=False,
            error_class=FAILURE_BACKEND_INCIDENT_FETCH_INVALID_JSON,
            error_detail=json_error,
            http_status=curl_result.http_code,
            curl_rc=curl_result.curl_rc,
            url=url,
            api_path=api_path,
            encoded_incident_id=encoded_id,
            body_prefix=body_prefix,
            stderr_prefix=stderr_prefix,
            json_error=json_error,
        )

    if contract_error is not None:
        return BackendIncidentFetchResult(
            success=False,
            error_class=FAILURE_BACKEND_INCIDENT_FETCH_CONTRACT_ERROR,
            error_detail=contract_error,
            http_status=curl_result.http_code,
            curl_rc=curl_result.curl_rc,
            url=url,
            api_path=api_path,
            encoded_incident_id=encoded_id,
            body_prefix=body_prefix[:100],  # Already valid JSON, show first 100
            stderr_prefix=stderr_prefix,
        )

    # Success
    return BackendIncidentFetchResult(
        success=True,
        incident=incident,
        http_status=curl_result.http_code,
        curl_rc=curl_result.curl_rc,
        url=url,
        api_path=api_path,
        encoded_incident_id=encoded_id,
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
    result = fetch_backend_incident_detail_result(
        kubeconfig=kubeconfig,
        namespace=namespace,
        incident_id=incident_id,
        backend_port=backend_port,
    )
    return result.incident


def invoke_targeted_automatic_diagnosis_loop(
    kubeconfig: str,
    namespace: str,
    incident_id: str,
    backend_port: int = DEFAULT_K9B_BACKEND_PORT,
    max_passes_per_incident: int = 5,
    require_complete_root_cause_before_stop: bool = False,
) -> TargetedDiagnosisInvocationResult:
    """Invoke the targeted automatic diagnosis-loop one-pass endpoint.

    Targets: POST /api/incidents/{incident_id}/automatic-diagnosis-loop/one-pass

    This endpoint wraps collect_automatic_diagnosis_evidence() and uses the
    REAL automatic diagnosis loop collector. Do NOT use /diagnosis-loop/one-pass;
    it is not the automatic collector path.

    Uses namespace-qualified Kubernetes Service DNS to ensure the backend
    is reachable from any namespace.

    Precise failure classification:
    - curl_rc=52, http_code=0 -> backend empty reply / handler crashed
    - curl_rc!=0 with DNS/connect failure -> transport_error
    - HTTP non-2xx -> http_error
    - HTTP 2xx with invalid JSON -> invalid_json
    - HTTP 2xx with skipped=True, eligible=False -> loop_not_eligible (budget_exhausted)
    - HTTP 2xx with valid JSON and eligible=True -> success

    Args:
        kubeconfig: Path to kubeconfig
        namespace: Namespace where k9b backend runs
        incident_id: Incident ID to diagnose
        backend_port: Backend port (default: 8080)
        max_passes_per_incident: Budget limit for passes per incident (default: 5).
            For lab scenarios requiring multiple passes, this should be >= MIN_REQUIRED_PASSES.
            The backend eligibility check uses this to determine if the incident is eligible.
        require_complete_root_cause_before_stop: If True (P4c lab-strict mode),
            stop_no_checks_proposed requires complete scheduling root cause evidence.
            This prevents premature termination before the diagnosis reaches
            a complete root-cause understanding.

    Returns:
        TargetedDiagnosisInvocationResult with invocation details
    """
    from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http import curl_backend_exec
    from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http_classify import (
        classify_targeted_invocation_failure,
    )

    url, api_path = _build_targeted_diagnosis_url(namespace, incident_id, backend_port)

    headers = {"Content-Type": "application/json"}

    # Request body with budget config for lab scenarios
    # The backend uses max_passes_per_incident as the budget limit for eligibility.
    # For P4c with MIN_REQUIRED_PASSES=2, we need budget >= 2 to allow pass 2.
    #
    # P4c lab-strict mode: require_complete_root_cause_before_stop ensures that
    # stop_no_checks_proposed is only accepted when the diagnosis contains complete
    # scheduling root cause evidence (shipping, nodeSelector, k9b.dev/otel-lab-node, FailedScheduling).
    request_body = json.dumps({
        "run_id": f"p4c-target-{int(time.time())}",
        "max_passes_per_incident": max_passes_per_incident,
        "require_complete_root_cause_before_stop": require_complete_root_cause_before_stop,
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

    # Check if curl was executed (curl_rc should not be None if curl ran)
    if curl_result.curl_rc is None:
        return TargetedDiagnosisInvocationResult(
            success=False,
            http_status=curl_result.http_code,
            body=curl_result.body[:500],
            json_parsed=False,
            error_class=FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
            error_detail=f"Transport error: curl not executed, exec timeout or exception. stderr={curl_result.stderr[:100]!r}",
            curl_rc=None,
            stderr_prefix=curl_result.stderr[:100],
        )

    # Try to parse JSON first (needed for structured classification)
    response_data: dict[str, Any] | None = None
    json_error: str | None = None
    try:
        response_data = json.loads(curl_result.body)
    except json.JSONDecodeError as e:
        json_error = str(e)

    # Check for specific failure patterns using precise classification
    # Only proceed to JSON/response checks if we have a valid HTTP response
    if curl_result.http_code == 0 or curl_result.curl_rc != 0:
        error_class, error_detail = classify_targeted_invocation_failure(curl_result, response_data)
        return TargetedDiagnosisInvocationResult(
            success=False,
            http_status=curl_result.http_code,
            body=curl_result.body[:500],
            json_parsed=False,
            error_class=error_class,
            error_detail=error_detail,
            curl_rc=curl_result.curl_rc,
            stderr_prefix=curl_result.stderr[:100],
        )

    # HTTP non-2xx
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

    # HTTP 2xx but invalid JSON
    if json_error is not None:
        return TargetedDiagnosisInvocationResult(
            success=False,
            http_status=curl_result.http_code,
            body=curl_result.body[:500],
            json_parsed=False,
            error_class=FAILURE_TARGETED_INVOCATION_INVALID_JSON,
            error_detail=f"JSON parse error: {json_error}",
            curl_rc=curl_result.curl_rc,
            stderr_prefix=curl_result.stderr[:100],
        )

    # HTTP 2xx with valid JSON - check for structured skip/not eligible
    if response_data is not None:
        # Check for budget_exhausted / not eligible response
        skipped = response_data.get("skipped", False)
        eligible = response_data.get("eligible", True)

        if skipped and not eligible:
            # Extract budget diagnostics from response for debugging
            budget_diagnostics = response_data.get("budget_diagnostics", [])
            if not isinstance(budget_diagnostics, list):
                budget_diagnostics = []

            # Structured "not eligible" response - this is expected runtime behavior
            # Return as success with detailed response_data for caller to handle
            return TargetedDiagnosisInvocationResult(
                success=True,  # HTTP succeeded, response is structured
                http_status=curl_result.http_code,
                body=curl_result.body,
                json_parsed=True,
                response_data=response_data,
                # Include classification info for clarity
                error_class=FAILURE_TARGETED_LOOP_NOT_ELIGIBLE,
                error_detail=f"Loop not eligible: {response_data.get('eligibility_reason', 'unknown')}",
                budget_diagnostics=budget_diagnostics,
            )

        # Successful response with valid JSON
        return TargetedDiagnosisInvocationResult(
            success=True,
            http_status=curl_result.http_code,
            body=curl_result.body,
            json_parsed=True,
            response_data=response_data,
        )

    # Should not reach here, but handle gracefully
    return TargetedDiagnosisInvocationResult(
        success=False,
        http_status=curl_result.http_code,
        body=curl_result.body[:500],
        json_parsed=False,
        error_class=FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
        error_detail="Unexpected state: HTTP 2xx with no JSON and no transport error",
        curl_rc=curl_result.curl_rc,
        stderr_prefix=curl_result.stderr[:100],
    )


__all__ = [
    "fetch_backend_incident_detail",
    "fetch_backend_incident_detail_result",
    "invoke_targeted_automatic_diagnosis_loop",
]
