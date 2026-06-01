"""Tests for loop_assessment_summary module."""

from __future__ import annotations

from k8s_diag_agent.health.loop_assessment_summary import (
    derive_assessment_summary,
    pick_dominant_layer_from_signals,
)
from k8s_diag_agent.health.loop_history import HealthRating
from k8s_diag_agent.models import Layer, SafetyLevel, Signal


def _signal(severity: str, layer: Layer) -> Signal:
    return Signal(
        id="sig-1",
        description="test signal",
        layer=layer,
        evidence_id="test",
        severity=severity,
    )


class TestPickDominantLayerFromSignals:
    def test_empty_signals_returns_none(self) -> None:
        result = pick_dominant_layer_from_signals([])
        assert result is None

    def test_single_signal_returns_its_layer(self) -> None:
        sig = _signal("high", Layer.WORKLOAD)
        result = pick_dominant_layer_from_signals([sig])
        assert result == Layer.WORKLOAD

    def test_high_severity_wins(self) -> None:
        low = _signal("low", Layer.WORKLOAD)
        high = _signal("high", Layer.NODE)
        medium = _signal("medium", Layer.STORAGE)
        result = pick_dominant_layer_from_signals([low, high, medium])
        assert result == Layer.NODE

    def test_medium_wins_over_low(self) -> None:
        low = _signal("low", Layer.WORKLOAD)
        medium = _signal("medium", Layer.NODE)
        result = pick_dominant_layer_from_signals([low, medium])
        assert result == Layer.NODE

    def test_unknown_severity_ranked_lowest(self) -> None:
        unknown = _signal("unknown", Layer.WORKLOAD)
        high = _signal("high", Layer.NODE)
        result = pick_dominant_layer_from_signals([unknown, high])
        assert result == Layer.NODE


class TestDeriveAssessmentSummary:
    def test_no_issues_produces_healthy_rating(self) -> None:
        result = derive_assessment_summary(
            signals=[],
            issues_detected=False,
            workload_issue_present=False,
            node_issue_present=False,
            references=[],
        )
        assert result.rating == HealthRating.HEALTHY
        assert result.safety_level == SafetyLevel.OBSERVE_ONLY
        assert result.references == ("routine health monitoring",)

    def test_issues_produce_degraded_rating(self) -> None:
        result = derive_assessment_summary(
            signals=[],
            issues_detected=True,
            workload_issue_present=False,
            node_issue_present=False,
            references=[],
        )
        assert result.rating == HealthRating.DEGRADED
        assert result.safety_level == SafetyLevel.LOW_RISK

    def test_helm_error_appends_reference(self) -> None:
        result = derive_assessment_summary(
            signals=[],
            issues_detected=True,
            workload_issue_present=False,
            node_issue_present=False,
            references=[],
            helm_error="some error",
        )
        assert "helm collection error" in result.references

    def test_missing_evidence_appends_reference(self) -> None:
        result = derive_assessment_summary(
            signals=[],
            issues_detected=True,
            workload_issue_present=False,
            node_issue_present=False,
            references=[],
            has_missing_evidence=True,
        )
        assert "missing evidence" in result.references

    def test_image_pull_secret_insight_appends_reference(self) -> None:
        result = derive_assessment_summary(
            signals=[],
            issues_detected=True,
            workload_issue_present=False,
            node_issue_present=False,
            references=[],
            has_image_pull_secret_insight=True,
        )
        assert "image pull secret supply chain" in result.references

    def test_pattern_refs_extended(self) -> None:
        result = derive_assessment_summary(
            signals=[],
            issues_detected=True,
            workload_issue_present=False,
            node_issue_present=False,
            references=[],
            pattern_refs=["probe failure pattern"],
        )
        assert "probe failure pattern" in result.references

    def test_references_deduplicated(self) -> None:
        result = derive_assessment_summary(
            signals=[],
            issues_detected=True,
            workload_issue_present=False,
            node_issue_present=False,
            references=["node health", "node health", "pod readiness"],
            pattern_refs=["node health"],
        )
        # Should preserve order, deduplicate
        assert list(result.references).count("node health") == 1

    def test_empty_references_gets_routine_monitoring(self) -> None:
        result = derive_assessment_summary(
            signals=[],
            issues_detected=False,
            workload_issue_present=False,
            node_issue_present=False,
            references=[],
        )
        assert result.references == ("routine health monitoring",)

    def test_dominant_layer_from_signals(self) -> None:
        sig = _signal("high", Layer.NODE)
        result = derive_assessment_summary(
            signals=[sig],
            issues_detected=True,
            workload_issue_present=False,
            node_issue_present=False,
            references=[],
        )
        assert result.dominant_layer == Layer.NODE

    def test_dominant_layer_none_when_no_signals(self) -> None:
        result = derive_assessment_summary(
            signals=[],
            issues_detected=False,
            workload_issue_present=False,
            node_issue_present=False,
            references=[],
        )
        assert result.dominant_layer is None
