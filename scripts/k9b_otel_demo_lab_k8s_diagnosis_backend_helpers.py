"""Backend-targeted diagnosis helpers for P4c K8s diagnosis phase.

This module is a thin compatibility façade that re-exports the public API
from the extracted backend helper modules.

Architecture:
- Uses kubectl exec against deploy/k9b-backend -c backend for backend-local HTTP
- Does NOT rely on scheduler periodic automatic diagnosis loop
- Targets POST /api/incidents/{incident_id}/automatic-diagnosis-loop/one-pass

Retry behavior:
- fetch_backend_incident_detail_with_retry() adds exponential backoff for
  transient DNS/endpoint/HTTP failures that occur with single-replica backends
- Bounded retry for up to 60s with exponential backoff (0.25s, 0.5s, 1.0s, 2.0s, 4.0s...)
- Retries: HTTP 0, connection failures, invalid JSON
- After retries exhausted, classifies based on curl_rc

For the actual implementation, see:
- k9b_otel_demo_lab_k8s_diagnosis_backend_contracts: dataclasses/constants
- k9b_otel_demo_lab_k8s_diagnosis_backend_http: HTTP helpers
- k9b_otel_demo_lab_k8s_diagnosis_backend_artifacts: artifact helpers
- k9b_otel_demo_lab_k8s_diagnosis_backend_poll: polling helpers
- k9b_otel_demo_lab_k8s_diagnosis_budget_reset: budget reset for live-lab
"""

from __future__ import annotations

# Re-export artifact helpers
from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_artifacts import (
    check_pass_artifacts_in_backend,
)

# Re-export contracts (dataclasses and constants)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
    FAILURE_BACKEND_DNS_RESOLUTION_FAILED,
    FAILURE_BACKEND_ENDPOINT_NOT_READY,
    FAILURE_BACKEND_INCIDENT_FETCH_CONTRACT_ERROR,
    FAILURE_BACKEND_INCIDENT_FETCH_FAILED,
    FAILURE_BACKEND_INCIDENT_FETCH_HTTP_ERROR,
    FAILURE_BACKEND_INCIDENT_FETCH_INVALID_JSON,
    FAILURE_BACKEND_INCIDENT_FETCH_NOT_FOUND,
    FAILURE_BACKEND_INCIDENT_FETCH_TRANSPORT_ERROR,
    FAILURE_TARGETED_INSUFFICIENT_PASSES,
    FAILURE_TARGETED_INVOCATION_HTTP_ERROR,
    FAILURE_TARGETED_INVOCATION_INVALID_JSON,
    FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
    FAILURE_TARGETED_LOOP_BACKEND_EMPTY_REPLY,
    FAILURE_TARGETED_LOOP_NOT_COMPLETED,
    FAILURE_TARGETED_LOOP_NOT_ELIGIBLE,
    FAILURE_TARGETED_NO_PASS_ARTIFACTS,
    FAILURE_TARGETED_REVIEW_PACKET_MISSING,
    BackendIncidentDetail,
    BackendIncidentFetchResult,
    TargetedDiagnosisInvocationResult,
    TargetedDiagnosisPollResult,
)

# Re-export HTTP helpers
from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http import (
    curl_backend_exec,
    fetch_backend_incident_detail,
    fetch_backend_incident_detail_result,
    invoke_targeted_automatic_diagnosis_loop,
)

# Re-export polling helpers
from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_poll import (
    poll_backend_diagnosis_state,
)

# Re-export retry helpers
from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_retry import (
    fetch_backend_incident_detail_with_retry,
)

# Re-export budget reset helpers
from scripts.k9b_otel_demo_lab_k8s_diagnosis_budget_reset import (
    get_budget_status,
    reset_diagnosis_loop_budget,
)

__all__ = [
    # Constants - DNS and endpoint failures
    "FAILURE_BACKEND_DNS_RESOLUTION_FAILED",
    "FAILURE_BACKEND_ENDPOINT_NOT_READY",
    # Constants - incident fetch
    "FAILURE_BACKEND_INCIDENT_FETCH_CONTRACT_ERROR",
    "FAILURE_BACKEND_INCIDENT_FETCH_FAILED",
    "FAILURE_BACKEND_INCIDENT_FETCH_HTTP_ERROR",
    "FAILURE_BACKEND_INCIDENT_FETCH_INVALID_JSON",
    "FAILURE_BACKEND_INCIDENT_FETCH_NOT_FOUND",
    "FAILURE_BACKEND_INCIDENT_FETCH_TRANSPORT_ERROR",
    # Constants - targeted invocation
    "FAILURE_TARGETED_INVOCATION_HTTP_ERROR",
    "FAILURE_TARGETED_INVOCATION_INVALID_JSON",
    "FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR",
    "FAILURE_TARGETED_LOOP_BACKEND_EMPTY_REPLY",
    "FAILURE_TARGETED_LOOP_NOT_COMPLETED",
    "FAILURE_TARGETED_LOOP_NOT_ELIGIBLE",
    "FAILURE_TARGETED_NO_PASS_ARTIFACTS",
    "FAILURE_TARGETED_REVIEW_PACKET_MISSING",
    "FAILURE_TARGETED_INSUFFICIENT_PASSES",
    # Dataclasses
    "BackendIncidentDetail",
    "BackendIncidentFetchResult",
    "TargetedDiagnosisInvocationResult",
    "TargetedDiagnosisPollResult",
    # Functions
    "curl_backend_exec",
    "fetch_backend_incident_detail",
    "fetch_backend_incident_detail_result",
    "fetch_backend_incident_detail_with_retry",
    "invoke_targeted_automatic_diagnosis_loop",
    "poll_backend_diagnosis_state",
    "check_pass_artifacts_in_backend",
    # Budget reset helpers
    "reset_diagnosis_loop_budget",
    "get_budget_status",
]
