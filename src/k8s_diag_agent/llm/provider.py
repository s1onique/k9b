"""Provider-agnostic seam for LLM assessments."""
from __future__ import annotations

import logging
from typing import Any

from ..collect.cluster_snapshot import ClusterSnapshot
from ..compare.two_cluster import ClusterComparison
from ..models import ConfidenceLevel, SafetyLevel
from ..security import sanitize_payload
from .assessor_schema import (
    AssessorAssessment,
    AssessorFinding,
    AssessorHypothesis,
    AssessorNextCheck,
    AssessorRecommendedAction,
    AssessorSignal,
)
from .base import LLMAssessmentInput, LLMProvider
from .llamacpp_provider import LlamaCppProvider

# Canonical and legacy provider name constants
OPENAI_COMPATIBLE_PROVIDER_NAME = "openai_compatible"
LEGACY_LLAMACPP_PROVIDER_NAME = "llamacpp"

logger = logging.getLogger(__name__)


def normalize_provider_name(name: str) -> str:
    """Normalize a provider name to its canonical form.

    Args:
        name: The provider name to normalize.

    Returns:
        The canonical provider name. Legacy names are mapped to their canonical
        equivalents with a deprecation warning. Unknown names pass through unchanged.
    """
    normalized = name.lower()
    if normalized == LEGACY_LLAMACPP_PROVIDER_NAME:
        logger.warning(
            "Provider name %r is deprecated. Use %r instead.",
            LEGACY_LLAMACPP_PROVIDER_NAME,
            OPENAI_COMPATIBLE_PROVIDER_NAME,
        )
        return OPENAI_COMPATIBLE_PROVIDER_NAME
    return normalized


class DefaultLLMProvider(LLMProvider):
    """Simple deterministic provider that summarizes snapshot diffs."""

    def assess(
        self,
        prompt: str,
        payload: LLMAssessmentInput,
        *,
        validate_schema: bool = True,
        max_tokens: int | None = None,
        response_format_json: bool = False,
    ) -> dict[str, Any]:
        differences = payload.comparison.get("differences") or {}
        diff_keys = sorted(differences)
        has_diff = bool(diff_keys)
        signal_description = (
            "Difference detected between snapshots: " + ", ".join(diff_keys)
            if has_diff
            else "Snapshots are equivalent across tracked dimensions."
        )
        signals = [
            AssessorSignal(
                id="snapshot-difference",
                description=signal_description,
                layer="observability",
                evidence_id="comparison.diff",
                severity="warning" if has_diff else "info",
            )
        ]
        findings = [
            AssessorFinding(
                description=(
                    "Node/helm/CRD drift observed in the last capture comparison."
                    if has_diff
                    else "No actionable drift detected."
                ),
                supporting_signals=[signal.description for signal in signals],
                layer="workflow",
            )
        ]
        hypothesis_confidence = ConfidenceLevel.MEDIUM if has_diff else ConfidenceLevel.LOW
        hypotheses = [
            AssessorHypothesis(
                description=(
                    "Differences likely point to a recent rollout or scaling event."
                    if has_diff
                    else "Clusters appear synchronized; maintain observability checks."
                ),
                confidence=hypothesis_confidence,
                probable_layer="node" if has_diff else "observability",
                what_would_falsify="Confirm with node and helm status once more." if has_diff else "Detect a difference to contradict this assessment.",
            )
        ]
        next_checks = [
            AssessorNextCheck(
                description="Re-run node count and Helm release listings in both clusters.",
                owner="platform-engineer",
                method="kubectl",
                evidence_needed=[
                    "kubectl get nodes --all-namespaces",
                    "helm list --all-namespaces --output json",
                ],
            )
        ]
        recommended = AssessorRecommendedAction(
            type="observation",
            description=(
                "Monitor the nodes and Helm charts until another diff emerges."
                if has_diff
                else "Continue observational monitoring."
            ),
            references=["comparison.diff"],
            safety_level=SafetyLevel.LOW_RISK,
        )
        assessment = AssessorAssessment(
            observed_signals=signals,
            findings=findings,
            hypotheses=hypotheses,
            next_evidence_to_collect=next_checks,
            recommended_action=recommended,
            safety_level=SafetyLevel.LOW_RISK,
            probable_layer_of_origin=hypotheses[0].probable_layer,
            overall_confidence=hypothesis_confidence,
        )
        return assessment.to_dict()


# Build the provider registry
_llama_cpp_provider = LlamaCppProvider()

PROVIDERS: dict[str, LLMProvider] = {
    "default": DefaultLLMProvider(),
    # Canonical name
    OPENAI_COMPATIBLE_PROVIDER_NAME: _llama_cpp_provider,
    # Legacy alias (temporary compatibility fallback during migration)
    LEGACY_LLAMACPP_PROVIDER_NAME: _llama_cpp_provider,
}

DEFAULT_PROVIDER_NAME = "default"
AVAILABLE_PROVIDERS = tuple(sorted(PROVIDERS.keys()))


def get_provider(name: str | None = None) -> LLMProvider:
    key = normalize_provider_name(name or DEFAULT_PROVIDER_NAME)
    if key not in PROVIDERS:
        available = ", ".join(sorted(PROVIDERS.keys()))
        raise ValueError(f"Unknown provider '{name}'. Available: {available}")
    return PROVIDERS[key]


def build_assessment_input(
    primary: ClusterSnapshot, secondary: ClusterSnapshot, comparison: ClusterComparison
) -> LLMAssessmentInput:
    metadata_payload: dict[str, Any] | None
    if comparison.metadata:
        metadata_payload = comparison.metadata.to_dict()
    else:
        metadata_payload = None
    return LLMAssessmentInput(
        primary_snapshot=sanitize_payload(primary.to_dict()),
        secondary_snapshot=sanitize_payload(secondary.to_dict()),
        comparison=sanitize_payload({"differences": comparison.differences}),
        comparison_metadata=sanitize_payload(metadata_payload) if metadata_payload else None,
        collection_statuses=sanitize_payload(
            {
                "primary": primary.collection_status.to_dict(),
                "secondary": secondary.collection_status.to_dict(),
            }
        ),
    )
