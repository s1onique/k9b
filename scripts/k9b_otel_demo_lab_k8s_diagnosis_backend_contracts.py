"""Compatibility façade for OTel demo backend contract helpers.

This module re-exports all public symbols from the split submodules to maintain
backward compatibility with existing imports. The implementation has been moved
to focused modules:
- k9b_otel_demo_lab_k8s_diagnosis_backend_failure_reasons: failure constants
- k9b_otel_demo_lab_k8s_diagnosis_backend_contract_types: dataclass types
- k9b_otel_demo_lab_k8s_diagnosis_backend_pass_counting: pass counting helpers
- k9b_otel_demo_lab_k8s_diagnosis_backend_terminal_decisions: terminal decision helpers
- k9b_otel_demo_lab_k8s_diagnosis_backend_p4c_outcome: P4c outcome computation

Architecture:
- Uses kubectl exec against deploy/k9b-backend -c backend for backend-local HTTP
- Does NOT rely on scheduler periodic automatic diagnosis loop
- Targets POST /api/incidents/{incident_id}/automatic-diagnosis-loop/one-pass
"""

from __future__ import annotations

# Dataclass types
from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contract_types import (
    BackendIncidentDetail,
    BackendIncidentFetchResult,
    P4cDiagnosisOutcome,
    TargetedDiagnosisInvocationResult,
    TargetedDiagnosisPollResult,
)

# Re-export all public symbols from submodules for backward compatibility
# Failure reason constants
from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_failure_reasons import (
    FAILURE_BACKEND_DNS_RESOLUTION_FAILED,
    FAILURE_BACKEND_EMPTY_REPLY,  # legacy alias
    FAILURE_BACKEND_ENDPOINT_NOT_READY,
    FAILURE_BACKEND_INCIDENT_FETCH_CONTRACT_ERROR,
    FAILURE_BACKEND_INCIDENT_FETCH_FAILED,
    FAILURE_BACKEND_INCIDENT_FETCH_HTTP_ERROR,
    FAILURE_BACKEND_INCIDENT_FETCH_INVALID_JSON,
    FAILURE_BACKEND_INCIDENT_FETCH_NOT_FOUND,
    FAILURE_BACKEND_INCIDENT_FETCH_TRANSPORT_ERROR,
    FAILURE_BUDGET_EXHAUSTED,
    FAILURE_TARGETED_BUDGET_EXHAUSTED_BEFORE_REQUIRED_PASSES,
    FAILURE_TARGETED_BUDGET_LIMIT_TOO_LOW,
    FAILURE_TARGETED_COMPLETED_WITHOUT_OBSERVABLE_PASS,
    FAILURE_TARGETED_INSUFFICIENT_PASSES,
    FAILURE_TARGETED_INVOCATION_HTTP_ERROR,
    FAILURE_TARGETED_INVOCATION_INVALID_JSON,
    FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
    FAILURE_TARGETED_LOOP_BACKEND_EMPTY_REPLY,
    FAILURE_TARGETED_LOOP_NOT_COMPLETED,
    FAILURE_TARGETED_LOOP_NOT_ELIGIBLE,
    FAILURE_TARGETED_LOOP_NOT_STARTED,
    FAILURE_TARGETED_NO_PASS_ARTIFACTS,
    FAILURE_TARGETED_REVIEW_PACKET_MISSING,
    FAILURE_TARGETED_TERMINAL_NO_CHECKS,
)

# P4c outcome computation
from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_p4c_outcome import (
    compute_p4c_outcome,
)

# Pass counting helpers
from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_pass_counting import (
    count_observable_targeted_diagnosis_passes,
    extract_pass_run_ids,
)

# Terminal decision helpers
from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_terminal_decisions import (
    is_read_only_terminal_decision,
    is_terminal_no_checks_decision,
)

__all__ = [
    # Failure constants
    "FAILURE_BACKEND_DNS_RESOLUTION_FAILED",
    "FAILURE_BACKEND_ENDPOINT_NOT_READY",
    "FAILURE_BACKEND_INCIDENT_FETCH_TRANSPORT_ERROR",
    "FAILURE_BACKEND_INCIDENT_FETCH_HTTP_ERROR",
    "FAILURE_BACKEND_INCIDENT_FETCH_NOT_FOUND",
    "FAILURE_BACKEND_INCIDENT_FETCH_INVALID_JSON",
    "FAILURE_BACKEND_INCIDENT_FETCH_CONTRACT_ERROR",
    "FAILURE_BACKEND_INCIDENT_FETCH_FAILED",
    "FAILURE_BUDGET_EXHAUSTED",
    "FAILURE_TARGETED_INVOCATION_HTTP_ERROR",
    "FAILURE_TARGETED_INVOCATION_INVALID_JSON",
    "FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR",
    "FAILURE_TARGETED_LOOP_BACKEND_EMPTY_REPLY",
    "FAILURE_TARGETED_LOOP_NOT_ELIGIBLE",
    "FAILURE_TARGETED_LOOP_NOT_COMPLETED",
    "FAILURE_TARGETED_LOOP_NOT_STARTED",
    "FAILURE_TARGETED_NO_PASS_ARTIFACTS",
    "FAILURE_TARGETED_REVIEW_PACKET_MISSING",
    "FAILURE_TARGETED_INSUFFICIENT_PASSES",
    "FAILURE_TARGETED_BUDGET_EXHAUSTED_BEFORE_REQUIRED_PASSES",
    "FAILURE_TARGETED_BUDGET_LIMIT_TOO_LOW",
    "FAILURE_TARGETED_COMPLETED_WITHOUT_OBSERVABLE_PASS",
    "FAILURE_TARGETED_TERMINAL_NO_CHECKS",
    "FAILURE_BACKEND_EMPTY_REPLY",
    # Dataclass types
    "P4cDiagnosisOutcome",
    "BackendIncidentDetail",
    "TargetedDiagnosisInvocationResult",
    "TargetedDiagnosisPollResult",
    "BackendIncidentFetchResult",
    # Pass counting
    "count_observable_targeted_diagnosis_passes",
    "extract_pass_run_ids",
    # Terminal decisions
    "is_terminal_no_checks_decision",
    "is_read_only_terminal_decision",
    # P4c outcome
    "compute_p4c_outcome",
]
