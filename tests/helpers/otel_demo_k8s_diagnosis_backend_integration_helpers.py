"""Shared helpers for OTel demo backend integration tests."""

from __future__ import annotations

from scripts.k9b_otel_demo_lab_k8s_diagnosis_budget_reset import BudgetResetResult


def mock_budget_reset_result(incident_id: str = "test-incident") -> BudgetResetResult:
    """Return a successful budget reset result."""
    return BudgetResetResult(
        incident_id=incident_id,
        reset_file_count=0,
        reset_paths=(),
        execution_context="k8s_backend_container",
        error=None,  # CRITICAL: must be None, not MagicMock
    )


def mock_budget_status_success(incident_id: str = "test-incident") -> dict:
    """Return a successful budget status result (budget is clean)."""
    return {
        "incident_id": incident_id,
        "budget_clean": True,
        "review_packet_count": 0,
        "loop_pass_count": 0,
        "other_auto_count": 0,
        "total_auto_artifact_count": 0,
        "budget_exhausted": False,
        "error": None,  # CRITICAL: must be None, not MagicMock
    }
