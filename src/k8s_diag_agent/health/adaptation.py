"""Deterministic adaptation helpers for health review proposals."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..models import ConfidenceLevel
from .baseline import BaselinePolicy
from .review_feedback import DrilldownSelection, HealthReviewArtifact, QualityMetric

_RELEASE_DRIFT_RE = re.compile(r"watched Helm release (?P<release>[^\s]+) drift", re.IGNORECASE)
_CRD_DRIFT_RE = re.compile(r"watched CRD (?P<family>[^\s]+) storage drift", re.IGNORECASE)


@dataclass(frozen=True)
class HealthProposal:
    proposal_id: str
    source_run_id: str
    source_artifact_path: str
    target: str
    proposed_change: str
    rationale: str
    confidence: ConfidenceLevel
    expected_benefit: str
    rollback_note: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "source_run_id": self.source_run_id,
            "source_artifact_path": self.source_artifact_path,
            "target": self.target,
            "proposed_change": self.proposed_change,
            "rationale": self.rationale,
            "confidence": self.confidence.value,
            "expected_benefit": self.expected_benefit,
            "rollback_note": self.rollback_note,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "HealthProposal":
        if not isinstance(raw, Mapping):
            raise ValueError("Proposal must be a mapping")
        confidence_value = raw.get("confidence")
        if not confidence_value:
            raise ValueError("Proposal missing confidence level")
        try:
            confidence = ConfidenceLevel(str(confidence_value))
        except ValueError as exc:
            raise ValueError(f"Invalid confidence value: {confidence_value}") from exc
        return cls(
            proposal_id=str(raw.get("proposal_id") or ""),
            source_run_id=str(raw.get("source_run_id") or ""),
            source_artifact_path=str(raw.get("source_artifact_path") or ""),
            target=str(raw.get("target") or ""),
            proposed_change=str(raw.get("proposed_change") or ""),
            rationale=str(raw.get("rationale") or ""),
            confidence=confidence,
            expected_benefit=str(raw.get("expected_benefit") or ""),
            rollback_note=str(raw.get("rollback_note") or ""),
        )


@dataclass(frozen=True)
class ProposalEvaluation:
    proposal_id: str
    noise_reduction: str
    signal_loss: str
    test_outcome: str


def _metric(review: HealthReviewArtifact, dimension: str) -> Optional[QualityMetric]:
    for metric in review.quality_summary:
        if metric.dimension == dimension:
            return metric
    return None


def collect_trigger_details(triggers_dir: Path, run_id: str) -> Tuple[Mapping[str, Any], ...]:
    if not triggers_dir.exists():
        return ()
    details: List[Mapping[str, Any]] = []
    pattern = f"{run_id}-*-trigger.json"
    for path in sorted(triggers_dir.glob(pattern)):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for entry in raw.get("trigger_details", []):
            if isinstance(entry, Mapping):
                details.append(entry)
    return tuple(details)


def _dedupe_by_key(items: Iterable[Tuple[str, Mapping[str, Any]]]) -> List[Tuple[str, Mapping[str, Any]]]:
    seen: set[str] = set()
    unique: List[Tuple[str, Mapping[str, Any]]] = []
    for key, item in items:
        if key in seen:
            continue
        seen.add(key)
        unique.append((key, item))
    return unique


def _parse_release_key(reason: str) -> Optional[str]:
    match = _RELEASE_DRIFT_RE.search(reason)
    if not match:
        return None
    return match.group("release")


def _parse_crd_family(reason: str) -> Optional[str]:
    match = _CRD_DRIFT_RE.search(reason)
    if not match:
        return None
    return match.group("family")


def _split_pair(value: str) -> Tuple[str, ...]:
    if not value:
        return ()
    parts = [segment.strip() for segment in value.split("vs")]
    return tuple(part for part in parts if part)


def _normalize_version(value: str) -> str:
    return value.lstrip("vV").strip()


def generate_proposals_from_review(
    review: HealthReviewArtifact,
    review_path: Path,
    run_id: str,
    warning_threshold: int,
    baseline_policy: BaselinePolicy,
    trigger_details: Sequence[Mapping[str, Any]] | None = None,
) -> Tuple[HealthProposal, ...]:
    selection = review.selected_drilldowns[0] if review.selected_drilldowns else None
    base_path = str(review_path)
    proposals: List[HealthProposal] = []
    if selection:
        proposal = _warning_threshold_proposal(
            run_id,
            base_path,
            warning_threshold,
            selection,
            review.run_id,
        )
        if proposal:
            proposals.append(proposal)
    if selection:
        noise_reason = _choose_noise_reason(selection)
        if noise_reason:
            proposal = _noise_reason_proposal(run_id, base_path, selection, noise_reason, review.run_id)
            proposals.append(proposal)
    release_details = [detail for detail in (trigger_details or ()) if detail.get("type") == "watched_helm_release"]
    crd_details = [detail for detail in (trigger_details or ()) if detail.get("type") == "watched_crd"]
    proposals.extend(_baseline_release_proposals(run_id, base_path, review.run_id, baseline_policy, release_details))
    proposals.extend(_baseline_crd_proposals(run_id, base_path, review.run_id, baseline_policy, crd_details))
    ranking_metric = _metric(review, "drilldown_prioritization")
    ranking_proposal = _drilldown_ranking_proposal(run_id, base_path, review.run_id, ranking_metric)
    if ranking_proposal:
        proposals.append(ranking_proposal)
    return tuple(dict.fromkeys(proposals))


def _warning_threshold_proposal(
    run_id: str,
    review_path: str,
    current_threshold: int,
    selection: DrilldownSelection,
    source_run_id: str,
) -> Optional[HealthProposal]:
    warnings = selection.warning_event_count
    if warnings < 2 or selection.non_running_pod_count * 2 >= warnings:
        return None
    candidate = max(current_threshold + 2, warnings + 1)
    if candidate <= current_threshold:
        candidate = current_threshold + 1
    return HealthProposal(
        proposal_id=f"{run_id}-warning-threshold",
        source_run_id=source_run_id,
        source_artifact_path=review_path,
        target="health.trigger_policy.warning_event_threshold",
        proposed_change=f"Raise warning_event_threshold from {current_threshold} to {candidate}.",
        rationale=(
            f"{warnings} warnings triggered while only {selection.non_running_pod_count} pods were non-running, suggesting noise."
        ),
        confidence=ConfidenceLevel.MEDIUM,
        expected_benefit="Suppress repeating warnings that do not lead to failures.",
        rollback_note=f"Revert threshold to {current_threshold} if true failures begin to appear.",
    )


def _choose_noise_reason(selection: DrilldownSelection) -> Optional[str]:
    for reason in selection.reasons:
        lowered = reason.lower()
        if lowered == "warning_event_threshold" or lowered == "health_regression" or not reason:
            continue
        return reason
    return None


def _noise_reason_proposal(
    run_id: str,
    review_path: str,
    selection: DrilldownSelection,
    reason: str,
    source_run_id: str,
) -> HealthProposal:
    return HealthProposal(
        proposal_id=f"{run_id}-ignore-{_slugify(reason)}",
        source_run_id=source_run_id,
        source_artifact_path=review_path,
        target="health.noise_filters.ignored_reasons",
        proposed_change=f"Add warning reason '{reason}' to the noise_filters ignore list.",
        rationale=(
            f"{selection.warning_event_count} '{reason}' warnings fired without corresponding pod issues, suggesting a noisy pattern."
        ),
        confidence=ConfidenceLevel.LOW,
        expected_benefit="Focus alerts on signals that correlate with failures.",
        rollback_note="Remove the reason from the ignore list if it later leads to real incidents.",
    )


def _baseline_release_proposals(
    run_id: str,
    review_path: str,
    source_run_id: str,
    baseline_policy: BaselinePolicy,
    details: Sequence[Mapping[str, Any]],
) -> List[HealthProposal]:
    proposals: List[HealthProposal] = []
    seen = set()
    for detail in details:
        reason = str(detail.get("reason") or "")
        release_key = _parse_release_key(reason)
        if not release_key or release_key in seen:
            continue
        seen.add(release_key)
        actual_value = str(detail.get("actual_value") or "")
        versions = _split_pair(actual_value)
        policy = baseline_policy.release_policy(release_key)
        if policy:
            normalized_allowed = {_normalize_version(item) for item in policy.allowed_versions}
            missing = [version for version in versions if _normalize_version(version) not in normalized_allowed]
            if not missing:
                continue
            allowed = ", ".join(dict.fromkeys((*policy.allowed_versions, *missing)))
            change = f"Allow {release_key} versions {allowed}."
        else:
            sample = versions[0] if versions else "latest"
            change = f"Start tracking Helm release {release_key} and allow version {sample}."
        proposals.append(
            HealthProposal(
                proposal_id=f"{run_id}-release-{_slugify(release_key)}",
                source_run_id=source_run_id,
                source_artifact_path=review_path,
                target="health.baseline_policy.watched_releases",
                proposed_change=change,
                rationale=(
                    f"Trigger detail '{reason}' indicates release drift and baseline expectations are outdated."
                ),
                confidence=ConfidenceLevel.MEDIUM,
                expected_benefit="Prevent repeated baseline drift alerts for this release.",
                rollback_note="Revert the baseline entry if this version causes instability.",
            )
        )
    return proposals


def _baseline_crd_proposals(
    run_id: str,
    review_path: str,
    source_run_id: str,
    baseline_policy: BaselinePolicy,
    details: Sequence[Mapping[str, Any]],
) -> List[HealthProposal]:
    proposals: List[HealthProposal] = []
    seen = set()
    for detail in details:
        reason = str(detail.get("reason") or "")
        family = _parse_crd_family(reason)
        if not family or family in seen:
            continue
        seen.add(family)
        policy = baseline_policy.crd_policy(family)
        if policy:
            change = f"Refresh CRD family {family} expectations; drift reported as '{reason}'."
        else:
            change = f"Add CRD family {family} to the baseline requirements."
        proposals.append(
            HealthProposal(
                proposal_id=f"{run_id}-crd-{_slugify(family)}",
                source_run_id=source_run_id,
                source_artifact_path=review_path,
                target="health.baseline_policy.required_crd_families",
                proposed_change=change,
                rationale="The health baseline reported storage drift for this CRD family.",
                confidence=ConfidenceLevel.MEDIUM,
                expected_benefit="Avoid spurious baseline violations when CRD storage versions vary.",
                rollback_note="Remove or adjust the CRD expectation if it causes false positives.",
            )
        )
    return proposals


def _drilldown_ranking_proposal(
    run_id: str,
    review_path: str,
    source_run_id: str,
    metric: Optional[QualityMetric],
) -> Optional[HealthProposal]:
    if not metric:
        return None
    if metric.level != "low" and metric.score >= 40:
        return None
    return HealthProposal(
        proposal_id=f"{run_id}-drilldown-order",
        source_run_id=source_run_id,
        source_artifact_path=review_path,
        target="health.drilldown.review_order",
        proposed_change="Adjust drilldown ranking to emphasize more contexts when the top selection has low severity.",
        rationale="The drilldown prioritization metric scored low, so operators may not see higher-severity alternatives quickly.",
        confidence=ConfidenceLevel.LOW,
        expected_benefit="Operators can access the next-best drilldowns without manual searching.",
        rollback_note="Revert ranking tweaks if the ordering becomes noisy.",
    )


def _slugify(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower() or "proposal"


def evaluate_proposal(proposal: HealthProposal, fixture_path: Path) -> ProposalEvaluation:
    fixture = _load_fixture_snapshot(fixture_path)
    warning_events = fixture.get("warning_events", [])
    warnings = sum(int(entry.get("count", 1)) for entry in warning_events)
    pods = int(fixture.get("non_running", 0))
    noise = _describe_noise_reduction(proposal, warnings)
    signal = _describe_signal_loss(proposal, pods)
    test_note = f"Fixture {fixture_path.name}: {warnings} warnings, {pods} non-running pods."
    return ProposalEvaluation(
        proposal_id=proposal.proposal_id,
        noise_reduction=noise,
        signal_loss=signal,
        test_outcome=test_note,
    )


def _load_fixture_snapshot(path: Path) -> Dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(raw, dict) and "cluster_snapshots" in raw:
        snapshots = raw.get("cluster_snapshots") or []
        if snapshots:
            return _extract_signals_from_snapshot(snapshots[0])
    return _extract_signals_from_snapshot(raw)


def _extract_signals_from_snapshot(snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    health = snapshot.get("health_signals") or {}
    pod_counts = health.get("pod_counts") or {}
    return {
        "warning_events": health.get("warning_events") or [],
        "non_running": pod_counts.get("non_running", 0),
    }


def _describe_noise_reduction(proposal: HealthProposal, warnings: int) -> str:
    if proposal.target == "health.trigger_policy.warning_event_threshold":
        reduction = min(100, warnings * 10)
        return f"Likely ~{reduction}% noise reduction by filtering recurring warnings."
    if proposal.target == "health.noise_filters.ignored_reasons":
        return "Suppresses repeated reasons that rarely correlate with failures."
    return "Not noise-focused; noise reduction not estimated."


def _describe_signal_loss(proposal: HealthProposal, pods: int) -> str:
    if proposal.target.startswith("health.trigger_policy") or proposal.target == "health.noise_filters.ignored_reasons":
        level = "low" if pods == 0 else "medium"
        return f"Possible signal loss: {level} (non-running pods observed: {pods})."
    return "Signal loss unlikely; proposal only adjusts baseline expectations."
