"""Helpers for building a human-friendly intent summary of health work."""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..security import sanitize_payload
from .adaptation import HealthProposal, ProposalLifecycleStatus
from .proposal_lifecycle_events import derive_current_proposal_status
from .summary_clusters import (
    _discover_latest_run_id,
    _load_history,
    build_cluster_summaries,
)
from .summary_clusters import (
    _load_json as _load_json_impl,
)
from .summary_proposals import collect_proposals_for_run, load_all_proposals
from .summary_triggers import collect_comparison_summaries, collect_triggers

logger = logging.getLogger(__name__)

_TRANSITIONS_SUBDIR = "transitions"
_ASSESSMENT_PATTERN = re.compile(r"(?P<run_id>.+-\d{8}T\d{6}Z)-(?P<label>.+)-assessment\.json$")
_TIMESTAMP_LENGTH = 16  # YYYYMMDDTHHMMSSZ


@dataclass(frozen=True)
class ClusterSummary:
    label: str
    top_finding: str | None
    findings_count: int
    health_rating: str | None
    warning_count: int | None
    non_running_pods: int | None
    missing_evidence: tuple[str, ...] | None
    cluster_class: str | None
    cluster_role: str | None
    baseline_cohort: str | None
    baseline_policy_path: str | None


@dataclass(frozen=True)
class ProposalSummary:
    proposal_id: str
    target: str
    rationale: str
    confidence: str
    source_run_id: str
    lifecycle_status: str


@dataclass(frozen=True)
class TopSelection:
    label: str
    warning_event_count: int
    non_running_pod_count: int


@dataclass(frozen=True)
class TriggerSummary:
    primary: str
    secondary: str
    primary_label: str
    secondary_label: str
    reasons: tuple[str, ...]
    notes: str | None
    comparison_intent: str | None = None
    peer_notes: str | None = None


@dataclass(frozen=True)
class ComparisonSummary:
    primary_label: str
    secondary_label: str
    policy_eligible: bool
    triggered: bool
    comparison_intent: str
    reason: str
    primary_class: str | None
    secondary_class: str | None
    primary_role: str | None
    secondary_role: str | None
    primary_cohort: str | None
    secondary_cohort: str | None
    expected_drift_categories: tuple[str, ...]
    ignored_drift_categories: tuple[str, ...]
    notes: str | None


@dataclass(frozen=True)
class PromotedComparison:
    proposal_id: str
    context: str | None
    noise_before: int
    noise_after: int
    quality_before: int | None
    quality_after: int | None
    non_running_before: int
    non_running_after: int
    signal_note: str


@dataclass(frozen=True)
class HealthSummary:
    run_id: str
    run_timestamp: datetime | None
    clusters: tuple[ClusterSummary, ...]
    proposals: tuple[ProposalSummary, ...]
    promoted: tuple[PromotedComparison, ...]
    triggers: tuple[TriggerSummary, ...]
    comparisons: tuple[ComparisonSummary, ...]


def _sanitize_text(value: str | None) -> str | None:
    sanitized = sanitize_payload(value)
    if isinstance(sanitized, str):
        return sanitized
    if sanitized is None:
        return None
    return str(sanitized)


def gather_health_summary(runs_dir: Path, *, run_id: str | None = None) -> HealthSummary:
    assessments_dir = runs_dir / "assessments"
    history_path = runs_dir / "history.json"
    proposals_dir = runs_dir / "proposals"
    triggers_dir = runs_dir / "triggers"
    reviews_dir = runs_dir / "reviews"

    run_id = run_id or _discover_latest_run_id(assessments_dir)
    if not run_id:
        raise RuntimeError("Unable to discover any health runs.")
    run_timestamp = _parse_run_timestamp(run_id)

    history = _load_history(history_path)
    cluster_summaries = _build_cluster_summaries(assessments_dir, run_id, history)
    all_proposals = load_all_proposals(proposals_dir)
    transitions_dir = proposals_dir / _TRANSITIONS_SUBDIR
    proposal_list = _collect_proposals_for_run(all_proposals, transitions_dir, run_id)
    trigger_artifacts = _collect_triggers_data(triggers_dir, run_id)
    promoted = _collect_promoted_reports(all_proposals, transitions_dir, reviews_dir, run_id)
    comparison_list = _collect_comparison_summaries(runs_dir, run_id)

    return HealthSummary(
        run_id=run_id,
        run_timestamp=run_timestamp,
        clusters=tuple(sorted(cluster_summaries, key=lambda entry: entry.label)),
        proposals=tuple(proposal_list),
        promoted=tuple(promoted),
        triggers=tuple(trigger_artifacts),
        comparisons=tuple(comparison_list),
    )


def _load_json(path: Path) -> dict[str, Any]:
    """Load JSON file with logging on the summary module logger.

    This wrapper ensures logging happens on k8s_diag_agent.health.summary
    for backward compatibility with tests.
    """
    try:
        return _load_json_impl(path)
    except (OSError, json.JSONDecodeError):
        logger.warning("Skipped malformed assessment artifact: %s", path.name, exc_info=True)
        return {}


def _collect_comparison_summaries(root: Path, run_id: str) -> list[ComparisonSummary]:
    """Convert comparison dicts to ComparisonSummary dataclass objects."""
    try:
        comp_dicts = collect_comparison_summaries(root, run_id)
    except (OSError, json.JSONDecodeError):
        logger.warning("Skipped malformed comparison-decisions artifact: %s", f"{run_id}-comparison-decisions.json", exc_info=True)
        return []
    return [
        ComparisonSummary(
            primary_label=d["primary_label"],
            secondary_label=d["secondary_label"],
            policy_eligible=d["policy_eligible"],
            triggered=d["triggered"],
            comparison_intent=d["comparison_intent"],
            reason=d["reason"],
            primary_class=d["primary_class"],
            secondary_class=d["secondary_class"],
            primary_role=d["primary_role"],
            secondary_role=d["secondary_role"],
            primary_cohort=d["primary_cohort"],
            secondary_cohort=d["secondary_cohort"],
            expected_drift_categories=d["expected_drift_categories"],
            ignored_drift_categories=d["ignored_drift_categories"],
            notes=d["notes"],
        )
        for d in comp_dicts
    ]


def _collect_triggers_data(triggers_dir: Path, run_id: str) -> list[TriggerSummary]:
    """Convert trigger dicts to TriggerSummary dataclass objects."""
    return [TriggerSummary(**d) for d in collect_triggers(triggers_dir, run_id)]


def _collect_proposals_for_run(
    proposals: Iterable[HealthProposal], transitions_dir: Path | None, run_id: str
) -> list[ProposalSummary]:
    """Convert proposal dicts to ProposalSummary dataclass objects."""
    return [ProposalSummary(**d) for d in collect_proposals_for_run(proposals, transitions_dir, run_id)]


def format_health_summary(summary: HealthSummary) -> str:
    lines: list[str] = []
    timestamp = summary.run_timestamp.isoformat() if summary.run_timestamp else "unknown"
    lines.append(f"Health run {summary.run_id} @ {timestamp}")
    lines.append("Status per cluster:")
    if summary.clusters:
        for entry in summary.clusters:
            warnings = entry.warning_count if entry.warning_count is not None else "n/a"
            pods = entry.non_running_pods if entry.non_running_pods is not None else "n/a"
            rating = _sanitize_text(entry.health_rating) or "unknown"
            metadata = _format_cluster_metadata(
                entry.cluster_class,
                entry.cluster_role,
                entry.baseline_cohort,
                entry.baseline_policy_path,
            )
            label = _sanitize_text(entry.label) or "unknown"
            lines.append(
                f"- {label}{metadata}: {rating} (non-running pods: {pods}, warnings: {warnings})"
            )
    else:
        lines.append("- none")

    lines.append("Top findings:")
    if summary.clusters:
        for entry in summary.clusters:
            finding = _sanitize_text(entry.top_finding) or "none"
            label = _sanitize_text(entry.label) or "unknown"
            lines.append(f"- {label}: {finding}")
    else:
        lines.append("- none")

    lines.append("Proposals generated:")
    if summary.proposals:
        for proposal in summary.proposals:
            proposal_id = _sanitize_text(proposal.proposal_id) or proposal.proposal_id
            confidence = _sanitize_text(proposal.confidence) or proposal.confidence
            target = _sanitize_text(proposal.target) or proposal.target
            rationale = _sanitize_text(proposal.rationale) or proposal.rationale
            lines.append(
                f"- {proposal_id} [{confidence}] target {target}: {rationale}"
            )
    else:
        lines.append("- none")

    lines.append("Promoted proposals applied:")
    if summary.promoted:
        for report in summary.promoted:
            proposal_id = _sanitize_text(report.proposal_id) or report.proposal_id
            context = _sanitize_text(report.context) or "unknown"
            signal_note = _sanitize_text(report.signal_note) or report.signal_note
            lines.append(
                f"- {proposal_id} ({context}): noise {report.noise_before}->{report.noise_after},"
                f" quality {report.quality_before or 'n/a'}->{report.quality_after or 'n/a'}, {signal_note}"
            )
    else:
        lines.append("- none")

    lines.append("Comparisons triggered:")
    if summary.triggers:
        for trigger in summary.triggers:
            sanitized_reasons = [
                _sanitize_text(reason) or reason for reason in trigger.reasons if reason
            ]
            reason_text = ", ".join(sanitized_reasons) or "unspecified"
            notes_value = _sanitize_text(trigger.notes)
            notes = f" ({notes_value})" if notes_value else ""
            classification_value = _sanitize_text(trigger.comparison_intent)
            classification = (
                f", classification {classification_value}"
                if classification_value
                else ""
            )
            peer_note_value = _sanitize_text(trigger.peer_notes)
            peer_note = f", peer notes {peer_note_value}" if peer_note_value else ""
            primary_label = _sanitize_text(trigger.primary_label) or "unknown"
            secondary_label = _sanitize_text(trigger.secondary_label) or "unknown"
            lines.append(
                f"- {primary_label} vs {secondary_label}: {reason_text}{classification}{notes}{peer_note}"
            )
    else:
        lines.append("- none")

    lines.append("Comparison policy decisions:")
    if summary.comparisons:
        for comp in summary.comparisons:
            eligibility = "eligible" if comp.policy_eligible else "skipped"
            triggered_text = "triggered" if comp.triggered else "not triggered"
            primary_meta = _format_cluster_metadata(
                comp.primary_class, comp.primary_role, comp.primary_cohort
            )
            secondary_meta = _format_cluster_metadata(
                comp.secondary_class, comp.secondary_role, comp.secondary_cohort
            )
            primary_label = _sanitize_text(comp.primary_label) or "unknown"
            secondary_label = _sanitize_text(comp.secondary_label) or "unknown"
            comparison_intent = _sanitize_text(comp.comparison_intent) or comp.comparison_intent
            reason = _sanitize_text(comp.reason) or comp.reason
            expected_text = _describe_categories(comp.expected_drift_categories)
            ignored_text = _describe_categories(comp.ignored_drift_categories)
            notes_value = _sanitize_text(comp.notes)
            notes = f", notes {notes_value}" if notes_value else ""
            lines.append(
                f"- {primary_label}{primary_meta} vs {secondary_label}{secondary_meta}: "
                f"{eligibility}, {triggered_text}, classification {comparison_intent}, "
                f"expected drift {expected_text}, ignored drift {ignored_text}, reason {reason}{notes}"
            )
    else:
        lines.append("- none")

    return "\n".join(lines)


def _parse_run_timestamp(run_id: str) -> datetime | None:
    if len(run_id) < _TIMESTAMP_LENGTH:
        return None
    timestamp = run_id[-_TIMESTAMP_LENGTH:]
    try:
        return datetime.strptime(timestamp, "%Y%m%dT%H%M%SZ")
    except ValueError:
        return None


# Re-export _build_cluster_summaries for backward compatibility with tests.
# Delegates to summary_clusters.build_cluster_summaries.
def _build_cluster_summaries(
    assessments_dir: Path, run_id: str, history: Mapping[str, Any]
) -> list[ClusterSummary]:
    """Build ClusterSummary objects for the health summary.

    Backward-compatibility wrapper around summary_clusters.build_cluster_summaries.
    """
    cluster_dicts = build_cluster_summaries(assessments_dir, run_id, history)
    return [
        ClusterSummary(
            label=d["label"],
            top_finding=d["top_finding"],
            findings_count=d["findings_count"],
            health_rating=d["health_rating"],
            warning_count=d["warning_count"],
            non_running_pods=d["non_running_pods"],
            missing_evidence=d["missing_evidence"],
            cluster_class=d["cluster_class"],
            cluster_role=d["cluster_role"],
            baseline_cohort=d["baseline_cohort"],
            baseline_policy_path=d["baseline_policy_path"],
        )
        for d in cluster_dicts
    ]


def _format_cluster_metadata(
    cluster_class: str | None,
    cluster_role: str | None,
    baseline_cohort: str | None,
    baseline_policy_path: str | None = None,
) -> str:
    class_role_parts: list[str] = []
    sanitized_class = _sanitize_text(cluster_class)
    sanitized_role = _sanitize_text(cluster_role)
    if sanitized_class:
        class_role_parts.append(sanitized_class)
    if sanitized_role:
        class_role_parts.append(sanitized_role)
    parts: list[str] = []
    if class_role_parts:
        parts.append("/".join(class_role_parts))
    sanitized_cohort = _sanitize_text(baseline_cohort)
    if sanitized_cohort:
        parts.append(f"cohort {sanitized_cohort}")
    if baseline_policy_path:
        path_label = _sanitize_text(Path(baseline_policy_path).name) or Path(baseline_policy_path).name
        parts.append(f"policy {path_label}")
    if not parts:
        return ""
    return f" ({'; '.join(parts)})"


def _describe_categories(categories: tuple[str, ...]) -> str:
    if not categories:
        return "none"
    parts: list[str] = []
    for category in categories:
        sanitized = _sanitize_text(category)
        if sanitized:
            parts.append(sanitized)
        else:
            parts.append(category)
    return ", ".join(parts)


def _collect_promoted_reports(
    proposals: Iterable[HealthProposal], transitions_dir: Path | None, reviews_dir: Path, after_run_id: str
) -> list[PromotedComparison]:
    promoted: list[PromotedComparison] = []
    for proposal in proposals:
        # Use event-aware derivation for promoted/accepted state
        current_status = derive_current_proposal_status(proposal.to_dict(), transitions_dir)
        if current_status not in {
            ProposalLifecycleStatus.ACCEPTED,
            ProposalLifecycleStatus.PROMOTED,
            ProposalLifecycleStatus.APPLIED,
        }:
            continue
        before_review = _load_review(proposal.source_run_id, reviews_dir)
        after_review = _load_review(after_run_id, reviews_dir)
        if not before_review or not after_review:
            continue
        before_selection = _extract_top_selection(before_review)
        after_selection = _extract_top_selection(after_review)
        if not before_selection or not after_selection:
            continue
        noise_before = before_selection.warning_event_count
        noise_after = after_selection.warning_event_count
        non_running_before = before_selection.non_running_pod_count
        non_running_after = after_selection.non_running_pod_count
        quality_before = _extract_quality_score(before_review, "signal_quality")
        quality_after = _extract_quality_score(after_review, "signal_quality")
        signal_note = _signal_note(non_running_before, non_running_after)
        promoted.append(
            PromotedComparison(
                proposal_id=proposal.proposal_id,
                context=before_selection.label,
                noise_before=noise_before,
                noise_after=noise_after,
                quality_before=quality_before,
                quality_after=quality_after,
                non_running_before=non_running_before,
                non_running_after=non_running_after,
                signal_note=signal_note,
            )
        )
    return promoted


def _load_review(run_id: str, reviews_dir: Path) -> Mapping[str, Any] | None:
    path = reviews_dir / f"{run_id}-review.json"
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(raw, Mapping):
        return raw
    return None


def _extract_top_selection(review: Mapping[str, Any]) -> TopSelection | None:
    selections = review.get("selected_drilldowns") or []
    if not isinstance(selections, (list, tuple)) or not selections:
        return None
    selection = selections[0]
    raw_label = selection.get("label") or selection.get("context") or ""
    label = str(raw_label)
    warning = int(selection.get("warning_event_count") or 0)
    pods = int(selection.get("non_running_pod_count") or 0)
    return TopSelection(label=label, warning_event_count=warning, non_running_pod_count=pods)


def _extract_quality_score(review: Mapping[str, Any], dimension: str) -> int | None:
    metrics = review.get("quality_summary") or []
    if not isinstance(metrics, (list, tuple)):
        return None
    for entry in metrics:
        if not isinstance(entry, Mapping):
            continue
        if entry.get("dimension") == dimension:
            score = entry.get("score")
            if isinstance(score, int):
                return score
            if isinstance(score, str) and score.isdigit():
                return int(score)
    return None


def _signal_note(before: int, after: int) -> str:
    if after < before:
        return f"signal loss risk (non-running pods {before} -> {after})"
    if after > before:
        return f"signals preserved or stronger (non-running pods {before} -> {after})"
    return f"signal presence unchanged (non-running pods {before})"
