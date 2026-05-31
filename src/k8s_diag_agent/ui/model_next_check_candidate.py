"""View model for next-check candidates (UI model module).

This module contains the candidate view model and builder extracted from model.py.
It exists to enable incremental modularization without changing behavior.

Dependency direction:
- model_next_check_candidate.py -> model_primitives.py, model_alertmanager.py,
  model_feedback.py, ui_planner_queue
- model.py and model_next_check_plan.py import from this module for re-export/compatibility.
"""

from __future__ import annotations

from collections.abc import Mapping

from .model_alertmanager import (
    _build_alertmanager_provenance_view,
)
from .model_feedback import (
    _build_feedback_adaptation_provenance_view,
)
from .model_next_check_plan import NextCheckCandidateView
from .model_primitives import (
    _coerce_optional_int,
    _coerce_optional_str,
    _coerce_str,
)


def _build_next_check_candidate_view(raw: Mapping[str, object]) -> NextCheckCandidateView:
    """Build NextCheckCandidateView from raw JSON data.

    This is the full builder that derives priority_rationale and ranking_reason
    via ui_planner_queue helpers.
    """
    # Import here to avoid circular dependency at module level.
    # This module is a source module and does NOT import from model.py.
    from ..health.ui_planner_queue import _derive_priority_rationale, _derive_ranking_reason

    provenance_raw = raw.get("alertmanagerProvenance") or raw.get("alertmanager_provenance")
    provenance = _build_alertmanager_provenance_view(provenance_raw)
    feedback_provenance_raw = raw.get("feedbackAdaptationProvenance") or raw.get("feedback_adaptation_provenance")
    feedback_provenance = _build_feedback_adaptation_provenance_view(feedback_provenance_raw)

    return NextCheckCandidateView(
        alertmanager_provenance=provenance,
        feedback_adaptation_provenance=feedback_provenance,
        candidate_id=_coerce_optional_str(raw.get("candidateId")),
        description=_coerce_str(raw.get("description")),
        target_cluster=_coerce_optional_str(raw.get("targetCluster")),
        source_reason=_coerce_optional_str(raw.get("sourceReason")),
        expected_signal=_coerce_optional_str(raw.get("expectedSignal")),
        suggested_command_family=_coerce_optional_str(raw.get("suggestedCommandFamily")),
        safe_to_automate=bool(raw.get("safeToAutomate")),
        requires_operator_approval=bool(raw.get("requiresOperatorApproval")),
        risk_level=_coerce_str(raw.get("riskLevel")),
        estimated_cost=_coerce_str(raw.get("estimatedCost")),
        confidence=_coerce_str(raw.get("confidence")),
        gating_reason=_coerce_optional_str(raw.get("gatingReason")),
        duplicate_of_existing_evidence=bool(raw.get("duplicateOfExistingEvidence")),
        duplicate_evidence_description=_coerce_optional_str(
            raw.get("duplicateEvidenceDescription")
        ),
        approval_status=_coerce_optional_str(raw.get("approvalStatus")),
        approval_artifact_path=_coerce_optional_str(raw.get("approvalArtifactPath")),
        approval_timestamp=_coerce_optional_str(raw.get("approvalTimestamp")),
        candidate_index=_coerce_optional_int(raw.get("candidateIndex")),
        normalization_reason=_coerce_optional_str(raw.get("normalizationReason")),
        safety_reason=_coerce_optional_str(raw.get("safetyReason")),
        approval_reason=_coerce_optional_str(raw.get("approvalReason")),
        duplicate_reason=_coerce_optional_str(raw.get("duplicateReason")),
        blocking_reason=_coerce_optional_str(raw.get("blockingReason")),
        approval_state=_coerce_optional_str(raw.get("approvalState")),
        execution_state=_coerce_optional_str(raw.get("executionState")),
        outcome_status=_coerce_optional_str(raw.get("outcomeStatus")),
        latest_artifact_path=_coerce_optional_str(raw.get("latestArtifactPath")),
        latest_timestamp=_coerce_optional_str(raw.get("latestTimestamp")),
        priority_label=_coerce_optional_str(raw.get("priorityLabel")),
        priority_rationale=_derive_priority_rationale(raw),
        ranking_reason=_derive_ranking_reason(raw),
    )
