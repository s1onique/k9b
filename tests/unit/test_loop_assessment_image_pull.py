"""Tests for loop_assessment_image_pull module."""

from __future__ import annotations

from collections.abc import Callable

from k8s_diag_agent.health.image_pull_secret import (
    ExternalSecretStatus,
    ImagePullSecretInsight,
    TargetSecretStatus,
)
from k8s_diag_agent.health.loop_assessment_image_pull import assess_image_pull_issues
from k8s_diag_agent.models import Finding, Layer, NextCheck, Signal


def _signal_id_generator() -> Callable[[], str]:
    """Simple signal ID generator for testing."""
    _counter = [0]
    def generator() -> str:
        _counter[0] += 1
        return f"sig-{_counter[0]}"
    return generator


def _make_image_pull_secret_insight() -> ImagePullSecretInsight:
    """Create a test ImagePullSecretInsight with known values."""
    external_secret = ExternalSecretStatus(
        namespace="default",
        name="glcr-secret-external",
        target_secret="glcr-secret",
        secret_store_ref={"name": "glcr-store", "kind": "SecretStore", "namespace": "default"},
        status_reason="UpdateFailed",
        status_message="Secret does not exist",
        ready=False,
    )
    return ImagePullSecretInsight(
        namespace="default",
        secret_name="glcr-secret",
        deployments=({"namespace": "default", "name": "app-deployment"},),
        external_secrets=(external_secret,),
        secret_store_refs=({"name": "glcr-store", "kind": "SecretStore", "namespace": "default"},),
        target_secret_status=TargetSecretStatus.missing("default", "glcr-secret", "secret not found"),
        events=(),
    )


class TestAssessImagePullIssues:
    """Tests for assess_image_pull_issues function."""

    def test_no_insight_returns_false(self) -> None:
        """No image pull secret insight should return False and no changes."""
        signals: list[Signal] = []
        findings: list[Finding] = []
        next_checks: list[NextCheck] = []
        generator = _signal_id_generator()

        hypothesis, issues_detected = assess_image_pull_issues(
            image_pull_secret_insight=None,
            signals=signals,
            signal_id_generator=generator,
            findings=findings,
            next_checks=next_checks,
        )

        assert issues_detected is False
        assert hypothesis is None
        assert len(signals) == 0
        assert len(findings) == 0
        assert len(next_checks) == 0

    def test_no_external_secrets_returns_false(self) -> None:
        """Insight with no external secrets should return False."""
        insight = ImagePullSecretInsight(
            namespace="default",
            secret_name="glcr-secret",
            deployments=(),
            external_secrets=(),
            secret_store_refs=(),
            target_secret_status=TargetSecretStatus.missing("default", "glcr-secret", "secret not found"),
            events=(),
        )
        signals: list[Signal] = []
        findings: list[Finding] = []
        next_checks: list[NextCheck] = []
        generator = _signal_id_generator()

        hypothesis, issues_detected = assess_image_pull_issues(
            image_pull_secret_insight=insight,
            signals=signals,
            signal_id_generator=generator,
            findings=findings,
            next_checks=next_checks,
        )

        assert issues_detected is False
        assert hypothesis is None

    def test_image_pull_issue_produces_signal(self) -> None:
        """Image pull issue with external secrets should produce a signal."""
        insight = _make_image_pull_secret_insight()
        signals: list[Signal] = []
        findings: list[Finding] = []
        next_checks: list[NextCheck] = []
        generator = _signal_id_generator()

        hypothesis, issues_detected = assess_image_pull_issues(
            image_pull_secret_insight=insight,
            signals=signals,
            signal_id_generator=generator,
            findings=findings,
            next_checks=next_checks,
        )

        assert issues_detected is True
        assert hypothesis is not None
        assert len(signals) == 1
        signal = signals[0]
        assert signal.severity == "high"
        assert signal.layer == Layer.WORKLOAD
        assert "glcr-secret" in signal.description
        assert "supply chain is broken" in signal.description

    def test_signal_id_is_generated(self) -> None:
        """Signal should have a generated ID from the signal_id_generator."""
        insight = _make_image_pull_secret_insight()
        signals: list[Signal] = []
        generator = _signal_id_generator()

        assess_image_pull_issues(
            image_pull_secret_insight=insight,
            signals=signals,
            signal_id_generator=generator,
            findings=[],
            next_checks=[],
        )

        assert len(signals) == 1
        assert signals[0].id.startswith("sig-")

    def test_finding_references_signal_id(self) -> None:
        """Finding should reference the generated signal ID correctly."""
        insight = _make_image_pull_secret_insight()
        signals: list[Signal] = []
        findings: list[Finding] = []
        generator = _signal_id_generator()

        assess_image_pull_issues(
            image_pull_secret_insight=insight,
            signals=signals,
            signal_id_generator=generator,
            findings=findings,
            next_checks=[],
        )

        assert len(findings) == 1
        signal = signals[0]
        finding = findings[0]
        assert signal.id in finding.supporting_signals

    def test_next_check_has_correct_evidence_needed(self) -> None:
        """Next check should have the correct kubectl commands."""
        insight = _make_image_pull_secret_insight()
        next_checks: list[NextCheck] = []
        generator = _signal_id_generator()

        assess_image_pull_issues(
            image_pull_secret_insight=insight,
            signals=[],
            signal_id_generator=generator,
            findings=[],
            next_checks=next_checks,
        )

        assert len(next_checks) == 1
        next_check = next_checks[0]
        assert "externalsecret" in next_check.description.lower()
        assert len(next_check.evidence_needed) == 2
        assert "kubectl describe externalsecret glcr-secret-external" in next_check.evidence_needed[0]
        assert "kubectl describe secret glcr-secret" in next_check.evidence_needed[1]

    def test_hypothesis_is_returned_with_correct_attributes(self) -> None:
        """Hypothesis should be returned with MEDIUM confidence and WORKLOAD layer."""
        insight = _make_image_pull_secret_insight()
        generator = _signal_id_generator()

        hypothesis, issues_detected = assess_image_pull_issues(
            image_pull_secret_insight=insight,
            signals=[],
            signal_id_generator=generator,
            findings=[],
            next_checks=[],
        )

        assert issues_detected is True
        assert hypothesis is not None
        assert hypothesis.probable_layer == Layer.WORKLOAD
        assert hypothesis.confidence.value == "medium"
        assert "glcr-secret" in hypothesis.description
        assert "ExternalSecret" in hypothesis.description
        assert "UpdateFailed" in hypothesis.description
        assert hypothesis.what_would_falsify

    def test_multiple_signal_ids_generated_in_order(self) -> None:
        """Multiple signal IDs should be generated in deterministic order."""
        insight = _make_image_pull_secret_insight()
        signals: list[Signal] = []
        findings: list[Finding] = []
        next_checks: list[NextCheck] = []
        generator = _signal_id_generator()

        assess_image_pull_issues(
            image_pull_secret_insight=insight,
            signals=signals,
            signal_id_generator=generator,
            findings=findings,
            next_checks=next_checks,
        )

        # Should have 1 signal + 1 finding = 2 IDs
        assert len(signals) == 1
        assert len(findings) == 1
        # Hypothesis also generates an ID
        assert signals[0].id == "sig-1"
        assert findings[0].id == "sig-2"
