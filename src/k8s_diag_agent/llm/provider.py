"""Provider-agnostic seam for LLM assessments."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict

from ..collect.cluster_snapshot import ClusterSnapshot
from ..compare.two_cluster import ClusterComparison
from ..models import ConfidenceLevel, SafetyLevel
from .assessor_schema import (
    AssessorAssessment,
    AssessorFinding,
    AssessorHypothesis,
    AssessorNextCheck,
    AssessorRecommendedAction,
    AssessorSignal,
)


@dataclass(frozen=True)
class LLMAssessmentInput:
    primary_snapshot: Dict[str, Any]
    secondary_snapshot: Dict[str, Any]
    comparison: Dict[str, Any]
    collection_statuses: Dict[str, Dict[str, Any]]


class LLMProvider(ABC):
    """Provider contract for producing structured assessments."""

    @abstractmethod
    def assess(self, prompt: str, payload: LLMAssessmentInput) -> Dict[str, Any]:
        ...


class DefaultLLMProvider(LLMProvider):
    """Simple deterministic provider that summarizes snapshot diffs."""

    def assess(self, prompt: str, payload: LLMAssessmentInput) -> Dict[str, Any]:
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


PROVIDERS: Dict[str, LLMProvider] = {"default": DefaultLLMProvider()}
DEFAULT_PROVIDER_NAME = "default"
AVAILABLE_PROVIDERS = tuple(PROVIDERS.keys())


def get_provider(name: str | None = None) -> LLMProvider:
    key = (name or DEFAULT_PROVIDER_NAME).lower()
    if key not in PROVIDERS:
        raise ValueError(f"Unknown provider '{name}'. Available: {', '.join(PROVIDERS)}")
    return PROVIDERS[key]


def build_assessment_input(
    primary: ClusterSnapshot, secondary: ClusterSnapshot, comparison: ClusterComparison
) -> LLMAssessmentInput:
    return LLMAssessmentInput(
        primary_snapshot=primary.to_dict(),
        secondary_snapshot=secondary.to_dict(),
        comparison={"differences": comparison.differences},
        collection_statuses={
            "primary": primary.collection_status.to_dict(),
            "secondary": secondary.collection_status.to_dict(),
        },
    )
