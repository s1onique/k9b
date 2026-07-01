"""Backend retry helpers for P4c K8s diagnosis phase.

This module provides retry logic for backend-targeted diagnosis:
1. fetch_backend_incident_detail_with_retry: Fetch with exponential backoff
2. _is_backend_fetch_retryable: Determine if a failure is retryable

Retry behavior:
- Bounded retry for up to 60s with exponential backoff
- Backoff sequence: 0.25s, 0.5s, 1.0s, 2.0s, 4.0s, 8s...
- Retries: HTTP 0, connection failures, invalid JSON
- After retries exhausted, classifies based on curl_rc:
  - curl_rc=6  -> backend_dns_resolution_failed
  - curl_rc=7  -> backend_endpoint_not_ready
  - curl_rc=28 -> backend_incident_fetch_transport_error
  - http=000   -> backend_endpoint_not_ready
  - 2xx invalid JSON -> backend_incident_fetch_invalid_json
"""

from __future__ import annotations

import time

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
    FAILURE_BACKEND_DNS_RESOLUTION_FAILED,
    FAILURE_BACKEND_ENDPOINT_NOT_READY,
    FAILURE_BACKEND_INCIDENT_FETCH_CONTRACT_ERROR,
    FAILURE_BACKEND_INCIDENT_FETCH_HTTP_ERROR,
    FAILURE_BACKEND_INCIDENT_FETCH_NOT_FOUND,
    FAILURE_BACKEND_INCIDENT_FETCH_TRANSPORT_ERROR,
    BackendIncidentFetchResult,
)
from scripts.lab_common.constants import (
    DEFAULT_K9B_BACKEND_PORT,
    P4C_BACKEND_RETRY_DEADLINE_SECONDS,
    P4C_BACKEND_RETRY_INITIAL_SLEEP_SECONDS,
    P4C_BACKEND_RETRY_MAX_SLEEP_SECONDS,
)


def _is_backend_fetch_retryable(result: BackendIncidentFetchResult) -> bool:
    """Check if a backend incident fetch result should be retried.
    
    Retry conditions:
    - Transport error (HTTP 0, connection failure)
    - Invalid JSON (service started but not fully ready)
    
    Do NOT retry:
    - 404 not found (incident doesn't exist)
    - Other HTTP errors (application errors, not transient)
    - Contract errors (malformed response structure)
    """
    if result.success:
        return False  # Already successful, no need to retry
    
    if result.error_class == FAILURE_BACKEND_INCIDENT_FETCH_NOT_FOUND:
        return False  # Not found is permanent, don't retry
    
    if result.error_class in (
        FAILURE_BACKEND_INCIDENT_FETCH_HTTP_ERROR,
        FAILURE_BACKEND_INCIDENT_FETCH_CONTRACT_ERROR,
    ):
        return False  # Application errors are not retryable
    
    # Retry: transport error, invalid JSON
    return True


def fetch_backend_incident_detail_with_retry(
    kubeconfig: str,
    namespace: str,
    incident_id: str,
    backend_port: int = DEFAULT_K9B_BACKEND_PORT,
) -> BackendIncidentFetchResult:
    """Fetch incident detail from backend with exponential backoff retry.
    
    This wrapper adds retry behavior to handle transient failures that occur
    with single-replica backends during rollout or readiness transitions:
    - HTTP 0 (service not ready)
    - Connection failures (endpoint not ready)
    - Invalid JSON (service started but not fully initialized)
    
    Retry behavior:
    - Bounded retry for up to 60s with exponential backoff
    - Backoff sequence: 0.25s, 0.5s, 1.0s, 2.0s, 4.0s, 8s...
    - After retries exhausted, classifies based on curl_rc:
      - curl_rc=6  -> backend_dns_resolution_failed
      - curl_rc=7  -> backend_endpoint_not_ready  
      - curl_rc=28 -> backend_incident_fetch_transport_error
      - http=000   -> backend_endpoint_not_ready
      - 2xx invalid JSON -> backend_incident_fetch_invalid_json
    
    Args:
        kubeconfig: Path to kubeconfig
        namespace: k9b namespace
        incident_id: Incident ID to fetch
        backend_port: Backend port (default: 8080)
        
    Returns:
        BackendIncidentFetchResult with detailed diagnostics and error classification.
    """
    # Import here to avoid circular dependency at module level
    from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http import (
        fetch_backend_incident_detail_result,
    )
    
    deadline = time.time() + P4C_BACKEND_RETRY_DEADLINE_SECONDS
    attempt = 0
    sleep_s: float = float(P4C_BACKEND_RETRY_INITIAL_SLEEP_SECONDS)
    last_result: BackendIncidentFetchResult | None = None
    
    while time.time() < deadline:
        attempt += 1
        
        result = fetch_backend_incident_detail_result(
            kubeconfig=kubeconfig,
            namespace=namespace,
            incident_id=incident_id,
            backend_port=backend_port,
        )
        last_result = result
        
        # Success - return immediately
        if result.success:
            return result
        
        # Not retryable (404, HTTP errors, contract errors)
        if not _is_backend_fetch_retryable(result):
            return result
        
        # Calculate sleep time with exponential backoff
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        
        sleep_for = min(sleep_s, remaining)
        if sleep_for > 0:
            time.sleep(sleep_for)
        
        # Increase backoff for next iteration
        if sleep_s < P4C_BACKEND_RETRY_MAX_SLEEP_SECONDS:
            sleep_s = min(sleep_s * 2, P4C_BACKEND_RETRY_MAX_SLEEP_SECONDS)
    
    # Retry deadline exceeded - classify the final failure
    if last_result is None:
        return BackendIncidentFetchResult(
            success=False,
            error_class=FAILURE_BACKEND_INCIDENT_FETCH_TRANSPORT_ERROR,
            error_detail=f"Retry deadline exceeded after {attempt} attempts",
        )
    
    # Classify based on curl_rc
    curl_rc = last_result.curl_rc
    
    if curl_rc == 6:
        # DNS resolution failed
        return BackendIncidentFetchResult(
            success=False,
            error_class=FAILURE_BACKEND_DNS_RESOLUTION_FAILED,
            error_detail=f"DNS resolution failed after {attempt} attempts: curl_rc={curl_rc}",
            http_status=last_result.http_status,
            curl_rc=curl_rc,
            url=last_result.url,
            api_path=last_result.api_path,
            encoded_incident_id=last_result.encoded_incident_id,
            body_prefix=last_result.body_prefix,
            stderr_prefix=last_result.stderr_prefix,
        )
    
    if curl_rc == 7 or last_result.http_status == 0:
        # Connection refused or HTTP 0 - endpoint not ready
        return BackendIncidentFetchResult(
            success=False,
            error_class=FAILURE_BACKEND_ENDPOINT_NOT_READY,
            error_detail=f"Backend endpoint not ready after {attempt} attempts: curl_rc={curl_rc}",
            http_status=last_result.http_status,
            curl_rc=curl_rc,
            url=last_result.url,
            api_path=last_result.api_path,
            encoded_incident_id=last_result.encoded_incident_id,
            body_prefix=last_result.body_prefix,
            stderr_prefix=last_result.stderr_prefix,
        )
    
    if curl_rc == 28:
        # Timeout
        return BackendIncidentFetchResult(
            success=False,
            error_class=FAILURE_BACKEND_INCIDENT_FETCH_TRANSPORT_ERROR,
            error_detail=f"Request timeout after {attempt} attempts: curl_rc={curl_rc}",
            http_status=last_result.http_status,
            curl_rc=curl_rc,
            url=last_result.url,
            api_path=last_result.api_path,
            encoded_incident_id=last_result.encoded_incident_id,
            body_prefix=last_result.body_prefix,
            stderr_prefix=last_result.stderr_prefix,
        )
    
    # Return the last result for other error types
    return last_result
