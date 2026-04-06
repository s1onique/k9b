"""Helpers for building a human-friendly intent summary of health work."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from .adaptation import HealthProposal, ProposalLifecycleStatus
from .utils import normalize_ref

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
    missing_evidence: Tuple[str, ...] | None


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
    reasons: Tuple[str, ...]
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
    clusters: Tuple[ClusterSummary, ...]
    proposals: Tuple[ProposalSummary, ...]
    promoted: Tuple[PromotedComparison, ...]
    triggers: Tuple[TriggerSummary, ...]


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
    all_proposals = _load_all_proposals(proposals_dir)
    proposal_list = _collect_proposals_for_run(all_proposals, run_id)
    trigger_artifacts = _collect_triggers(triggers_dir, run_id)
    promoted = _collect_promoted_reports(all_proposals, reviews_dir, run_id)

    return HealthSummary(
        run_id=run_id,
        run_timestamp=run_timestamp,
        clusters=tuple(sorted(cluster_summaries, key=lambda entry: entry.label)),
        proposals=tuple(proposal_list),
        promoted=tuple(promoted),
        triggers=tuple(trigger_artifacts),
    )


def format_health_summary(summary: HealthSummary) -> str:
    lines: List[str] = []
    timestamp = summary.run_timestamp.isoformat() if summary.run_timestamp else "unknown"
    lines.append(f"Health run {summary.run_id} @ {timestamp}")
    lines.append("Status per cluster:")
    if summary.clusters:
        for entry in summary.clusters:
            warnings = entry.warning_count if entry.warning_count is not None else "n/a"
            pods = entry.non_running_pods if entry.non_running_pods is not None else "n/a"
            rating = entry.health_rating or "unknown"
            lines.append(
                f"- {entry.label}: {rating} (non-running pods: {pods}, warnings: {warnings})"
            )
    else:
        lines.append("- none")

    lines.append("Top findings:")
    if summary.clusters:
        for entry in summary.clusters:
            finding = entry.top_finding or "none"
            lines.append(f"- {entry.label}: {finding}")
    else:
        lines.append("- none")

    lines.append("Proposals generated:")
    if summary.proposals:
        for proposal in summary.proposals:
            lines.append(
                f"- {proposal.proposal_id} [{proposal.confidence}] target {proposal.target}: {proposal.rationale}"
            )
    else:
        lines.append("- none")

    lines.append("Promoted proposals applied:")
    if summary.promoted:
        for report in summary.promoted:
            lines.append(
                f"- {report.proposal_id} ({report.context or 'unknown'}): noise {report.noise_before}->{report.noise_after},"
                f" quality {report.quality_before or 'n/a'}->{report.quality_after or 'n/a'}, {report.signal_note}"
            )
    else:
        lines.append("- none")

    lines.append("Comparisons triggered:")
    if summary.triggers:
        for trigger in summary.triggers:
            reason_text = ", ".join(trigger.reasons) or "unspecified"
            notes = f" ({trigger.notes})" if trigger.notes else ""
            lines.append(
                f"- {trigger.primary_label} vs {trigger.secondary_label}: {reason_text}{notes}"
            )
    else:
        lines.append("- none")

    return "\n".join(lines)


def _discover_latest_run_id(assessments_dir: Path) -> str | None:
    if not assessments_dir.is_dir():
        return None
    candidates: Dict[str, datetime] = {}
    for path in assessments_dir.iterdir():
        if not path.is_file():
            continue
        parsed = _parse_assessment_filename(path.name)
        if not parsed:
            continue
        run_id, _ = parsed
        timestamp = _parse_run_timestamp(run_id)
        if not timestamp:
            continue
        candidates[run_id] = max(timestamp, candidates.get(run_id, timestamp))
    if not candidates:
        return None
    latest = max(candidates.items(), key=lambda item: item[1])
    return latest[0]


def _parse_assessment_filename(name: str) -> tuple[str, str] | None:
    match = _ASSESSMENT_PATTERN.match(name)
    if not match:
        return None
    return match.group("run_id"), match.group("label")


def _parse_run_timestamp(run_id: str) -> datetime | None:
    if len(run_id) < _TIMESTAMP_LENGTH:
        return None
    timestamp = run_id[-_TIMESTAMP_LENGTH :]
    try:
        return datetime.strptime(timestamp, "%Y%m%dT%H%M%SZ")
    except ValueError:
        return None


def _load_history(history_path: Path) -> Dict[str, Any]:
    if not history_path.exists():
        return {}
    try:
        raw = json.loads(history_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(raw, Mapping):
        return dict(raw)
    return {}


def _build_cluster_summaries(
    assessments_dir: Path, run_id: str, history: Mapping[str, Any]
) -> List[ClusterSummary]:
    summaries: List[ClusterSummary] = []
    if not assessments_dir.is_dir():
        return summaries
    for path in sorted(assessments_dir.glob(f"{run_id}-*-assessment.json")):
        label = _label_from_assessment_path(run_id, path)
        data = _load_json(path)
        findings = data.get("findings") if isinstance(data, Mapping) else []
        top_finding = None
        if isinstance(findings, Sequence) and findings:
            first = findings[0]
            if isinstance(first, Mapping):
                top_finding = first.get("description") or first.get("text")
            else:
                top_finding = str(first)
        summary_entry = ClusterSummary(
            label=label or "unknown",
            top_finding=top_finding,
            findings_count=len(findings) if isinstance(findings, Sequence) else 0,
            health_rating=_lookup_history_field(history, label, "health_rating"),
            warning_count=_history_int(history, label, "warning_event_count"),
            non_running_pods=_history_int(history, label, "pod_counts", "non_running"),
            missing_evidence=_history_list(history, label, "missing_evidence"),
        )
        summaries.append(summary_entry)
    return summaries


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(raw, Mapping):
        return raw
    return {}


def _label_from_assessment_path(run_id: str, path: Path) -> str | None:
    name = path.name
    prefix = f"{run_id}-"
    suffix = "-assessment.json"
    if not name.startswith(prefix) or not name.endswith(suffix):
        return None
    return name[len(prefix) : -len(suffix)]


def _lookup_history_field(history: Mapping[str, Any], label: str | None, *fields: str) -> Any | None:
    entry = _history_entry_for_label(history, label)
    if not isinstance(entry, Mapping):
        return None
    result: Any = entry
    for field in fields:
        if not isinstance(result, Mapping) or field not in result:
            return None
        result = result[field]
    return result


def _history_entry_for_label(history: Mapping[str, Any], label: str | None) -> Mapping[str, Any] | None:
    if not label:
        return None
    normalized = normalize_ref(label)
    for key, value in history.items():
        if normalize_ref(key) == normalized and isinstance(value, Mapping):
            return value
    return None


def _history_int(history: Mapping[str, Any], label: str | None, *fields: str) -> int | None:
    result = _lookup_history_field(history, label, *fields)
    if isinstance(result, int):
        return result
    if isinstance(result, str) and result.isdigit():
        return int(result)
    return None


def _history_list(history: Mapping[str, Any], label: str | None, field: str) -> Tuple[str, ...] | None:
    entry = _history_entry_for_label(history, label)
    if not isinstance(entry, Mapping):
        return None
    raw = entry.get(field)
    if isinstance(raw, Sequence):
        return tuple(str(item) for item in raw if item is not None)
    return None


def _load_all_proposals(proposals_dir: Path) -> List[HealthProposal]:
    proposals: List[HealthProposal] = []
    if not proposals_dir.is_dir():
        return proposals
    for path in sorted(proposals_dir.glob("*.json")):
        data = _load_json(path)
        if not data:
            continue
        try:
            proposals.append(HealthProposal.from_dict(data))
        except ValueError:
            continue
    return proposals


def _collect_proposals_for_run(proposals: Iterable[HealthProposal], run_id: str) -> List[ProposalSummary]:
    summaries: List[ProposalSummary] = []
    for proposal in proposals:
        if proposal.source_run_id != run_id:
            continue
        lifecycle_status = proposal.lifecycle_history[-1].status.value
        summaries.append(
            ProposalSummary(
                proposal_id=proposal.proposal_id,
                target=proposal.target,
                rationale=proposal.rationale,
                confidence=proposal.confidence.value,
                source_run_id=proposal.source_run_id,
                lifecycle_status=lifecycle_status,
            )
        )
    return summaries


def _collect_triggers(triggers_dir: Path, run_id: str) -> List[TriggerSummary]:
    triggers: List[TriggerSummary] = []
    if not triggers_dir.is_dir():
        return triggers
    pattern = f"{run_id}-*-trigger.json"
    for path in sorted(triggers_dir.glob(pattern)):
        data = _load_json(path)
        reasons = tuple(str(item) for item in (data.get("trigger_reasons") or ()) if item)
        notes = str(data.get("notes")) if data.get("notes") else None
        triggers.append(
            TriggerSummary(
                primary=str(data.get("primary") or ""),
                secondary=str(data.get("secondary") or ""),
                primary_label=str(data.get("primary_label") or ""),
                secondary_label=str(data.get("secondary_label") or ""),
                reasons=reasons,
                notes=notes,
            )
        )
    return triggers


def _collect_promoted_reports(
    proposals: Iterable[HealthProposal], reviews_dir: Path, after_run_id: str
) -> List[PromotedComparison]:
    promoted: List[PromotedComparison] = []
    for proposal in proposals:
        if not _has_promoted_status(proposal):
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
    data = _load_json(path)
    return data if data else None


def _extract_top_selection(review: Mapping[str, Any]) -> TopSelection | None:
    selections = review.get("selected_drilldowns") or []
    if not isinstance(selections, Sequence) or not selections:
        return None
    selection = selections[0]
    raw_label = selection.get("label") or selection.get("context") or ""
    label = str(raw_label)
    warning = int(selection.get("warning_event_count") or 0)
    pods = int(selection.get("non_running_pod_count") or 0)
    return TopSelection(label=label, warning_event_count=warning, non_running_pod_count=pods)


def _extract_quality_score(review: Mapping[str, Any], dimension: str) -> int | None:
    metrics = review.get("quality_summary") or []
    if not isinstance(metrics, Sequence):
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


def _has_promoted_status(proposal: HealthProposal) -> bool:
    return any(
        entry.status in {
            ProposalLifecycleStatus.PROMOTED,
            ProposalLifecycleStatus.APPLIED,
        }
        for entry in proposal.lifecycle_history
    )
