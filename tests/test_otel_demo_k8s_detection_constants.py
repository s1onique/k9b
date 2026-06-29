"""Tests for OTel Demo K8s-native incident discovery - Constants.

These tests verify detection constants are correctly defined.
"""

from __future__ import annotations


class TestK8sDetectionConstants:
    """Test detection constants are correctly defined."""

    def test_accepted_candidate_classes_defined(self) -> None:
        """Accepted candidate classes include pending_pod, deployment_unavailable, warning_event_burst."""
        from scripts.k9b_otel_demo_lab_k8s_detection import ACCEPTED_CANDIDATE_CLASSES

        assert "pending_pod" in ACCEPTED_CANDIDATE_CLASSES
        assert "deployment_unavailable" in ACCEPTED_CANDIDATE_CLASSES
        assert "warning_event_burst" in ACCEPTED_CANDIDATE_CLASSES
        assert len(ACCEPTED_CANDIDATE_CLASSES) == 3

    def test_failed_scheduling_patterns_defined(self) -> None:
        """FailedScheduling patterns include FailedScheduling and Unschedulable."""
        from scripts.k9b_otel_demo_lab_k8s_detection import FAILED_SCHEDULING_PATTERNS

        assert "FailedScheduling" in FAILED_SCHEDULING_PATTERNS
        assert "Unschedulable" in FAILED_SCHEDULING_PATTERNS
