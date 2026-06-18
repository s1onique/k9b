"""Shared fixtures for incident detail suggested checks tests.

This module provides:
- Realistic artifact fixture builders for next-check-plan.json
- Test harness with temp external-analysis directory management
- Shared incident creation helpers

Not collected as test classes (no Test prefix).
"""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from k8s_diag_agent.collect.incident_lifecycle import IncidentSignal
from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.collect.incident_store_provider import (
    reset_incident_store,
    set_incident_store,
)

from .incident_lifecycle_fixtures import TEST_TIME_1, make_candidate

# =============================================================================
# Realistic artifact fixture builders
# =============================================================================


def make_valid_next_check_plan_artifact(
    run_id: str,
    incident_id: str,
    *,
    candidate_id: str = "check-001",
    title: str = "Pod Log Inspection",
    description: str = "Check pod logs for crash loop errors",
    rationale: str = "CrashLoopBackOff typically leaves informative logs",
    risk_level: str = "LOW",
) -> dict:
    """Create a realistic valid next-check-plan.json artifact.

    This fixture represents a real artifact produced by the next-check planner
    with proper linkage fields for SAFE incident association.
    """
    return {
        "run_id": run_id,
        "linkage_schema_version": 1,
        "candidates": [
            {
                "linkage_status": "linked",
                "incident_id": incident_id,
                "candidateId": candidate_id,
                "title": title,
                "description": description,
                "rationale": rationale,
                "riskLevel": risk_level,
                "sourceReason": "CrashLoopBackOff",
                "suggestedCommandFamily": "kubectl-logs",
                "safeToAutomate": True,
                "requiresOperatorApproval": False,
                "confidence": "high",
                "estimatedCost": "low",
            },
        ],
    }


def make_partial_next_check_plan_artifact(run_id: str) -> dict:
    """Create an artifact with partial candidates (no usable linked check).

    Partial candidates have entity fields but no incident_id linkage.
    These should NOT appear in incident detail suggested_checks.
    """
    return {
        "run_id": run_id,
        "linkage_schema_version": 1,
        "candidates": [
            {
                "linkage_status": "partial",
                "candidateId": "check-001",
                "title": "Check pod logs",
                "description": "Check pod logs for crash loop",
                "namespace": "default",
                "objectKind": "Pod",
                "objectName": "test-pod",
            },
            {
                "linkage_status": "unlinked",
                "candidateId": "check-002",
                "title": "Describe pod",
                "description": "Describe the pod",
            },
        ],
    }


def make_wrong_incident_next_check_plan_artifact(run_id: str, wrong_incident_id: str) -> dict:
    """Create an artifact where linked candidates reference a different incident.

    These should NOT appear in incident detail suggested_checks for our incident.
    """
    return {
        "run_id": run_id,
        "linkage_schema_version": 1,
        "candidates": [
            {
                "linkage_status": "linked",
                "incident_id": wrong_incident_id,
                "candidateId": "check-001",
                "title": "Check logs",
                "description": "Check logs for other incident",
                "riskLevel": "LOW",
            },
        ],
    }


def make_legacy_next_check_plan_artifact(run_id: str) -> dict:
    """Create an artifact without linkage fields (legacy format).

    Legacy artifacts without linkage_status and incident_id should
    NOT produce suggested checks.
    """
    return {
        "run_id": run_id,
        "candidates": [
            {
                "candidateId": "check-001",
                "title": "Check logs",
                "description": "Check pod logs",
                "suggestedCommandFamily": "kubectl-logs",
            },
        ],
    }


def make_malformed_next_check_plan_artifact() -> str:
    """Return malformed JSON that should be gracefully skipped."""
    return "{ invalid json }"


def make_empty_candidates_next_check_plan_artifact(run_id: str) -> dict:
    """Create an artifact with empty candidates list.

    An artifact with linkage fields but no candidates should
    produce empty suggested_checks, not fail.
    """
    return {
        "run_id": run_id,
        "linkage_schema_version": 1,
        "candidates": [],
    }


def make_no_candidates_key_next_check_plan_artifact(run_id: str) -> dict:
    """Create an artifact without a candidates key.

    Should be gracefully handled (empty suggested_checks).
    """
    return {
        "run_id": run_id,
        "linkage_schema_version": 1,
    }


# =============================================================================
# Test harness (not a Test class - no pytest collection)
# =============================================================================


class IncidentSuggestedChecksHarness:
    """Test harness for incident detail suggested_checks tests.

    Provides:
    - IncidentStore setup/reset
    - Temp external-analysis directory management
    - Incident with signal creation
    - Artifact writing helpers
    """

    def setUp(self) -> None:
        """Set up test fixtures."""
        self._test_store = IncidentStore()
        set_incident_store(self._test_store)
        self._tmpdir = tempfile.mkdtemp()
        self._external_dir = Path(self._tmpdir) / "external-analysis"
        self._external_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        """Clean up after each test."""
        set_incident_store(None)
        reset_incident_store()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def write_plan_artifact(self, run_id: str, payload: dict) -> None:
        """Write a plan artifact to the external_analysis directory."""
        path = self._external_dir / f"{run_id}-next-check-plan.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

    def write_malformed_artifact(self, run_id: str, content: str) -> None:
        """Write a malformed artifact to the external_analysis directory."""
        path = self._external_dir / f"{run_id}-next-check-plan.json"
        path.write_text(content, encoding="utf-8")

    def create_incident_with_signal(
        self,
        run_id: str,
        *,
        signal_reason: str = "CrashLoopBackOff",
        signal_message: str = "restarting",
        captured_at: datetime = TEST_TIME_1,
    ) -> str:
        """Create an incident with a signal in the store."""
        # Create incident via candidate promotion
        candidate = make_candidate(name="test-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident = incidents[0]
        incident_id = incident.incident_id

        # Add signal to the stored incident (required for artifact lookup)
        stored_incident = self._test_store._incidents[incident_id]
        signal = IncidentSignal(
            source="pod",
            reason=signal_reason,
            message=signal_message,
            captured_at=captured_at,
            run_id=run_id,
        )
        stored_incident.signals.append(signal)

        return incident_id
