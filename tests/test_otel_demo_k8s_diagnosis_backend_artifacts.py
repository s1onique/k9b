"""Unit tests for k9b_otel_demo_lab_k8s_diagnosis_backend_artifacts.py.

These tests validate the artifact helpers for backend-targeted diagnosis.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_artifacts import (
    check_pass_artifacts_in_backend,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
    BackendIncidentDetail,
)

# =============================================================================
# Test check_pass_artifacts_in_backend
# =============================================================================


class TestCheckPassArtifactsInBackend:
    """Tests for check_pass_artifacts_in_backend."""

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_artifacts.fetch_backend_incident_detail")
    def test_sufficient_passes(self, mock_fetch: MagicMock) -> None:
        """Test detection of sufficient pass artifacts."""
        mock_fetch.return_value = BackendIncidentDetail(
            incident_id="inc-123",
            status="diagnosed",
            evidence_count=5,
            review_packet_status="ready",
            loop_summary_status="completed",
            review_available=True,
            raw={
                "automatic_diagnosis_loop_summary": {
                    "pass_count": 3,
                    "pass_run_ids": ["run-1", "run-2", "run-3"],
                }
            },
        )

        has_sufficient, pass_count, pass_ids = check_pass_artifacts_in_backend(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
            min_required_passes=2,
        )

        assert has_sufficient is True
        assert pass_count == 3
        assert len(pass_ids) == 3

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_artifacts.fetch_backend_incident_detail")
    def test_insufficient_passes(self, mock_fetch: MagicMock) -> None:
        """Test detection of insufficient pass artifacts."""
        mock_fetch.return_value = BackendIncidentDetail(
            incident_id="inc-123",
            status="diagnosed",
            evidence_count=1,
            review_packet_status="pending",
            loop_summary_status="completed",
            review_available=False,
            raw={
                "automatic_diagnosis_loop_summary": {
                    "pass_count": 1,
                    "pass_run_ids": ["run-1"],
                }
            },
        )

        has_sufficient, pass_count, pass_ids = check_pass_artifacts_in_backend(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
            min_required_passes=2,
        )

        assert has_sufficient is False
        assert pass_count == 1
        assert len(pass_ids) == 1

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_artifacts.fetch_backend_incident_detail")
    def test_no_passes(self, mock_fetch: MagicMock) -> None:
        """Test no pass artifacts available."""
        mock_fetch.return_value = BackendIncidentDetail(
            incident_id="inc-123",
            status="diagnosing",
            evidence_count=0,
            review_packet_status=None,
            loop_summary_status="running",
            review_available=False,
            raw={},
        )

        has_sufficient, pass_count, pass_ids = check_pass_artifacts_in_backend(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
            min_required_passes=2,
        )

        assert has_sufficient is False
        assert pass_count == 0
        assert pass_ids == []

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_artifacts.fetch_backend_incident_detail")
    def test_fetch_returns_none(self, mock_fetch: MagicMock) -> None:
        """Test when fetch returns None."""
        mock_fetch.return_value = None

        has_sufficient, pass_count, pass_ids = check_pass_artifacts_in_backend(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
            min_required_passes=2,
        )

        assert has_sufficient is False
        assert pass_count == 0
        assert pass_ids == []

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_artifacts.fetch_backend_incident_detail")
    def test_pass_run_ids_from_incident_raw(self, mock_fetch: MagicMock) -> None:
        """Test pass_run_ids extracted from incident raw when not in loop_summary."""
        mock_fetch.return_value = BackendIncidentDetail(
            incident_id="inc-123",
            status="diagnosed",
            evidence_count=5,
            review_packet_status="ready",
            loop_summary_status="completed",
            review_available=True,
            raw={
                "pass_run_ids": ["run-1", "run-2"],
            },
        )

        has_sufficient, pass_count, pass_ids = check_pass_artifacts_in_backend(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
            min_required_passes=2,
        )

        assert has_sufficient is True
        assert pass_count == 2
        assert pass_ids == ["run-1", "run-2"]
