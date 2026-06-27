"""Shared test utilities for incident discovery gate tests.

This module contains shared fixtures, builders, sample objects, and
assertion helpers used across the incident discovery gate test modules.
"""

from scripts.incident_discovery_gate import (
    FAILURE_INCIDENT_API_CONTRACT_MISMATCH,
    FAILURE_INCIDENT_CANDIDATE_NOT_DETECTED,
    FAILURE_INCIDENT_CANDIDATE_NOT_PROMOTED,
    FAILURE_INCIDENT_DISCOVERY_TIMEOUT,
    FAILURE_INCIDENT_FIXTURE_HEALTHY_UNEXPECTEDLY,
    FAILURE_INCIDENT_FIXTURE_MISSING,
    FAILURE_INCIDENT_FIXTURE_NAMESPACE_MISMATCH,
    FAILURE_INCIDENT_SCHEDULER_COMMUNICATION_ERROR,
    # LLM enrichment failures (Phase 2d/2e)
    FAILURE_LLM_ENRICHMENT_DISABLED,
    FAILURE_LLM_ENRICHMENT_NOT_TRIGGERED_NO_INCIDENT,
    FAILURE_LLM_ENRICHMENT_NOT_TRIGGERED_POLICY_GATE,
    FAILURE_LLM_PROVIDER_CLIENT_NOT_INVOKED,
    FAILURE_LLM_PROVIDER_ENV_MISSING,
    FAILURE_LLM_PROVIDER_NOT_CONFIGURED,
    FAILURE_LLM_PROVIDER_REQUEST_FAILED,
    FAILURE_LLM_PROVIDER_RESPONSE_NOT_PERSISTED,
    FAILURE_LLM_PROVIDER_SECRET_MISSING,
)
from scripts.incident_discovery_gate.classify import (
    classify_api_contract_issue,
    classify_api_response_shape,
    classify_candidate_detection,
    classify_fixture_failure,
    classify_incident_promotion,
    extract_incident_id_from_response,
    sanitize_api_response_for_logging,
)
from scripts.incident_discovery_gate.enrich import (
    classify_enrichment_status,
    extract_enrichment_status_from_incident,
)
from scripts.incident_discovery_gate.render import sanitize_logs_for_artifacts
from scripts.incident_discovery_gate.types import IncidentDiscoveryResult

# Re-export everything for convenience
__all__ = [
    # Constants
    "FAILURE_INCIDENT_API_CONTRACT_MISMATCH",
    "FAILURE_INCIDENT_CANDIDATE_NOT_DETECTED",
    "FAILURE_INCIDENT_CANDIDATE_NOT_PROMOTED",
    "FAILURE_INCIDENT_DISCOVERY_TIMEOUT",
    "FAILURE_INCIDENT_FIXTURE_HEALTHY_UNEXPECTEDLY",
    "FAILURE_INCIDENT_FIXTURE_MISSING",
    "FAILURE_INCIDENT_FIXTURE_NAMESPACE_MISMATCH",
    "FAILURE_INCIDENT_SCHEDULER_COMMUNICATION_ERROR",
    "FAILURE_LLM_ENRICHMENT_DISABLED",
    "FAILURE_LLM_ENRICHMENT_NOT_TRIGGERED_NO_INCIDENT",
    "FAILURE_LLM_ENRICHMENT_NOT_TRIGGERED_POLICY_GATE",
    "FAILURE_LLM_PROVIDER_CLIENT_NOT_INVOKED",
    "FAILURE_LLM_PROVIDER_ENV_MISSING",
    "FAILURE_LLM_PROVIDER_NOT_CONFIGURED",
    "FAILURE_LLM_PROVIDER_REQUEST_FAILED",
    "FAILURE_LLM_PROVIDER_RESPONSE_NOT_PERSISTED",
    "FAILURE_LLM_PROVIDER_SECRET_MISSING",
    # Classify functions
    "classify_api_contract_issue",
    "classify_api_response_shape",
    "classify_candidate_detection",
    "classify_fixture_failure",
    "classify_incident_promotion",
    "extract_incident_id_from_response",
    "sanitize_api_response_for_logging",
    # Enrich functions
    "classify_enrichment_status",
    "extract_enrichment_status_from_incident",
    # Render functions
    "sanitize_logs_for_artifacts",
    # Types
    "IncidentDiscoveryResult",
]


# ============================================================================
# Builder / Factory Functions
# ============================================================================


def make_pod_status_found(
    namespace: str = "test-ns",
    phase: str = "Running",
    container_statuses: list | None = None,
    conditions: list | None = None,
) -> dict:
    """Create a pod status dict simulating a found pod."""
    return {
        "found": True,
        "namespace": namespace,
        "phase": phase,
        "container_statuses": container_statuses or [{"ready": True}],
        "conditions": conditions or [],
    }


def make_pod_status_not_found() -> dict:
    """Create a pod status dict simulating a not-found pod."""
    return {"found": False}


def make_healthy_pod_status(
    namespace: str = "test-ns",
    container_count: int = 1,
) -> dict:
    """Create a pod status dict representing a healthy pod."""
    return make_pod_status_found(
        namespace=namespace,
        phase="Running",
        container_statuses=[{"ready": True} for _ in range(container_count)],
        conditions=[{"type": "Ready", "status": "True"}],
    )


def make_unhealthy_pod_status(
    namespace: str = "test-ns",
    reason: str = "readiness_failure",
    restart_count: int = 0,
) -> dict:
    """Create a pod status dict representing an unhealthy pod."""
    if reason == "readiness_failure":
        return make_pod_status_found(
            namespace=namespace,
            phase="Running",
            container_statuses=[{"ready": False}],
            conditions=[],
        )
    elif reason == "pending":
        return make_pod_status_found(
            namespace=namespace,
            phase="Pending",
            container_statuses=[],
            conditions=[],
        )
    elif reason == "failed":
        return make_pod_status_found(
            namespace=namespace,
            phase="Failed",
            container_statuses=[],
            conditions=[],
        )
    elif reason == "restart_loop":
        return make_pod_status_found(
            namespace=namespace,
            phase="Running",
            container_statuses=[{"ready": True, "restartCount": restart_count}],
            conditions=[{"type": "Ready", "status": "True"}],
        )
    raise ValueError(f"Unknown reason: {reason}")


def make_api_response(incidents: list | None = None) -> str:
    """Create a JSON API response string with the given incidents."""
    if incidents is None:
        incidents = []
    return f'{{"incidents": {incidents}}}'
