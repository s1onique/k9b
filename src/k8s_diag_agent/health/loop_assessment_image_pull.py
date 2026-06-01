"""Image-pull assessment helpers for health assessment building."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from ..models import ConfidenceLevel, Finding, Hypothesis, Layer, NextCheck, Signal
from .image_pull_secret import ImagePullSecretInsight

__all__ = [
    "assess_image_pull_issues",
]


def assess_image_pull_issues(
    *,
    image_pull_secret_insight: ImagePullSecretInsight | None,
    signals: list[Signal],
    signal_id_generator: Callable[[], str],
    findings: list[Finding],
    next_checks: list[NextCheck],
) -> tuple[Hypothesis | None, bool]:
    """Assess image pull secret issues and record signals, findings, and next checks.

    This function extracts image-pull secret assessment logic from build_health_assessment().
    It processes an ImagePullSecretInsight to detect broken image pull secret supply chains.

    Returns:
        A tuple of (insight_hypothesis, issues_detected) where:
        - insight_hypothesis: The Hypothesis if an issue was detected, None otherwise
        - issues_detected: True if any image pull issue was detected, False otherwise
    """
    if not image_pull_secret_insight or not image_pull_secret_insight.external_secrets:
        return None, False

    details = image_pull_secret_insight
    target_status = details.target_secret_status
    primary_external = details.external_secrets[0]

    def _add_signal(description: str, severity: str, layer: Layer) -> Signal:
        signal = Signal(
            id=signal_id_generator(),
            description=description,
            layer=layer,
            evidence_id="",
            severity=severity,
        )
        signals.append(signal)
        return signal

    def _record_finding(description: str, layer: Layer, signal_ids: Sequence[str]) -> None:
        if not signal_ids:
            return
        findings.append(
            Finding(
                id=signal_id_generator(),
                description=description,
                supporting_signals=list(signal_ids),
                layer=layer,
            )
        )

    signal = _add_signal(
        (f"Registry image pull secret {details.secret_name} supply chain is broken in {details.namespace}."),
        "high",
        Layer.WORKLOAD,
    )
    _record_finding(
        (f"ExternalSecret {primary_external.name} reports {primary_external.status_reason}: {primary_external.status_message or 'missing secret'} for {details.secret_name}."),
        Layer.WORKLOAD,
        [signal.id],
    )
    next_checks.append(
        NextCheck(
            description="Review the ExternalSecret and backing Kubernetes secret for the failing image pull secret.",
            owner="platform engineer",
            method="kubectl",
            evidence_needed=[
                f"kubectl describe externalsecret {primary_external.name} -n {details.namespace}",
                f"kubectl describe secret {details.secret_name} -n {details.namespace}",
            ],
        )
    )

    insight_hypothesis = Hypothesis(
        id=signal_id_generator(),
        description=(f"Image pull secret {details.secret_name} is missing because ExternalSecret {primary_external.name} failed to update the secret ({primary_external.status_reason})."),
        confidence=ConfidenceLevel.MEDIUM,
        probable_layer=Layer.WORKLOAD,
        what_would_falsify=(f"ExternalSecret {primary_external.name} reports Ready and secret {target_status.name or details.secret_name} exists."),
    )

    return insight_hypothesis, True
