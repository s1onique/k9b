"""Deterministic planner for provider suggested next checks."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ..external_analysis.artifact import ExternalAnalysisArtifact, ExternalAnalysisStatus
from .review_input import ReviewEnrichmentInput, ReviewSelectionContext, build_review_enrichment_input


class CommandFamily(StrEnum):
    KUBECTL_GET = "kubectl-get"
    KUBECTL_DESCRIBE = "kubectl-describe"
    KUBECTL_LOGS = "kubectl-logs"
    KUBECTL_GET_CRD = "kubectl-get-crd"
    UNKNOWN = "unknown"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CostEstimate(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().strip().split())


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


def _detect_command_family(text: str) -> CommandFamily:
    normalized = text.lower()
    if "kubectl logs" in normalized or "logs" in normalized and "kubectl" in normalized:
        return CommandFamily.KUBECTL_LOGS
    if "kubectl describe" in normalized or "describe" in normalized:
        return CommandFamily.KUBECTL_DESCRIBE
    if "kubectl get" in normalized:
        if "crd" in normalized:
            return CommandFamily.KUBECTL_GET_CRD
        return CommandFamily.KUBECTL_GET
    if "describe" in normalized:
        return CommandFamily.KUBECTL_DESCRIBE
    return CommandFamily.UNKNOWN


def _detect_expected_signal(text: str) -> str | None:
    normalized = text.lower()
    if any(keyword in normalized for keyword in ("logs", "log file", "pod logs")):
        return "logs"
    if any(keyword in normalized for keyword in ("event", "events", "warning")):
        return "events"
    if any(keyword in normalized for keyword in ("metric", "latency", "cpu", "memory", "iops")):
        return "metrics"
    if any(keyword in normalized for keyword in ("rollout", "deployment", "replica", "cronjob")):
        return "rollout"
    if any(keyword in normalized for keyword in ("storage", "pvc", "volume")):
        return "storage"
    return None


MUTATION_KEYWORDS = (
    "apply",
    "delete",
    "scale",
    "patch",
    "restart",
    "rollout",
    "upgrade",
    "replace",
    "set",
    "edit",
    "create",
)


def _mentions_mutation(text: str) -> bool:
    normalized = text.lower()
    return any(keyword in normalized for keyword in MUTATION_KEYWORDS)


def _risk_from_family(family: CommandFamily) -> RiskLevel:
    if family in (CommandFamily.KUBECTL_LOGS, CommandFamily.KUBECTL_DESCRIBE):
        return RiskLevel.LOW
    if family in (CommandFamily.KUBECTL_GET, CommandFamily.KUBECTL_GET_CRD):
        return RiskLevel.MEDIUM
    return RiskLevel.HIGH


def _confidence_level(safe: bool, family: CommandFamily) -> str:
    if safe and family != CommandFamily.UNKNOWN:
        return "high"
    if family == CommandFamily.UNKNOWN:
        return "low"
    return "medium"


def _cost_from_risk(risk: RiskLevel) -> CostEstimate:
    if risk == RiskLevel.LOW:
        return CostEstimate.LOW
    if risk == RiskLevel.MEDIUM:
        return CostEstimate.MEDIUM
    return CostEstimate.HIGH


def _normalize_description(value: str) -> str:
    return _normalize_text(value)


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


def _find_similar_description(candidate_key: str, evidence_map: Mapping[str, str]) -> str | None:
    for normalized, original in evidence_map.items():
        if not normalized:
            continue
        if candidate_key == normalized:
            return original
        if candidate_key in normalized or normalized in candidate_key:
            return original
    return None


@dataclass(frozen=True)
class NextCheckCandidate:
    description: str
    target_cluster: str | None
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

    def to_dict(self) -> dict[str, object | str | bool]:
        return {
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
        }


@dataclass(frozen=True)
class NextCheckPlan:
    run_id: str
    review_path: Path
    enrichment_artifact_path: str | None
    candidates: tuple[NextCheckCandidate, ...]

    def to_payload(self) -> dict[str, object | None]:
        return {
            "review_path": str(self.review_path),
            "enrichment_artifact_path": self.enrichment_artifact_path,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


def plan_next_checks(
    review_path: Path,
    run_id: str,
    enrichment_artifact: ExternalAnalysisArtifact,
) -> NextCheckPlan | None:
    if enrichment_artifact.status != ExternalAnalysisStatus.SUCCESS:
        return None
    checks = enrichment_artifact.suggested_next_checks
    if not checks:
        return None
    try:
        context = build_review_enrichment_input(review_path, run_id)
    except Exception:
        return None
    evidence_map = _collect_existing_evidence(context)
    selections = context.selections
    candidates: list[NextCheckCandidate] = []
    for candidate_text in checks:
        if not candidate_text or not isinstance(candidate_text, str):
            continue
        selection = _match_selection_for_text(candidate_text, selections)
        target_cluster = selection.label if selection else None
        source_reason = None
        if selection:
            reasons_entry = selection.entry.get("reasons")
            if isinstance(reasons_entry, Sequence):
                for reason_item in reasons_entry:
                    if isinstance(reason_item, str) and reason_item:
                        source_reason = reason_item
                        break
        if not source_reason and enrichment_artifact.summary:
            source_reason = enrichment_artifact.summary
        family = _detect_command_family(candidate_text)
        risk = _risk_from_family(family)
        expected_signal = _detect_expected_signal(candidate_text)
        candidate_key = _normalize_description(candidate_text)
        duplicate_description = _find_similar_description(candidate_key, evidence_map)
        duplicate = bool(duplicate_description)
        mutation_flag = _mentions_mutation(candidate_text)
        safe = family != CommandFamily.UNKNOWN and not mutation_flag and not duplicate
        requires_approval = not safe or duplicate
        gating_reason: str | None = None
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
        candidate = NextCheckCandidate(
            description=candidate_text.strip(),
            target_cluster=target_cluster,
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
        )
        candidates.append(candidate)
    if not candidates:
        return None
    return NextCheckPlan(
        run_id=run_id,
        review_path=review_path,
        enrichment_artifact_path=enrichment_artifact.artifact_path,
        candidates=tuple(candidates),
    )
