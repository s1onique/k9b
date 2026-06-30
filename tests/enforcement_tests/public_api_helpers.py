"""Shared helpers for public API enforcement tests.

This module provides reusable fixtures, constants, and assertion helpers
for public API testing. It is NOT a test file (no test_ functions).
"""
from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from k8s_diag_agent.collect.incident_diagnosis_loop_policy import (
    DiagnosisLoopPolicy,
)
from k8s_diag_agent.collect.runtime_state import LoopRuntimeState

if TYPE_CHECKING:
    pass


# =============================================================================
# Policy fixtures
# =============================================================================


@pytest.fixture
def sample_policy() -> DiagnosisLoopPolicy:
    """Default policy for testing."""
    return DiagnosisLoopPolicy.live_lab_default()


@pytest.fixture
def restrictive_policy() -> DiagnosisLoopPolicy:
    """Policy that stops immediately on budget exhaustion."""
    return DiagnosisLoopPolicy(
        max_passes=1,
        max_total_checks=0,
    )


@pytest.fixture
def single_check_per_pass_policy() -> DiagnosisLoopPolicy:
    """Policy that allows only one check per pass."""
    return DiagnosisLoopPolicy(
        max_checks_per_pass=1,
        max_passes=5,
        max_total_checks=10,
    )


# =============================================================================
# Case file fixtures
# =============================================================================


@pytest.fixture
def sample_case_file() -> dict[str, Any]:
    """Sample case file for testing."""
    return {
        "incident": {
            "incident_id": "test-incident-123",
            "namespace": "default",
            "object_kind": "Pod",
            "object_name": "test-pod",
            "severity": "warning",
        },
        "events": [],
        "pods": [],
    }


@pytest.fixture
def sample_diagnosis_report() -> dict[str, Any]:
    """Sample diagnosis report with recommended checks."""
    return {
        "diagnosis": {
            "recommended_investigations": [
                {"check_id": "check_1", "title": "Check 1"},
                {"check_id": "check_2", "title": "Check 2"},
            ]
        }
    }


# =============================================================================
# Handler factories
# =============================================================================


def make_tracking_handler(
    call_tracker: list[str],
) -> Any:
    """Create a handler that tracks which checks were called.

    Args:
        call_tracker: List to append check IDs to

    Returns:
        A handler function
    """
    def handler(check: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
        check_id = check.get("check_id", "unknown")
        call_tracker.append(check_id)
        return {
            "check_id": check_id,
            "status": "completed",
            "summary": f"Executed {check_id}",
        }
    return handler


def make_crash_on_call_handler(
    call_tracker: list[bool],
) -> Any:
    """Create a handler that records being called but doesn't crash.

    This is for testing that handlers are NEVER called (enforcement tests).

    Args:
        call_tracker: List to append True when handler is called

    Returns:
        A handler function
    """
    def handler(check: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
        call_tracker.append(True)
        return {
            "check_id": check.get("check_id", "unknown"),
            "status": "completed",
            "summary": "Handler was called!",
        }
    return handler


# =============================================================================
# Fake handlers
# =============================================================================


def make_fake_handlers(
    checks: list[str] | None = None,
    tracking: list[str] | None = None,
) -> dict[str, Any]:
    """Create fake handlers for testing.

    Args:
        checks: List of check IDs to create handlers for
        tracking: If provided, track calls in this list

    Returns:
        Dict of check_id -> handler
    """
    if checks is None:
        checks = ["check_1", "check_2", "check_3"]

    handlers: dict[str, Any] = {}
    tracker = tracking or []

    for check_id in checks:
        handlers[check_id] = make_tracking_handler(tracker)

    return handlers


# =============================================================================
# Temporary directory helpers
# =============================================================================


@pytest.fixture
def temp_analysis_dir() -> Path:
    """Create a temporary directory for analysis artifacts."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


# =============================================================================
# Assertion helpers
# =============================================================================


def assert_gate_summary_rejects_mutating(gate_summary: dict[str, Any]) -> None:
    """Assert that gate summary shows mutating checks were rejected."""
    rejected_mutating = gate_summary.get("rejected_mutating", 0)
    assert rejected_mutating >= 1, (
        f"Expected at least 1 mutating check to be rejected, got {rejected_mutating}"
    )


def assert_gate_summary_rejects_sensitive(gate_summary: dict[str, Any]) -> None:
    """Assert that gate summary shows sensitive checks were rejected."""
    rejected_sensitive = gate_summary.get("rejected_sensitive", 0)
    assert rejected_sensitive >= 1, (
        f"Expected at least 1 sensitive check to be rejected, got {rejected_sensitive}"
    )


def assert_gate_summary_rejects_duplicate(gate_summary: dict[str, Any]) -> None:
    """Assert that gate summary shows duplicate checks were rejected."""
    rejected_duplicate = gate_summary.get("rejected_duplicate", 0)
    assert rejected_duplicate >= 1, (
        f"Expected at least 1 duplicate check to be rejected, got {rejected_duplicate}"
    )


def assert_pass_artifact_valid_schema(artifact: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate pass artifact has required schema fields.

    Returns:
        Tuple of (is_valid, missing_fields)
    """
    from k8s_diag_agent.collect.incident_diagnosis_loop_policy import (
        validate_pass_artifact_schema,
    )
    return validate_pass_artifact_schema(artifact)


# =============================================================================
# Runtime state helpers
# =============================================================================


def make_runtime_state_for_pass(
    pass_index: int,
    incident_id: str = "test-incident",
    seen_fingerprints: frozenset[str] | None = None,
) -> LoopRuntimeState:
    """Create a runtime state for a specific pass.

    Args:
        pass_index: The pass index
        incident_id: The incident ID
        seen_fingerprints: Fingerprints already seen (for duplicate detection)

    Returns:
        LoopRuntimeState instance
    """
    return LoopRuntimeState(
        loop_run_id=f"test-run-{pass_index}",
        incident_id=incident_id,
        pass_index=pass_index,
        started_at=datetime.now(UTC).isoformat(),
        seen_check_fingerprints=seen_fingerprints or frozenset(),
    )


# =============================================================================
# Constants
# =============================================================================

# Common mutating check IDs that should be rejected
MUTATING_CHECK_IDS = [
    "kubectl_apply",
    "kubectl_delete",
    "kubectl_patch",
    "kubectl_scale",
]

# Common sensitive check IDs that should be rejected
SENSITIVE_CHECK_IDS = [
    "kubectl_get_secrets",
    "kubectl_get_configmap_sensitive",
    "get_credentials",
]


__all__ = [
    # Fixtures
    "sample_policy",
    "restrictive_policy",
    "single_check_per_pass_policy",
    "sample_case_file",
    "sample_diagnosis_report",
    "temp_analysis_dir",
    # Factories
    "make_tracking_handler",
    "make_crash_on_call_handler",
    "make_fake_handlers",
    # Helpers
    "assert_gate_summary_rejects_mutating",
    "assert_gate_summary_rejects_sensitive",
    "assert_gate_summary_rejects_duplicate",
    "assert_pass_artifact_valid_schema",
    "make_runtime_state_for_pass",
    # Constants
    "MUTATING_CHECK_IDS",
    "SENSITIVE_CHECK_IDS",
]
