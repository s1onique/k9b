"""Tests for HistoryDriftAssessment dataclass."""

from __future__ import annotations

from unittest.mock import MagicMock

from k8s_diag_agent.health.loop_assessment_history_drift import HistoryDriftAssessment
from k8s_diag_agent.models import NextCheck


class TestHistoryDriftAssessmentDataclass:
    """Test HistoryDriftAssessment dataclass."""

    def test_dataclass_creation(self) -> None:
        """HistoryDriftAssessment can be created with has_drift=True."""
        assessment = HistoryDriftAssessment(has_drift=True)
        assert assessment.has_drift is True

    def test_default_has_drift_false(self) -> None:
        """HistoryDriftAssessment defaults has_drift to False."""
        assessment = HistoryDriftAssessment(has_drift=False)
        assert assessment.has_drift is False