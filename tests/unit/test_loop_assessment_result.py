"""Tests for loop_assessment_result module.

Verifies final health assessment result assembly helper in isolation.
This is a pure assembly helper: it constructs the result object without
creating signals, findings, hypotheses, or next checks.
"""

from __future__ import annotations

from k8s_diag_agent.health.loop_assessment_result import build_health_assessment_result
from k8s_diag_agent.health.loop_history import HealthRating
from k8s_diag_agent.models import (
    Assessment,
    ConfidenceLevel,
    Finding,
    Hypothesis,
    Layer,
    NextCheck,
    RecommendedAction,
    SafetyLevel,
)


class TestBuildHealthAssessmentResult:
    """Tests for build_health_assessment_result helper."""

    def _make_minimal_assessment(self) -> Assessment:
        """Build a minimal Assessment object for testing."""
        return Assessment(
            observed_signals=[],
            findings=[],
            hypotheses=[],
            next_evidence_to_collect=[],
            recommended_action=RecommendedAction(
                type="observation",
                description="Test action.",
                references=[],
                safety_level=SafetyLevel.OBSERVE_ONLY,
            ),
            safety_level=SafetyLevel.OBSERVE_ONLY,
            overall_confidence=ConfidenceLevel.HIGH,
        )

    def test_returns_health_assessment_result(self) -> None:
        """Helper returns a HealthAssessmentResult instance."""
        result = build_health_assessment_result(
            assessment=self._make_minimal_assessment(),
            rating=HealthRating.HEALTHY,
            missing_evidence=(),
            node_count=3,
            pod_count=42,
            control_plane_version="v1.28.0",
            pattern_reasons=(),
            pattern_metadata={},
        )
        assert result is not None
        # Verify it's a result-like object with expected fields
        assert hasattr(result, "assessment")
        assert hasattr(result, "rating")
        assert hasattr(result, "missing_evidence")
        assert hasattr(result, "node_count")
        assert hasattr(result, "pod_count")
        assert hasattr(result, "control_plane_version")
        assert hasattr(result, "pattern_reasons")
        assert hasattr(result, "pattern_metadata")

    def test_assessment_field_wired(self) -> None:
        """assessment field is correctly wired to result."""
        assessment = self._make_minimal_assessment()
        result = build_health_assessment_result(
            assessment=assessment,
            rating=HealthRating.HEALTHY,
            missing_evidence=(),
            node_count=3,
            pod_count=42,
            control_plane_version="v1.28.0",
            pattern_reasons=(),
            pattern_metadata={},
        )
        assert result.assessment is assessment

    def test_rating_field_wired(self) -> None:
        """rating field is correctly wired to result."""
        result = build_health_assessment_result(
            assessment=self._make_minimal_assessment(),
            rating=HealthRating.DEGRADED,
            missing_evidence=(),
            node_count=3,
            pod_count=42,
            control_plane_version="v1.28.0",
            pattern_reasons=(),
            pattern_metadata={},
        )
        assert result.rating == HealthRating.DEGRADED

    def test_missing_evidence_wired(self) -> None:
        """missing_evidence field is correctly wired to result."""
        missing = ("nodes", "pods")
        result = build_health_assessment_result(
            assessment=self._make_minimal_assessment(),
            rating=HealthRating.HEALTHY,
            missing_evidence=missing,
            node_count=3,
            pod_count=42,
            control_plane_version="v1.28.0",
            pattern_reasons=(),
            pattern_metadata={},
        )
        assert result.missing_evidence == missing

    def test_node_count_wired(self) -> None:
        """node_count field is correctly wired to result."""
        result = build_health_assessment_result(
            assessment=self._make_minimal_assessment(),
            rating=HealthRating.HEALTHY,
            missing_evidence=(),
            node_count=5,
            pod_count=100,
            control_plane_version="v1.28.0",
            pattern_reasons=(),
            pattern_metadata={},
        )
        assert result.node_count == 5

    def test_pod_count_wired(self) -> None:
        """pod_count field is correctly wired to result."""
        result = build_health_assessment_result(
            assessment=self._make_minimal_assessment(),
            rating=HealthRating.HEALTHY,
            missing_evidence=(),
            node_count=3,
            pod_count=99,
            control_plane_version="v1.28.0",
            pattern_reasons=(),
            pattern_metadata={},
        )
        assert result.pod_count == 99

    def test_pod_count_none_wired(self) -> None:
        """pod_count can be None and is correctly wired to result."""
        result = build_health_assessment_result(
            assessment=self._make_minimal_assessment(),
            rating=HealthRating.UNKNOWN,
            missing_evidence=(),
            node_count=0,
            pod_count=None,
            control_plane_version="unknown",
            pattern_reasons=(),
            pattern_metadata={},
        )
        assert result.pod_count is None

    def test_control_plane_version_wired(self) -> None:
        """control_plane_version field is correctly wired to result."""
        result = build_health_assessment_result(
            assessment=self._make_minimal_assessment(),
            rating=HealthRating.HEALTHY,
            missing_evidence=(),
            node_count=3,
            pod_count=42,
            control_plane_version="v1.29.1+k3s1",
            pattern_reasons=(),
            pattern_metadata={},
        )
        assert result.control_plane_version == "v1.29.1+k3s1"

    def test_pattern_reasons_wired(self) -> None:
        """pattern_reasons field is correctly wired to result."""
        reasons = ("warning_events", "missing_evidence")
        result = build_health_assessment_result(
            assessment=self._make_minimal_assessment(),
            rating=HealthRating.DEGRADED,
            missing_evidence=(),
            node_count=3,
            pod_count=42,
            control_plane_version="v1.28.0",
            pattern_reasons=reasons,
            pattern_metadata={},
        )
        assert result.pattern_reasons == reasons

    def test_pattern_metadata_wired(self) -> None:
        """pattern_metadata field is correctly wired to result."""
        metadata = {"warning_events": ("EvictedPod", "ImagePullBackOff")}
        result = build_health_assessment_result(
            assessment=self._make_minimal_assessment(),
            rating=HealthRating.DEGRADED,
            missing_evidence=(),
            node_count=3,
            pod_count=42,
            control_plane_version="v1.28.0",
            pattern_reasons=(),
            pattern_metadata=metadata,
        )
        assert result.pattern_metadata == metadata

    def test_findsings_hypotheses_nextchecks_order_preserved(self) -> None:
        """Object identity and order are preserved for findings, hypotheses, next checks."""
        findings = [
            Finding(
                id="f1",
                description="Finding 1",
                supporting_signals=["s1"],
                layer=Layer.WORKLOAD,
            ),
            Finding(
                id="f2",
                description="Finding 2",
                supporting_signals=["s2"],
                layer=Layer.NODE,
            ),
        ]
        hypotheses = [
            Hypothesis(
                id="h1",
                description="Hypothesis 1",
                confidence=ConfidenceLevel.MEDIUM,
                probable_layer=Layer.WORKLOAD,
                what_would_falsify="falsifier",
            ),
        ]
        next_checks = [
            NextCheck(
                description="Check 1",
                owner="engineer",
                method="kubectl",
                evidence_needed=["pods"],
            ),
            NextCheck(
                description="Check 2",
                owner="engineer",
                method="kubectl",
                evidence_needed=["nodes"],
            ),
        ]
        assessment = Assessment(
            observed_signals=[],
            findings=findings,
            hypotheses=hypotheses,
            next_evidence_to_collect=next_checks,
            recommended_action=RecommendedAction(
                type="observation",
                description="Test action.",
                references=[],
                safety_level=SafetyLevel.OBSERVE_ONLY,
            ),
            safety_level=SafetyLevel.OBSERVE_ONLY,
            overall_confidence=ConfidenceLevel.HIGH,
        )
        result = build_health_assessment_result(
            assessment=assessment,
            rating=HealthRating.DEGRADED,
            missing_evidence=(),
            node_count=3,
            pod_count=42,
            control_plane_version="v1.28.0",
            pattern_reasons=(),
            pattern_metadata={},
        )
        # Verify order and identity are preserved
        assert result.assessment.findings == findings
        assert result.assessment.hypotheses == hypotheses
        assert result.assessment.next_evidence_to_collect == next_checks

    def test_different_ratings(self) -> None:
        """All HealthRating values are correctly wired."""
        for rating in HealthRating:
            result = build_health_assessment_result(
                assessment=self._make_minimal_assessment(),
                rating=rating,
                missing_evidence=(),
                node_count=3,
                pod_count=42,
                control_plane_version="v1.28.0",
                pattern_reasons=(),
                pattern_metadata={},
            )
            assert result.rating == rating

    def test_empty_pattern_reasons_and_metadata(self) -> None:
        """Empty pattern_reasons and pattern_metadata are correctly handled."""
        result = build_health_assessment_result(
            assessment=self._make_minimal_assessment(),
            rating=HealthRating.HEALTHY,
            missing_evidence=(),
            node_count=3,
            pod_count=42,
            control_plane_version="v1.28.0",
            pattern_reasons=(),
            pattern_metadata={},
        )
        assert result.pattern_reasons == ()
        assert result.pattern_metadata == {}

    def test_multiple_pattern_reasons(self) -> None:
        """Multiple pattern reasons are correctly handled."""
        reasons = ("warning_events", "image_pull_backoff", "job_failures")
        result = build_health_assessment_result(
            assessment=self._make_minimal_assessment(),
            rating=HealthRating.DEGRADED,
            missing_evidence=(),
            node_count=3,
            pod_count=42,
            control_plane_version="v1.28.0",
            pattern_reasons=reasons,
            pattern_metadata={},
        )
        assert result.pattern_reasons == reasons
