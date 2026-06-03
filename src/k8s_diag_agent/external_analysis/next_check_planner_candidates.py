"""Candidate construction and payload shaping for next check planner."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING, Any

from ..external_analysis.artifact import ExternalAnalysisArtifact, ExternalAnalysisStatus
from .next_check_planner_models import (
    ApprovalReason,
    BlockingReason,
    CommandFamily,
    CostEstimate,
    DuplicateReason,
    NormalizationReason,
    RiskLevel,
    SafetyReason,
    _confidence_level,
    _cost_from_risk,
    _mentions_mutation,
    _normalize_text,
    _risk_from_family,
    detect_command_family,
    detect_expected_signal,
)
from .result_digest import ExecutionResultDigest
from .review_input import ReviewEnrichmentInput, ReviewSelectionContext, build_review_enrichment_input

if TYPE_CHECKING:
    from .next_check_planner import AlertmanagerRankingProvenance


def _find_execution_result_for_candidate(
    candidate_text: str,
    execution_context: tuple[ExecutionResultDigest, ...],
) -> ExecutionResultDigest | None:
    """Find execution result that relates to the candidate.
    
    Attaches provenance only when there is meaningful overlap:
    - description overlap, or
    - signal overlap
    
    Cluster-only match is not sufficient for provenance attachment.
    
    Args:
        candidate_text: The candidate description text
        execution_context: Current execution context digests
    
    Returns:
        ExecutionResultDigest if a related execution was found, else None
    """
    if not execution_context:
        return None
    
    # Normalize candidate text for comparison
    candidate_lower = candidate_text.lower()
    
    for digest in execution_context:
        # Check description overlap (most reliable provenance signal)
        if digest.candidate_description:
            desc_lower = digest.candidate_description.lower()
            if candidate_lower in desc_lower or desc_lower in candidate_lower:
                return digest
        
        # Check signal overlap (second reliable signal)
        if digest.signals:
            for signal in digest.signals:
                if signal.lower() in candidate_lower:
                    return digest
    
    return None


def _build_execution_provenance(
    execution_digest: ExecutionResultDigest,
) -> dict[str, Any]:
    """Build execution provenance dict from execution digest.
    
    Args:
        execution_digest: The execution result digest to convert
    
    Returns:
        Dictionary with execution provenance for candidate
    """
    return {
        "priorArtifact": execution_digest.artifact_path,
        "priorCandidateId": execution_digest.candidate_id,
        "priorCandidateDescription": execution_digest.candidate_description,
        "priorStatus": execution_digest.status,
        "priorUsefulnessClass": execution_digest.usefulness_class,
        "priorSummary": execution_digest.summary,
        "priorSignals": list(execution_digest.signals),
    }


def _check_duplicate_against_execution(
    candidate_text: str,
    execution_context: tuple[ExecutionResultDigest, ...],
) -> tuple[bool, str | None]:
    """Check if candidate duplicates prior execution result.
    
    Args:
        candidate_text: The candidate description text
        execution_context: Current execution context digests
    
    Returns:
        (is_duplicate, duplicate_description)
    """
    if not execution_context:
        return False, None
    
    candidate_normalized = _normalize_for_dedup(candidate_text)
    
    for digest in execution_context:
        if not digest.candidate_description:
            continue
        
        # Check exact dedup signature match
        exec_normalized = _normalize_for_dedup(digest.candidate_description)
        if candidate_normalized == exec_normalized:
            return True, digest.candidate_description
        
        # Check overlap
        if candidate_normalized in exec_normalized or exec_normalized in candidate_normalized:
            return True, digest.candidate_description
    
    return False, None

# Generic phrase patterns for detecting low-specificity candidates.
# These indicate the model is being cautious/non-specific rather than providing targeted guidance.
_GENERIC_PHRASES = (
    "review status",
    "review cluster",
    "review everything",
    "investigate flagged",
    "investigate flagged resources",
    "investigate resources",
    "assess cluster",
)

_GENERIC_KEYWORDS = ("review", "investigate", "assess", "inspect", "check", "verify")
_GENERIC_STATUS_TERMS = ("status", "resources", "signals", "components", "health", "workload", "everything")


def _normalize_description(value: str) -> str:
    return _normalize_text(value)


def _normalize_for_dedup(value: str) -> str:
    normalized = _normalize_text(value)
    normalized = re.sub(r"\(.*?\)", "", normalized)
    normalized = re.sub(r"\bversion\b\s*\S*", "", normalized)
    normalized = re.sub(r"\b(v?\d+(?:\.\d+)*)\b", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized or _normalize_text(value)


def _build_dedup_signature(description: str, target_cluster: str | None) -> str:
    normalized = _normalize_for_dedup(description)
    target = target_cluster or ""
    return f"{target}|{normalized}"


def _derive_candidate_id(
    description: str,
    target_cluster: str | None,
    source_reason: str | None,
    family: CommandFamily,
) -> str:
    normalized_desc = _normalize_description(description or "")
    components = "|".join(
        (
            normalized_desc,
            target_cluster or "",
            source_reason or "",
            family.value,
        )
    )
    return sha256(components.encode("utf-8")).hexdigest()


def _collect_existing_evidence(context: ReviewEnrichmentInput) -> Mapping[str, str]:
    normalized: dict[str, str] = {}
    for selection in context.selections:
        assessment = selection.assessment or {}
        next_checks = assessment.get("next_evidence_to_collect") or []
        if not isinstance(next_checks, Iterable):
            continue
        for entry in next_checks:
            if not isinstance(entry, Mapping):
                continue
            desc = entry.get("description")
            if not isinstance(desc, str):
                continue
            key = _normalize_description(desc)
            if key:
                normalized[key] = desc
    return normalized


def _find_similar_description(candidate_key: str, evidence_map: Mapping[str, str]) -> tuple[DuplicateReason | None, str | None]:
    for normalized, original in evidence_map.items():
        if not normalized:
            continue
        if candidate_key == normalized:
            return DuplicateReason.EXACT_MATCH, original
        if candidate_key in normalized or normalized in candidate_key:
            return DuplicateReason.OVERLAP, original
    return None, None


def _determine_normalization_reason(
    text: str, selection: ReviewSelectionContext | None, summary: str | None
) -> NormalizationReason:
    normalized = _normalize_text(text)
    if selection:
        label = (selection.label or "").strip()
        context = (selection.context or "").strip()
        if label and label.lower() in normalized:
            return NormalizationReason.SELECTION_LABEL
        if context and context.lower() in normalized:
            return NormalizationReason.SELECTION_CONTEXT
        return NormalizationReason.SELECTION_DEFAULT
    if summary:
        return NormalizationReason.SUMMARY_FALLBACK
    return NormalizationReason.UNKNOWN


def _is_generic_candidate(text: str, family: CommandFamily) -> bool:
    if family != CommandFamily.UNKNOWN:
        return False
    normalized = _normalize_text(text)
    for phrase in _GENERIC_PHRASES:
        if phrase in normalized:
            return True
    if any(keyword in normalized for keyword in _GENERIC_KEYWORDS) and any(
        term in normalized for term in _GENERIC_STATUS_TERMS
    ):
        return True
    if "everything" in normalized or "general" in normalized:
        return True
    return False


def _determine_priority_label(
    *,
    duplicate: bool,
    target_cluster: str | None,
    safe_to_automate: bool,
    family: CommandFamily,
    cost: CostEstimate,
    generic: bool,
) -> str:
    if duplicate or generic or family == CommandFamily.UNKNOWN:
        return "fallback"
    if target_cluster and safe_to_automate and cost == CostEstimate.LOW:
        return "primary"
    return "secondary"


@dataclass(frozen=True)
class NextCheckCandidate:
    candidate_id: str
    description: str
    target_cluster: str | None
    target_context: str | None
    source_reason: str | None
    expected_signal: str | None
    suggested_command_family: CommandFamily
    safe_to_automate: bool
    requires_operator_approval: bool
    risk_level: RiskLevel
    estimated_cost: CostEstimate
    confidence: str
    gating_reason: str | None
    duplicate_of_existing_evidence: bool
    duplicate_evidence_description: str | None
    normalization_reason: str | None
    safety_reason: str | None
    approval_reason: str | None
    duplicate_reason: str | None
    blocking_reason: str | None
    priority_label: str
    # Internal flag for generic candidates (low-specificity from model)
    # Used by ranking to apply -80 penalty; not serialized to dict
    generic_candidate: bool = False
    # Observability: why ranking policy was applied (if any)
    ranking_policy_reason: str | None = None
    # Structured provenance for Alertmanager-driven ranking (if any)
    # Must be AlertmanagerRankingProvenance object (not dict) for attribute access
    alertmanager_provenance: AlertmanagerRankingProvenance | None = None
    # Run-scoped provenance for feedback-based Alertmanager bonus suppression
    # Set when operator marked Alertmanager relevance as not_relevant/noisy in this run
    feedback_adaptation_provenance: dict[str, Any] | None = None
    # Execution result provenance for follow-up planning
    # Set when this candidate is derived from or related to a prior execution result
    execution_provenance: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, object | str | bool]:
        result: dict[str, object | str | bool] = {
            "description": self.description,
            "targetCluster": self.target_cluster,
            "sourceReason": self.source_reason,
            "expectedSignal": self.expected_signal,
            "suggestedCommandFamily": self.suggested_command_family.value,
            "safeToAutomate": self.safe_to_automate,
            "requiresOperatorApproval": self.requires_operator_approval,
            "riskLevel": self.risk_level.value,
            "estimatedCost": self.estimated_cost.value,
            "confidence": self.confidence,
            "gatingReason": self.gating_reason,
            "duplicateOfExistingEvidence": self.duplicate_of_existing_evidence,
            "duplicateEvidenceDescription": self.duplicate_evidence_description,
            "normalizationReason": self.normalization_reason,
            "safetyReason": self.safety_reason,
            "approvalReason": self.approval_reason,
            "duplicateReason": self.duplicate_reason,
            "blockingReason": self.blocking_reason,
            "targetContext": self.target_context,
            "candidateId": self.candidate_id,
            "priorityLabel": self.priority_label,
        }
        if self.ranking_policy_reason is not None:
            result["rankingPolicyReason"] = self.ranking_policy_reason
        if self.alertmanager_provenance is not None:
            result["alertmanagerProvenance"] = self.alertmanager_provenance.to_dict()
        if self.feedback_adaptation_provenance is not None:
            result["feedbackAdaptationProvenance"] = self.feedback_adaptation_provenance
        if self.execution_provenance is not None:
            result["executionProvenance"] = self.execution_provenance
        return result


def _match_selection_for_text(
    text: str, selections: Iterable[ReviewSelectionContext]
) -> ReviewSelectionContext | None:
    normalized = _normalize_text(text)
    for selection in selections:
        label = (selection.label or "").strip()
        context = (selection.context or "").strip()
        if label and label.lower() in normalized:
            return selection
        if context and context.lower() in normalized:
            return selection
    return next(iter(selections), None)


def build_candidates_from_enrichment(
    review_path: str,
    run_id: str,
    enrichment_artifact: ExternalAnalysisArtifact,
    execution_context: tuple[ExecutionResultDigest, ...] = (),
) -> tuple[NextCheckCandidate, ...] | None:
    """Build candidates from enrichment artifact.
    
    Args:
        review_path: Path to the review artifact
        run_id: Run identifier
        enrichment_artifact: The enrichment artifact with suggested next checks
        execution_context: Optional tuple of ExecutionResultDigest from prior
            executions. When provided, candidates can include execution provenance
            based on description/signal overlap. No module-level state is used.
    
    Returns:
        Tuple of NextCheckCandidate if enrichment is successful and checks available.
        Returns None on context building failure (non-fatal).
    """
    if enrichment_artifact.status != ExternalAnalysisStatus.SUCCESS:
        return None
    checks = enrichment_artifact.suggested_next_checks
    if not checks:
        return None
    try:
        from pathlib import Path
        context = build_review_enrichment_input(Path(review_path), run_id)
    except (OSError, ValueError, KeyError):
        # REVIEWED: Non-fatal context building fallback.
        # Silently skip if review artifact cannot be loaded - returns None to caller.
        return None
    evidence_map = _collect_existing_evidence(context)
    selections = context.selections
    candidates: list[NextCheckCandidate] = []
    seen_signatures: set[str] = set()
    for candidate_text in checks:
        if not candidate_text or not isinstance(candidate_text, str):
            continue
        selection = _match_selection_for_text(candidate_text, selections)
        target_cluster = selection.label if selection else None
        target_context = selection.context.strip() if selection and selection.context else None
        source_reason: str | None = None
        if selection:
            reasons_entry = selection.entry.get("reasons")
            if isinstance(reasons_entry, Sequence):
                for reason_item in reasons_entry:
                    if isinstance(reason_item, str) and reason_item:
                        source_reason = reason_item
                        break
        if not source_reason and enrichment_artifact.summary:
            source_reason = enrichment_artifact.summary
        family = detect_command_family(candidate_text)
        risk = _risk_from_family(family)
        expected_signal = detect_expected_signal(candidate_text)
        candidate_key = _normalize_description(candidate_text)
        duplicate_reason_enum, duplicate_description = _find_similar_description(
            candidate_key, evidence_map
        )
        duplicate = duplicate_reason_enum is not None
        mutation_flag = _mentions_mutation(candidate_text)
        safe = family != CommandFamily.UNKNOWN and not mutation_flag and not duplicate
        requires_approval = not safe or duplicate
        gating_reason: str | None = None
        normalization_reason = _determine_normalization_reason(
            candidate_text, selection, enrichment_artifact.summary
        )
        if duplicate:
            safety_reason = SafetyReason.DUPLICATE_EVIDENCE
        elif mutation_flag:
            safety_reason = SafetyReason.MUTATION_DETECTED
        elif family == CommandFamily.UNKNOWN:
            safety_reason = SafetyReason.UNKNOWN_COMMAND
        else:
            safety_reason = SafetyReason.KNOWN_COMMAND
        approval_reason: ApprovalReason | None = None
        if requires_approval:
            if duplicate:
                approval_reason = ApprovalReason.DUPLICATE_EVIDENCE
            elif mutation_flag:
                approval_reason = ApprovalReason.MUTATION_DETECTED
            elif family == CommandFamily.UNKNOWN:
                approval_reason = ApprovalReason.UNKNOWN_COMMAND
            else:
                approval_reason = ApprovalReason.GENERIC
        blocking_reason: BlockingReason | None = None
        if duplicate:
            blocking_reason = BlockingReason.DUPLICATE
        elif mutation_flag:
            blocking_reason = BlockingReason.MUTATION_DETECTED
        elif not safe:
            blocking_reason = BlockingReason.UNKNOWN_COMMAND
        if duplicate:
            gating_reason = (
                f"Matches deterministic next check: {duplicate_description}"
                if duplicate_description
                else "Duplicate of deterministic evidence"
            )
        elif mutation_flag:
            gating_reason = "Step mentions a potentially mutating kubectl command"
        elif family == CommandFamily.UNKNOWN:
            gating_reason = "Command not recognized or too vague"
        cost = _cost_from_risk(risk)
        confidence = _confidence_level(safe, family)
        signature = _build_dedup_signature(candidate_text, target_cluster)
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        is_generic = _is_generic_candidate(candidate_text, family)
        priority_label = _determine_priority_label(
            duplicate=duplicate,
            target_cluster=target_cluster,
            safe_to_automate=safe,
            family=family,
            cost=cost,
            generic=is_generic,
        )
        candidate_id = _derive_candidate_id(
            candidate_text,
            target_cluster,
            source_reason,
            family,
        )
        # Attach execution provenance if candidate relates to prior execution
        # Provenance is attached only on description/signal overlap, not cluster-only
        execution_provenance: dict[str, Any] | None = None
        if execution_context:
            related_digest = _find_execution_result_for_candidate(
                candidate_text, execution_context
            )
            if related_digest:
                execution_provenance = _build_execution_provenance(related_digest)
        
        candidate = NextCheckCandidate(
            candidate_id=candidate_id,
            description=candidate_text.strip(),
            target_cluster=target_cluster,
            target_context=target_context,
            source_reason=source_reason,
            expected_signal=expected_signal,
            suggested_command_family=family,
            safe_to_automate=safe,
            requires_operator_approval=requires_approval,
            risk_level=risk,
            estimated_cost=cost,
            confidence=confidence,
            gating_reason=gating_reason,
            duplicate_of_existing_evidence=duplicate,
            duplicate_evidence_description=duplicate_description,
            normalization_reason=normalization_reason.value,
            safety_reason=safety_reason.value,
            approval_reason=approval_reason.value if approval_reason else None,
            duplicate_reason=duplicate_reason_enum.value if duplicate_reason_enum else None,
            blocking_reason=blocking_reason.value if blocking_reason else None,
            priority_label=priority_label,
            generic_candidate=is_generic,
            execution_provenance=execution_provenance,
        )
        candidates.append(candidate)
    return tuple(candidates) if candidates else None
