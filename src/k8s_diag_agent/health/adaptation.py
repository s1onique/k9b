"""Deterministic adaptation helpers for health review proposals."""
from __future__ import annotations

import difflib
import json
import re
from collections import OrderedDict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any

from ..models import ConfidenceLevel
from .baseline import (
    DEFAULT_CRD_NEXT_CHECK,
    DEFAULT_RELEASE_NEXT_CHECK,
    BaselineDriftCategory,
    BaselinePolicy,
    resolve_baseline_policy_path,
)
from .review_feedback import DrilldownSelection, HealthReviewArtifact, QualityMetric

_RELEASE_DRIFT_RE = re.compile(r"watched Helm release (?P<release>[^\s]+) drift", re.IGNORECASE)
_CRD_DRIFT_RE = re.compile(r"watched CRD (?P<family>[^\s]+) storage drift", re.IGNORECASE)


class ProposalLifecycleStatus(StrEnum):
    PENDING = "pending"
    CHECKED = "checked"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    APPLIED = "applied"
    PROPOSED = "proposed"
    REPLAYED = "replayed"
    PROMOTED = "promoted"


@dataclass(frozen=True)
class ProposalLifecycleEntry:
    status: ProposalLifecycleStatus
    timestamp: str
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "status": self.status.value,
            "timestamp": self.timestamp,
        }
        if self.note:
            data["note"] = self.note
        return data


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _freeze_payload(value: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    base = dict(value or {})
    return MappingProxyType(base)


def _empty_payload() -> Mapping[str, Any]:
    return MappingProxyType({})


def _default_lifecycle_history() -> tuple[ProposalLifecycleEntry, ...]:
    return (ProposalLifecycleEntry(status=ProposalLifecycleStatus.PENDING, timestamp=_now_iso()),)


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
    promotion_payload: Mapping[str, Any] = field(default_factory=_empty_payload)
    lifecycle_history: tuple[ProposalLifecycleEntry, ...] = field(default_factory=_default_lifecycle_history)
    promotion_evaluation: ProposalEvaluation | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "promotion_payload", _freeze_payload(self.promotion_payload))
        history = tuple(self.lifecycle_history) if self.lifecycle_history else _default_lifecycle_history()
        if not history:
            history = _default_lifecycle_history()
        object.__setattr__(self, "lifecycle_history", history)

    def to_dict(self) -> dict[str, Any]:
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
            "promotion_payload": dict(self.promotion_payload),
            "lifecycle_history": [entry.to_dict() for entry in self.lifecycle_history],
            "promotion_evaluation": self.promotion_evaluation.to_dict() if self.promotion_evaluation else None,
        }

    def __hash__(self) -> int:
        return hash((self.proposal_id, self.source_run_id, self.target, self.proposed_change))

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> HealthProposal:
        if not isinstance(raw, Mapping):
            raise ValueError("Proposal must be a mapping")
        confidence_value = raw.get("confidence")
        if not confidence_value:
            raise ValueError("Proposal missing confidence level")
        try:
            confidence = ConfidenceLevel(str(confidence_value))
        except ValueError as exc:
            raise ValueError(f"Invalid confidence value: {confidence_value}") from exc
        payload_raw = raw.get("promotion_payload") or {}
        payload = _freeze_payload(payload_raw if isinstance(payload_raw, Mapping) else {})
        history_entries: list[ProposalLifecycleEntry] = []
        history_raw = raw.get("lifecycle_history")
        if isinstance(history_raw, Sequence):
            for entry_raw in history_raw:
                if not isinstance(entry_raw, Mapping):
                    continue
                status_value = entry_raw.get("status")
                timestamp_value = entry_raw.get("timestamp")
                note_value = entry_raw.get("note")
                timestamp = str(timestamp_value) if timestamp_value else _now_iso()
                try:
                    status = ProposalLifecycleStatus(str(status_value)) if status_value else ProposalLifecycleStatus.PENDING
                except ValueError:
                    status = ProposalLifecycleStatus.PENDING
                history_entries.append(
                    ProposalLifecycleEntry(status=status, timestamp=timestamp, note=str(note_value) if note_value else None)
                )
        history = tuple(history_entries) if history_entries else _default_lifecycle_history()
        evaluation_raw = raw.get("promotion_evaluation")
        evaluation: ProposalEvaluation | None = None
        if isinstance(evaluation_raw, Mapping):
            try:
                evaluation = ProposalEvaluation.from_dict(evaluation_raw)
            except ValueError:
                evaluation = None
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
            promotion_payload=payload,
            lifecycle_history=history,
            promotion_evaluation=evaluation,
        )


@dataclass(frozen=True)
class ProposalEvaluation:
    proposal_id: str
    noise_reduction: str
    signal_loss: str
    test_outcome: str

    def to_dict(self) -> dict[str, str]:
        return {
            "proposal_id": self.proposal_id,
            "noise_reduction": self.noise_reduction,
            "signal_loss": self.signal_loss,
            "test_outcome": self.test_outcome,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> ProposalEvaluation:
        if not isinstance(raw, Mapping):
            raise ValueError("promotion_evaluation must be a mapping")
        return cls(
            proposal_id=str(raw.get("proposal_id") or ""),
            noise_reduction=str(raw.get("noise_reduction") or ""),
            signal_loss=str(raw.get("signal_loss") or ""),
            test_outcome=str(raw.get("test_outcome") or ""),
        )


def _metric(review: HealthReviewArtifact, dimension: str) -> QualityMetric | None:
    for metric in review.quality_summary:
        if metric.dimension == dimension:
            return metric
    return None


def collect_trigger_details(triggers_dir: Path, run_id: str) -> tuple[Mapping[str, Any], ...]:
    if not triggers_dir.exists():
        return ()
    details: list[Mapping[str, Any]] = []
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


def _dedupe_by_key(items: Iterable[tuple[str, Mapping[str, Any]]]) -> list[tuple[str, Mapping[str, Any]]]:
    seen: set[str] = set()
    unique: list[tuple[str, Mapping[str, Any]]] = []
    for key, item in items:
        if key in seen:
            continue
        seen.add(key)
        unique.append((key, item))
    return unique


def _parse_release_key(reason: str) -> str | None:
    match = _RELEASE_DRIFT_RE.search(reason)
    if not match:
        return None
    return match.group("release")


def _parse_crd_family(reason: str) -> str | None:
    match = _CRD_DRIFT_RE.search(reason)
    if not match:
        return None
    return match.group("family")


def _split_pair(value: str) -> tuple[str, ...]:
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
) -> tuple[HealthProposal, ...]:
    selection = review.selected_drilldowns[0] if review.selected_drilldowns else None
    base_path = str(review_path)
    proposals: list[HealthProposal] = []
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
) -> HealthProposal | None:
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
        promotion_payload={"threshold": candidate},
    )


def _choose_noise_reason(selection: DrilldownSelection) -> str | None:
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
        promotion_payload={"reason": reason},
    )


def _has_baseline_mismatch(details: Sequence[Mapping[str, Any]]) -> bool:
    for detail in details:
        if isinstance(detail, Mapping) and detail.get("type") == "baseline_mismatch":
            return True
    return False


def _baseline_release_proposals(
    run_id: str,
    review_path: str,
    source_run_id: str,
    baseline_policy: BaselinePolicy,
    details: Sequence[Mapping[str, Any]],
) -> list[HealthProposal]:
    proposals: list[HealthProposal] = []
    if _has_baseline_mismatch(details):
        return proposals
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
            versions_to_add = missing
        else:
            sample = versions[0] if versions else "latest"
            change = f"Start tracking Helm release {release_key} and allow version {sample}."
            versions_to_add = [sample]
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
                promotion_payload={
                    "release_key": release_key,
                    "versions": versions_to_add,
                },
            )
        )
    return proposals


def _baseline_crd_proposals(
    run_id: str,
    review_path: str,
    source_run_id: str,
    baseline_policy: BaselinePolicy,
    details: Sequence[Mapping[str, Any]],
) -> list[HealthProposal]:
    proposals: list[HealthProposal] = []
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
                promotion_payload={"family": family, "reason": reason},
            )
        )
    return proposals


def _drilldown_ranking_proposal(
    run_id: str,
    review_path: str,
    source_run_id: str,
    metric: QualityMetric | None,
) -> HealthProposal | None:
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


def _load_fixture_snapshot(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(raw, dict) and "cluster_snapshots" in raw:
        snapshots = raw.get("cluster_snapshots") or []
        if snapshots:
            return _extract_signals_from_snapshot(snapshots[0])
    return _extract_signals_from_snapshot(raw)


def _extract_signals_from_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
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


def with_lifecycle_status(
    proposal: HealthProposal,
    status: ProposalLifecycleStatus,
    note: str | None = None,
) -> HealthProposal:
    history = proposal.lifecycle_history
    if history and history[-1].status == status:
        return proposal
    entry = ProposalLifecycleEntry(status=status, timestamp=_now_iso(), note=note)
    return replace(proposal, lifecycle_history=history + (entry,))


class PromotionError(Exception):
    pass


class UnsupportedProposalTarget(PromotionError):
    pass


class PromotionNotApplicable(PromotionError):
    pass


_HEALTH_CONFIG_TARGETS = {
    "health.trigger_policy.warning_event_threshold",
    "health.noise_filters.ignored_reasons",
}

_BASELINE_TARGETS = {
    "health.baseline_policy.watched_releases",
    "health.baseline_policy.required_crd_families",
    "health.baseline_policy.ignored_drift",
}


def render_proposal_patch(
    proposal: HealthProposal,
    health_config_path: Path,
    output_dir: Path,
    baseline_path: Path | None = None,
) -> Path:
    target = proposal.target
    if target in _HEALTH_CONFIG_TARGETS:
        target_path = health_config_path
    elif target in _BASELINE_TARGETS:
        target_path = baseline_path or _resolve_baseline_path(health_config_path)
    else:
        raise UnsupportedProposalTarget(f"Unsupported proposal target: {target}")
    original_text = target_path.read_text(encoding="utf-8")
    data = _load_ordered_json(target_path)
    if target == "health.trigger_policy.warning_event_threshold":
        _apply_threshold_update(data, proposal.promotion_payload)
    elif target == "health.noise_filters.ignored_reasons":
        _apply_noise_update(data, proposal.promotion_payload)
    elif target == "health.baseline_policy.watched_releases":
        _apply_release_update(data, proposal.promotion_payload)
    elif target == "health.baseline_policy.required_crd_families":
        _apply_crd_update(data, proposal.promotion_payload)
    elif target == "health.baseline_policy.ignored_drift":
        _apply_ignored_drift_update(data, proposal.promotion_payload)
    else:
        raise UnsupportedProposalTarget(f"Unsupported proposal target: {target}")
    updated_text = _dump_json(data)
    return _write_patch(target_path, original_text, updated_text, output_dir, proposal.proposal_id)


def _load_ordered_json(path: Path) -> OrderedDict[str, Any]:
    raw_text = path.read_text(encoding="utf-8")
    parsed = json.loads(raw_text, object_pairs_hook=OrderedDict)
    if isinstance(parsed, Mapping):
        return OrderedDict(parsed)
    return OrderedDict()


def _dump_json(data: Mapping[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _apply_threshold_update(data: OrderedDict[str, Any], payload: Mapping[str, Any]) -> None:
    triggers = data.setdefault("comparison_triggers", OrderedDict())
    threshold_value = payload.get("threshold")
    if threshold_value is None:
        raise PromotionError("Promotion payload missing threshold value")
    try:
        triggers["warning_event_threshold"] = int(threshold_value)
    except (TypeError, ValueError) as exc:
        raise PromotionError(f"Invalid threshold value: {threshold_value}") from exc


def _apply_noise_update(data: OrderedDict[str, Any], payload: Mapping[str, Any]) -> None:
    reason = payload.get("reason")
    if not reason:
        raise PromotionError("Promotion payload missing noise reason")
    noise_filters = data.setdefault("noise_filters", OrderedDict())
    ignored = noise_filters.setdefault("ignored_reasons", [])
    if not isinstance(ignored, list):
        ignored = list(ignored)
        noise_filters["ignored_reasons"] = ignored
    if reason not in ignored:
        ignored.append(str(reason))


def _apply_release_update(data: OrderedDict[str, Any], payload: Mapping[str, Any]) -> None:
    release_key = payload.get("release_key")
    versions = payload.get("versions")
    if not release_key or not versions:
        raise PromotionError("Promotion payload missing release key or versions")
    releases = data.setdefault("watched_releases", [])
    target_entry: OrderedDict[str, Any] | None = None
    for entry in releases:
        if isinstance(entry, Mapping) and str(entry.get("release")) == release_key:
            target_entry = OrderedDict(entry)
            index = releases.index(entry)
            releases[index] = target_entry
            break
    if target_entry is None:
        target_entry = OrderedDict(
            [
                ("release", release_key),
                ("allowed_versions", []),
                ("why", "Platform stability depends on curated Helm releases."),
                ("next_check", DEFAULT_RELEASE_NEXT_CHECK),
            ]
        )
        releases.append(target_entry)
    allowed = target_entry.setdefault("allowed_versions", [])
    if not isinstance(allowed, list):
        allowed = list(allowed)
        target_entry["allowed_versions"] = allowed
    seen: set[str] = { _normalize_version(str(entry)) for entry in allowed if entry }
    for version in versions:
        normalized = _normalize_version(str(version))
        if not normalized or normalized in seen:
            continue
        allowed.append(str(version))
        seen.add(normalized)


def _apply_crd_update(data: OrderedDict[str, Any], payload: Mapping[str, Any]) -> None:
    family = payload.get("family")
    if not family:
        raise PromotionError("Promotion payload missing CRD family")
    crds = data.setdefault("required_crd_families", [])
    for entry in crds:
        if isinstance(entry, Mapping) and str(entry.get("family")) == family:
            return
    crds.append(
        OrderedDict(
            [
                ("family", family),
                ("why", "Workload delivery requires this CRD family."),
                ("next_check", DEFAULT_CRD_NEXT_CHECK),
            ]
        )
    )


def _apply_ignored_drift_update(data: OrderedDict[str, Any], payload: Mapping[str, Any]) -> None:
    category = payload.get("category")
    if not category:
        raise PromotionError("Promotion payload missing drift category")
    valid_categories = {item.value for item in BaselineDriftCategory}
    if str(category) not in valid_categories:
        raise PromotionError(f"Unknown drift category: {category}")
    ignored = data.setdefault("ignored_drift", [])
    if not isinstance(ignored, list):
        ignored = list(ignored)
        data["ignored_drift"] = ignored
    if category not in ignored:
        ignored.append(category)


def _resolve_baseline_path(config_path: Path) -> Path:
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    baseline_raw = raw.get("baseline_policy_path") if isinstance(raw, Mapping) else None
    explicit = str(baseline_raw) if baseline_raw else None
    try:
        return resolve_baseline_policy_path(config_path.parent, explicit)
    except FileNotFoundError as exc:
        raise PromotionError(str(exc)) from exc


def _write_patch(
    target_path: Path,
    original_text: str,
    updated_text: str,
    output_dir: Path,
    proposal_id: str,
) -> Path:
    if original_text == updated_text:
        raise PromotionNotApplicable("No changes would result from this promotion")
    original_lines = original_text.splitlines()
    updated_lines = updated_text.splitlines()
    diff_lines = list(
        difflib.unified_diff(
            original_lines,
            updated_lines,
            fromfile=str(target_path),
            tofile=str(target_path),
            lineterm="",
        )
    )
    if not diff_lines:
        raise PromotionNotApplicable("No differences found after promotion")
    patch_content = "\n".join(diff_lines) + "\n"
    output_dir.mkdir(parents=True, exist_ok=True)
    patch_file = output_dir / f"{proposal_id}.patch"
    patch_file.write_text(patch_content, encoding="utf-8")
    return patch_file
