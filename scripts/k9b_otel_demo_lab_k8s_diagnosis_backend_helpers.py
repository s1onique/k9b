"""Backend-targeted diagnosis helpers for P4c K8s diagnosis phase.

This module is a thin compatibility façade that re-exports the public API
from the extracted backend helper modules.

Architecture:
- Uses kubectl exec against deploy/k9b-backend -c backend for backend-local HTTP
- Does NOT rely on scheduler periodic automatic diagnosis loop
- Targets POST /api/incidents/{incident_id}/automatic-diagnosis-loop/one-pass

For the actual implementation, see:
- k9b_otel_demo_lab_k8s_diagnosis_backend_contracts: dataclasses/constants
- k9b_otel_demo_lab_k8s_diagnosis_backend_http: HTTP helpers
- k9b_otel_demo_lab_k8s_diagnosis_backend_artifacts: artifact helpers
- k9b_otel_demo_lab_k8s_diagnosis_backend_poll: polling helpers
"""

from __future__ import annotations

# Re-export artifact helpers
from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_artifacts import (
    check_pass_artifacts_in_backend,
)

# Re-export contracts (dataclasses and constants)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
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
    FAILURE_TARGETED_LOOP_NOT_COMPLETED,
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

__all__ = [
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
    "FAILURE_TARGETED_LOOP_NOT_COMPLETED",
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
    "invoke_targeted_automatic_diagnosis_loop",
    "poll_backend_diagnosis_state",
    "check_pass_artifacts_in_backend",
]
