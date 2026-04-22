"""Run-scoped Alertmanager relevance feedback for ranking adaptation.

This module provides run-scoped learning: if an executed next-check had Alertmanager
provenance and the operator later marked Alertmanager relevance as `not_relevant` or
`noisy`, then for the same run only, similar Alertmanager-driven candidates are
demoted with explicit provenance.

No cross-run persistence of learned weighting is introduced.

Design constraints:
- artifact-first
- evidence-first
- preserve operator trust
- run-scoped only
- no hidden durable learning
- operator-visible provenance for any adaptation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .artifact import AlertmanagerRelevanceClass, ExternalAnalysisArtifact, ExternalAnalysisPurpose


class FeedbackAdaptationReason(StrEnum):
    """Why Alertmanager influence was adapted based on operator feedback."""
    NOT_RELEVANT = "operator-marked-not-relevant"
    NOISY = "operator-marked-noisy"


@dataclass(frozen=True)
class DimensionFeedback:
    """Feedback for a specific Alertmanager dimension."""
    dimension: str  # "namespace", "cluster", "service"
    values: tuple[str, ...]  # specific values marked as not relevant/noisy
    reason: FeedbackAdaptationReason
    source_execution_index: int  # index of the execution artifact that provided feedback
    source_execution_artifact: str  # path to the execution artifact


@dataclass(frozen=True)
class RunScopedAlertmanagerFeedback:
    """Collected Alertmanager relevance feedback for the current run.
    
    This is built from execution artifacts with alertmanager_relevance judgments
    and used during ranking to demote similar Alertmanager-driven candidates.
    
    All adaptation is run-scoped only - no cross-run persistence.
    """
    feedback_entries: tuple[DimensionFeedback, ...] = field(default_factory=tuple)
    # Summary for provenance display
    total_entries: int = 0
    namespaces_with_feedback: tuple[str, ...] = field(default_factory=tuple)
    clusters_with_feedback: tuple[str, ...] = field(default_factory=tuple)
    services_with_feedback: tuple[str, ...] = field(default_factory=tuple)

    def is_relevant_for_candidate(
        self,
        candidate_target_cluster: str | None,
        candidate_target_context: str | None,
        candidate_description: str | None,
    ) -> tuple[bool, FeedbackAdaptationReason | None, str | None]:
        """Check if candidate matches any feedback-marked dimension.
        
        Returns:
            (matches_feedback, adaptation_reason, adaptation_explanation)
        """
        if not self.feedback_entries:
            return False, None, None

        # Check namespace match
        if candidate_target_context:
            context_lower = candidate_target_context.lower()
            for entry in self.feedback_entries:
                if entry.dimension == "namespace":
                    for value in entry.values:
                        if value.lower() in context_lower:
                            return True, entry.reason, f"namespace '{value}' was marked {entry.reason.value} in this run"

        # Check cluster match
        if candidate_target_cluster:
            cluster_lower = candidate_target_cluster.lower()
            for entry in self.feedback_entries:
                if entry.dimension == "cluster":
                    for value in entry.values:
                        if value.lower() in cluster_lower or cluster_lower in value.lower():
                            return True, entry.reason, f"cluster '{value}' was marked {entry.reason.value} in this run"

        # Check service match in description/context
        search_text = f"{candidate_description or ''} {candidate_target_context or ''}".lower()
        for entry in self.feedback_entries:
            if entry.dimension == "service":
                for value in entry.values:
                    if value.lower() in search_text:
                        return True, entry.reason, f"service '{value}' was marked {entry.reason.value} in this run"

        return False, None, None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for provenance/debugging."""
        return {
            "feedback_entries": [
                {
                    "dimension": entry.dimension,
                    "values": list(entry.values),
                    "reason": entry.reason.value,
                    "source_execution_index": entry.source_execution_index,
                }
                for entry in self.feedback_entries
            ],
            "total_entries": self.total_entries,
            "namespaces_with_feedback": list(self.namespaces_with_feedback),
            "clusters_with_feedback": list(self.clusters_with_feedback),
            "services_with_feedback": list(self.services_with_feedback),
        }


def build_feedback_from_execution_artifacts(
    artifacts: tuple[ExternalAnalysisArtifact, ...],
) -> RunScopedAlertmanagerFeedback:
    """Build run-scoped feedback from execution artifacts with Alertmanager relevance judgments.
    
    Args:
        artifacts: External analysis artifacts for the current run (purpose: next-check-execution)
        compact: Alertmanager compact from current run (for extracting dimension values)
    
    Returns:
        RunScopedAlertmanagerFeedback with collected feedback, or empty feedback if none exists.
    """
    if not artifacts:
        return RunScopedAlertmanagerFeedback()

    feedback_entries: list[DimensionFeedback] = []
    namespaces_with_feedback: set[str] = set()
    clusters_with_feedback: set[str] = set()
    services_with_feedback: set[str] = set()

    for index, artifact in enumerate(artifacts):
        # Only process execution artifacts with Alertmanager relevance feedback
        if artifact.purpose != ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION:
            continue
        if artifact.alertmanager_relevance is None:
            continue
        if artifact.alertmanager_relevance not in (
            AlertmanagerRelevanceClass.NOT_RELEVANT,
            AlertmanagerRelevanceClass.NOISY,
        ):
            continue

        # Get the provenance that links this execution to Alertmanager dimensions
        provenance = artifact.alertmanager_provenance
        if not provenance:
            continue

        relevance = artifact.alertmanager_relevance
        adaptation_reason = (
            FeedbackAdaptationReason.NOT_RELEVANT
            if relevance == AlertmanagerRelevanceClass.NOT_RELEVANT
            else FeedbackAdaptationReason.NOISY
        )

        # Extract matched dimensions from provenance
        matched_dims_raw = provenance.get("matchedDimensions")
        matched_dims: list[str] = []
        if isinstance(matched_dims_raw, list):
            matched_dims = [str(d) for d in matched_dims_raw if isinstance(d, str)]
        
        matched_vals_raw = provenance.get("matchedValues")
        if not isinstance(matched_vals_raw, dict):
            matched_vals: dict[str, list[object]] = {}
        else:
            matched_vals = matched_vals_raw

        # Process each dimension that was matched
        for dim in matched_dims:
            if not isinstance(dim, str):
                continue
            if dim not in matched_vals:
                continue
            
            values = tuple(str(v) for v in matched_vals.get(dim, []) if v)
            if not values:
                continue

            feedback_entries.append(DimensionFeedback(
                dimension=dim,
                values=values,
                reason=adaptation_reason,
                source_execution_index=index,
                source_execution_artifact=artifact.artifact_path or "",
            ))

            # Track feedback for efficient lookup
            if dim == "namespace":
                namespaces_with_feedback.update(values)
            elif dim == "cluster":
                clusters_with_feedback.update(values)
            elif dim == "service":
                services_with_feedback.update(values)

    return RunScopedAlertmanagerFeedback(
        feedback_entries=tuple(feedback_entries),
        total_entries=len(feedback_entries),
        namespaces_with_feedback=tuple(namespaces_with_feedback),
        clusters_with_feedback=tuple(clusters_with_feedback),
        services_with_feedback=tuple(services_with_feedback),
    )


# Suppression penalty when Alertmanager dimension matches operator feedback
# This is applied to the bonus that would otherwise be added.
# Using a moderate suppression to be noticeable but not overwhelming.
_SUPPRESSION_PENALTY = -100


def compute_feedback_adjusted_bonus(
    base_bonus: int,
    candidate_target_cluster: str | None,
    candidate_target_context: str | None,
    candidate_description: str | None,
    feedback: RunScopedAlertmanagerFeedback,
) -> tuple[int, str | None, dict[str, Any] | None]:
    """Compute feedback-adjusted Alertmanager bonus with explicit provenance.
    
    Args:
        base_bonus: The bonus computed from Alertmanager signal matching
        candidate_target_cluster: Target cluster of the candidate
        candidate_target_context: Target context (often contains namespace)
        candidate_description: Description of the candidate command
        feedback: Run-scoped feedback context
    
    Returns:
        (adjusted_bonus, adaptation_rationale, adaptation_provenance)
        If no feedback adjustment was needed, returns (base_bonus, None, None)
    """
    if base_bonus <= 0 or not feedback.feedback_entries:
        return base_bonus, None, None

    matches_feedback, adaptation_reason, explanation = feedback.is_relevant_for_candidate(
        candidate_target_cluster,
        candidate_target_context,
        candidate_description,
    )

    if not matches_feedback:
        return base_bonus, None, None

    # Apply suppression penalty
    suppressed_bonus = max(base_bonus + _SUPPRESSION_PENALTY, 0)  # Don't go negative

    assert adaptation_reason is not None, "adaptation_reason should not be None when matches_feedback is True"

    adaptation_rationale = (
        f"alertmanager-feedback:suppressed:reason={adaptation_reason.value}:"
        f"original_bonus={base_bonus}:suppressed_bonus={suppressed_bonus}:{explanation}"
    )

    adaptation_provenance = {
        "feedback_adaptation": True,
        "adaptation_reason": adaptation_reason.value,
        "original_bonus": base_bonus,
        "suppressed_bonus": suppressed_bonus,
        "penalty_applied": _SUPPRESSION_PENALTY,
        "explanation": explanation,
        "feedback_summary": {
            "total_entries": feedback.total_entries,
            "namespaces_with_feedback": list(feedback.namespaces_with_feedback),
            "clusters_with_feedback": list(feedback.clusters_with_feedback),
            "services_with_feedback": list(feedback.services_with_feedback),
        },
    }

    return suppressed_bonus, adaptation_rationale, adaptation_provenance
