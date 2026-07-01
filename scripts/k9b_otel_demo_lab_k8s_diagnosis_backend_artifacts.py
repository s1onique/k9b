"""Backend artifact helpers for P4c K8s diagnosis phase.

This module provides artifact-related helpers for backend-targeted diagnosis:
1. check_pass_artifacts_in_backend: Check if pass artifacts exist for an incident

Architecture:
- Uses kubectl exec against deploy/k9b-backend -c backend for backend-local HTTP
- Does NOT rely on scheduler periodic automatic diagnosis loop
"""

from __future__ import annotations

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http import (
    fetch_backend_incident_detail,
)
from scripts.lab_common.constants import DEFAULT_K9B_BACKEND_PORT


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
