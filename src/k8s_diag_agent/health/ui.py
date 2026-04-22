"""Utilities that build a compact artifact index for UI consumers."""

from __future__ import annotations

import json
import math
import re
import shlex
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..datetime_utils import parse_iso_to_utc
from ..external_analysis.alertmanager_artifact import (
    read_alertmanager_compact,
    read_alertmanager_sources,
)
from ..external_analysis.alertmanager_source_actions import (
    merge_source_overrides,
    read_source_overrides,
)
from ..external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisPurpose,
    ExternalAnalysisStatus,
    UsefulnessClass,
)
from ..external_analysis.config import (
    AutoDrilldownPolicy,
    ExternalAnalysisSettings,
    ReviewEnrichmentPolicy,
)
from ..external_analysis.next_check_approval import (
    NextCheckApprovalRecord,
    collect_next_check_approvals,
)
from ..external_analysis.utils import artifact_matches_run
from ..structured_logging import emit_structured_log
from .adaptation import HealthProposal
from .notifications import NotificationArtifact

if TYPE_CHECKING:
    from .loop import DrilldownArtifact, HealthAssessmentArtifact, HealthSnapshotRecord


# Directory name for stable "latest" diagnostic pack mirror files
LATEST_PACK_DIR_NAME = "latest"


def _serialize_cluster(
    record: HealthSnapshotRecord,
    assessment_map: Mapping[str, HealthAssessmentArtifact | None],
    drilldown_map: Mapping[str, DrilldownArtifact],
    root_dir: Path,
) -> dict[str, object]:
    assessment = assessment_map.get(record.target.label)
    warning_events = len(record.snapshot.health_signals.warning_events)
    pod_counts = record.snapshot.health_signals.pod_counts
    snapshot_path = _relative_path(root_dir, record.path)
    assessment_path = _relative_path(root_dir, assessment.artifact_path if assessment else None)
    drilldown = drilldown_map.get(record.target.label)
    if drilldown:
        drilldown_path = _relative_path(root_dir, drilldown.artifact_path)
        drilldown_timestamp = drilldown.timestamp.isoformat()
        trigger_reason = drilldown.trigger_reasons[0] if drilldown.trigger_reasons else None
    else:
        drilldown_path = None
        drilldown_timestamp = None
        trigger_reason = None
    return {
        "label": record.target.label,
        "context": record.target.context,
        "cluster_class": record.target.cluster_class,
        "cluster_role": record.target.cluster_role,
        "health_rating": assessment.health_rating.value if assessment else "unknown",
        "warnings": warning_events,
        "non_running_pods": pod_counts.non_running,
        "node_count": record.snapshot.metadata.node_count,
        "control_plane_version": record.snapshot.metadata.control_plane_version or "unknown",
        "baseline_cohort": record.target.baseline_cohort,
        "baseline_policy_path": record.baseline_policy_path,
        "missing_evidence": list(assessment.missing_evidence) if assessment else [],
        "latest_run_timestamp": record.snapshot.metadata.captured_at.isoformat(),
        "top_trigger_reason": trigger_reason,
        "artifact_paths": {
            "snapshot": snapshot_path,
            "assessment": assessment_path,
            "drilldown": drilldown_path,
        },
        "drilldown_available": bool(drilldown),
        "drilldown_timestamp": drilldown_timestamp,
    }


def _serialize_drilldown(artifact: DrilldownArtifact, root_dir: Path) -> dict[str, object]:
    pod_entries = [pod.to_dict() for pod in artifact.non_running_pods]
    rollout_entries = [entry.to_dict() for entry in artifact.rollout_status]
    return {
        "label": artifact.label,
        "context": artifact.context,
        "cluster_id": artifact.cluster_id,
        "trigger_reasons": list(artifact.trigger_reasons),
        "missing_evidence": list(artifact.missing_evidence),
        "warning_events": len(artifact.warning_events),
        "non_running_pods": pod_entries,
        "summary": artifact.evidence_summary,
        "rollout_status": rollout_entries,
        "pattern_details": artifact.pattern_details,
        "artifact_path": _relative_path(root_dir, artifact.artifact_path),
    }


def _serialize_proposal(proposal: HealthProposal, root_dir: Path) -> dict[str, object]:
    latest_status = proposal.lifecycle_history[-1]
    data: dict[str, object] = {
        "proposal_id": proposal.proposal_id,
        "target": proposal.target,
        "confidence": proposal.confidence.value,
        "rationale": proposal.rationale,
        "expected_benefit": proposal.expected_benefit,
        "status": latest_status.status.value,
        "lifecycle_history": [entry.to_dict() for entry in proposal.lifecycle_history],
        "source_run_id": proposal.source_run_id,
        "artifact_path": _relative_path(root_dir, proposal.artifact_path),
        "review_artifact": _relative_path(root_dir, proposal.source_artifact_path),
    }
    # Thread artifact_id for provenance/debugging surfaces (optional)
    if proposal.artifact_id:
        data["artifact_id"] = proposal.artifact_id
    return data


def _serialize_review_enrichment_policy(policy: ReviewEnrichmentPolicy) -> dict[str, object]:
    provider = (policy.provider or "").strip()
    return {
        "enabled": policy.enabled,
        "provider": provider or None,
    }


def _serialize_auto_drilldown_policy(policy: AutoDrilldownPolicy) -> dict[str, object]:
    provider = (policy.provider or "").strip()
    return {
        "enabled": policy.enabled,
        "provider": provider or None,
        "maxPerRun": policy.max_per_run,
    }


NotificationRecord = tuple[NotificationArtifact, Path]


def write_health_ui_index(
    output_dir: Path,
    run_id: str,
    run_label: str,
    collector_version: str,
    records: Sequence[HealthSnapshotRecord],
    assessments: Sequence[HealthAssessmentArtifact],
    drilldowns: Sequence[DrilldownArtifact],
    proposals: Sequence[HealthProposal],
    external_analysis: Sequence[ExternalAnalysisArtifact] = (),
    notifications: Sequence[NotificationRecord] = (),
    external_analysis_settings: ExternalAnalysisSettings | None = None,
    available_adapters: Iterable[str] | None = None,
    expected_scheduler_interval_seconds: int | None = None,
) -> Path:
    assessment_map = {artifact.label: artifact for artifact in assessments}
    drilldown_map = _latest_drilldown_map(drilldowns)
    clusters = [
        _serialize_cluster(record, assessment_map, drilldown_map, output_dir)
        for record in records
    ]
    deterministic_next_checks = _build_deterministic_next_checks_projection(
        clusters,
        assessment_map,
        drilldown_map,
        output_dir,
    )
    cluster_context_map = {record.target.label: record.target.context for record in records}
    drilldown_entries = [
        _serialize_drilldown(artifact, output_dir)
        for artifact in sorted(drilldowns, key=lambda item: item.timestamp, reverse=True)
    ]
    latest_drilldown = drilldown_entries[0] if drilldown_entries else None
    proposals_data = [_serialize_proposal(proposal, output_dir) for proposal in proposals]
    drilldown_availability = _serialize_drilldown_availability(records, drilldown_map, output_dir)
    external_analysis_data = _serialize_external_analysis(external_analysis, output_dir)
    historical_entries = _collect_historical_external_analysis_entries(output_dir / "external-analysis")
    auto_drilldown_data = _serialize_auto_drilldown_interpretations(
        external_analysis_data.get("artifacts"), output_dir
    )
    notification_history = _serialize_notification_history(notifications, output_dir)
    latest_assessment = _serialize_latest_assessment(assessments, output_dir)
    review_enrichment_entry = _serialize_review_enrichment(
        external_analysis,
        output_dir,
        run_id,
        historical_entries,
    )
    plan_entry = _serialize_next_check_plan(external_analysis, output_dir, run_id)
    queue_entry = _build_next_check_queue(plan_entry, cluster_context_map)
    settings = external_analysis_settings or ExternalAnalysisSettings()
    review_config = _serialize_review_enrichment_policy(settings.review_enrichment)
    review_status = _build_review_enrichment_status(
        external_analysis_settings,
        available_adapters,
        bool(review_enrichment_entry),
        review_config,
    )
    planner_availability_entry = _build_next_check_planner_availability(
        plan_entry, review_enrichment_entry, review_status
    )
    auto_config = _serialize_auto_drilldown_policy(settings.auto_drilldown)
    diagnostic_pack_review_entry = _serialize_diagnostic_pack_review(
        external_analysis, output_dir, run_id
    )
    # Read Alertmanager compact artifact if available
    alertmanager_compact_entry = _serialize_alertmanager_compact(output_dir, run_id)
    # Read Alertmanager sources inventory if available
    alertmanager_sources_entry = _serialize_alertmanager_sources(output_dir, run_id)
    run_entry = {
        "run_id": run_id,
        "run_label": run_label,
        "timestamp": datetime.now(UTC).isoformat(),
        "collector_version": collector_version,
        "cluster_count": len(clusters),
        "drilldown_count": len(drilldowns),
        "proposal_count": len(proposals_data),
        "external_analysis_count": external_analysis_data.get("count", 0),
        "notification_count": len(notifications),
        "llm_stats": _build_llm_stats(external_analysis_data),
        "historical_llm_stats": _build_historical_llm_stats(
            output_dir / "external-analysis", historical_entries
        ),
        "llm_activity": _serialize_llm_activity(historical_entries, output_dir),
        "llm_policy": _build_llm_policy(
            settings,
            external_analysis,
            len(drilldowns),
        ),
        "provider_execution": _build_provider_execution(
            settings,
            external_analysis,
            drilldowns,
            review_config,
        ),
        "auto_drilldown_config": auto_config,
        "review_enrichment": review_enrichment_entry,
        "review_enrichment_config": review_config,
        "review_enrichment_status": review_status,
        "planner_availability": planner_availability_entry,
        "next_check_plan": plan_entry,
        "next_check_queue": queue_entry,
        "next_check_queue_explanation": _build_next_check_queue_explanation(
            clusters,
            drilldown_availability,
            plan_entry,
            queue_entry,
            review_enrichment_entry,
            review_status,
            deterministic_next_checks,
        ),
        "deterministic_next_checks": deterministic_next_checks,
        "diagnostic_pack_review": diagnostic_pack_review_entry,
        "diagnostic_pack": _serialize_diagnostic_pack(output_dir, run_id, run_label),
        "next_check_execution_history": _build_next_check_execution_history(
            external_analysis, output_dir, run_id
        ),
        "scheduler_interval_seconds": expected_scheduler_interval_seconds,
        "alertmanager_compact": alertmanager_compact_entry,
        "alertmanager_sources": alertmanager_sources_entry,
    }
    index = {
        "run": run_entry,
        "fleet_status": _serialize_fleet_status(clusters),
        "clusters": clusters,
        "drilldowns": drilldown_entries,
        "latest_drilldown": latest_drilldown,
        "proposal_status_summary": _serialize_proposal_status_summary(proposals_data),
        "proposals": proposals_data,
        "drilldown_availability": drilldown_availability,
        "notification_history": notification_history,
        "external_analysis": external_analysis_data,
        "auto_drilldown_interpretations": auto_drilldown_data,
        "latest_assessment": latest_assessment,
        "next_check_plan": plan_entry,
        "deterministic_next_checks": deterministic_next_checks,
    }
    index["run_stats"] = _build_run_stats(output_dir / "reviews")
    index_path = output_dir / "ui-index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return index_path


def _relative_path(base: Path, target: object | None) -> str | None:
    if target is None:
        return None
    candidate = Path(str(target))
    try:
        return str(candidate.relative_to(base))
    except ValueError:
        return str(candidate)


def _latest_drilldown_map(drilldowns: Sequence[DrilldownArtifact]) -> dict[str, DrilldownArtifact]:
    mapping: dict[str, DrilldownArtifact] = {}
    for artifact in sorted(drilldowns, key=lambda item: item.timestamp, reverse=True):
        mapping.setdefault(artifact.label, artifact)
    return mapping


_RATING_ORDER = ("degraded", "healthy", "unknown")
_PROPOSAL_STATUS_ORDER = (
    "pending",
    "checked",
    "accepted",
    "rejected",
    "applied",
    "proposed",
    "replayed",
    "promoted",
)
_ANALYSIS_STATUS_ORDER = tuple(status.value for status in ExternalAnalysisStatus)
_LLM_ACTIVITY_LIMIT = 20
_NOTIFICATION_HISTORY_LIMIT = 20
_NEXT_CHECK_EXECUTION_HISTORY_LIMIT = 5
_NEXT_CHECK_QUEUE_STATUS_ORDER = (
    "approved-ready",
    "safe-ready",
    "approval-needed",
    "failed",
    "completed",
    "duplicate-or-stale",
)
_NEXT_CHECK_QUEUE_PRIORITY_ORDER = {
    "primary": 0,
    "secondary": 1,
    "fallback": 2,
}
_QUEUE_STATUS_ORDER = {status: idx for idx, status in enumerate(_NEXT_CHECK_QUEUE_STATUS_ORDER)}
_SCOPE_CURRENT_RUN = "current_run"
_SCOPE_RETAINED_HISTORY = "retained_history"


def _serialize_fleet_status(clusters: Sequence[dict[str, object]]) -> dict[str, object]:
    counts: dict[str, int] = {}
    degraded: list[str] = []
    for cluster in clusters:
        rating = str(cluster.get("health_rating") or "unknown").lower()
        counts[rating] = counts.get(rating, 0) + 1
        if rating == "degraded":
            degraded.append(str(cluster.get("label")))
    ordered: list[dict[str, object]] = []
    seen: set[str] = set()
    for rating in _RATING_ORDER:
        if rating in counts:
            ordered.append({"rating": rating, "count": counts[rating]})
            seen.add(rating)
    for rating, count in sorted(counts.items()):
        if rating in seen:
            continue
        ordered.append({"rating": rating, "count": count})
    return {"rating_counts": ordered, "degraded_clusters": degraded}


def _serialize_proposal_status_summary(proposals: Sequence[dict[str, object]]) -> dict[str, object]:
    counts: dict[str, int] = {}
    for proposal in proposals:
        status = str(proposal.get("status") or "unknown").lower()
        counts[status] = counts.get(status, 0) + 1
    ordered: list[dict[str, object]] = []
    seen: set[str] = set()
    for status in _PROPOSAL_STATUS_ORDER:
        if status in counts:
            ordered.append({"status": status, "count": counts[status]})
            seen.add(status)
    for status, count in sorted(counts.items()):
        if status in seen:
            continue
        ordered.append({"status": status, "count": count})
    return {"status_counts": ordered}


def _serialize_drilldown_availability(
    records: Sequence[HealthSnapshotRecord],
    drilldown_map: Mapping[str, DrilldownArtifact],
    root_dir: Path,
) -> dict[str, object]:
    coverage: list[dict[str, object]] = []
    available = 0
    missing_labels: list[str] = []
    for record in sorted(records, key=lambda item: item.target.label):
        artifact = drilldown_map.get(record.target.label)
        if artifact:
            available += 1
            timestamp = artifact.timestamp.isoformat()
            path = _relative_path(root_dir, artifact.artifact_path)
            available_flag = True
        else:
            timestamp = None
            path = None
            missing_labels.append(record.target.label)
            available_flag = False
        coverage.append(
            {
                "label": record.target.label,
                "context": record.target.context,
                "available": available_flag,
                "timestamp": timestamp,
                "artifact_path": path,
            }
        )
    total = len(records)
    return {
        "total_clusters": total,
        "available": available,
        "missing": max(total - available, 0),
        "coverage": coverage,
        "missing_clusters": missing_labels,
    }


def _serialize_external_analysis(
    artifacts: Sequence[ExternalAnalysisArtifact],
    root_dir: Path,
) -> dict[str, object]:
    entries: list[dict[str, object]] = []
    counts: dict[str, int] = {}
    for artifact in sorted(artifacts, key=lambda item: item.timestamp, reverse=True):
        status = artifact.status.value
        counts[status] = counts.get(status, 0) + 1
        entry: dict[str, object] = {
            "tool_name": artifact.tool_name,
            "cluster_label": artifact.cluster_label,
            "run_id": artifact.run_id,
            "run_label": artifact.run_label,
            "status": status,
            "summary": artifact.summary,
            "findings": list(artifact.findings),
            "suggested_next_checks": list(artifact.suggested_next_checks),
            "timestamp": artifact.timestamp.isoformat(),
            "artifact_path": _relative_path(root_dir, artifact.artifact_path),
            "duration_ms": artifact.duration_ms,
            "provider": artifact.provider,
            "purpose": artifact.purpose.value,
            "payload": artifact.payload,
            "error_summary": artifact.error_summary,
            "skip_reason": artifact.skip_reason,
        }
        # Immutable artifact instance identity for provenance/debugging
        if artifact.artifact_id:
            entry["artifact_id"] = artifact.artifact_id
        entries.append(entry)
    status_counts: list[dict[str, object]] = []
    seen: set[str] = set()
    for status in _ANALYSIS_STATUS_ORDER:
        if status in counts:
            status_counts.append({"status": status, "count": counts[status]})
            seen.add(status)
    for status, count in sorted(counts.items()):
        if status in seen:
            continue
        status_counts.append({"status": status, "count": count})
    return {"count": len(entries), "status_counts": status_counts, "artifacts": entries}


def _serialize_review_enrichment(
    artifacts: Sequence[ExternalAnalysisArtifact],
    root_dir: Path,
    run_id: str,
    fallback: Sequence[Mapping[str, object]] | None = None,
) -> dict[str, object] | None:
    artifact = _find_review_enrichment_artifact(artifacts, run_id)
    if not artifact and fallback:
        fallback_entries: list[ExternalAnalysisArtifact] = []
        for raw in fallback:
            if not isinstance(raw, Mapping):
                continue
            try:
                candidate = ExternalAnalysisArtifact.from_dict(raw)
            except Exception:
                continue
            if candidate.run_id != run_id:
                continue
            if candidate.purpose != ExternalAnalysisPurpose.REVIEW_ENRICHMENT:
                continue
            fallback_entries.append(candidate)
        if fallback_entries:
            artifact = sorted(
                fallback_entries, key=lambda item: item.timestamp, reverse=True
            )[0]
    if not artifact:
        return None
    payload = artifact.payload if isinstance(artifact.payload, Mapping) else {}

    # Merge interpretation field (which carries alertmanagerEvidenceReferences) into payload
    # This ensures the bounded evidence references are threaded through to the UI
    if artifact.interpretation and isinstance(artifact.interpretation, Mapping):
        for key, value in artifact.interpretation.items():
            if key not in payload:
                payload[key] = value

    def _list_from(*keys: str) -> list[str]:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                return [str(item) for item in value]
            if value is not None:
                return [str(value)]
        return []

    # Extract alertmanager evidence references from merged payload
    alertmanager_refs = payload.get("alertmanagerEvidenceReferences") or payload.get("alertmanager_evidence_references")

    result: dict[str, object] = {
        "status": artifact.status.value,
        "provider": artifact.provider,
        "timestamp": artifact.timestamp.isoformat(),
        "summary": artifact.summary,
        "triageOrder": _list_from("triageOrder", "triage_order"),
        "topConcerns": _list_from("topConcerns", "top_concerns"),
        "evidenceGaps": _list_from("evidenceGaps", "evidence_gaps"),
        "nextChecks": _list_from("nextChecks", "next_checks"),
        "focusNotes": _list_from("focusNotes", "focus_notes", "caveats", "proposal_caveats"),
        "artifactPath": _relative_path(root_dir, artifact.artifact_path),
        "errorSummary": artifact.error_summary,
        "skipReason": artifact.skip_reason,
    }
    if alertmanager_refs is not None:
        result["alertmanagerEvidenceReferences"] = alertmanager_refs
    return result


def _find_review_enrichment_artifact(
    artifacts: Sequence[ExternalAnalysisArtifact], run_id: str
) -> ExternalAnalysisArtifact | None:
    for artifact in sorted(artifacts, key=lambda item: item.timestamp, reverse=True):
        if (
            artifact.purpose == ExternalAnalysisPurpose.REVIEW_ENRICHMENT
            and artifact_matches_run(artifact, run_id)
        ):
            return artifact
    return None


def _find_diagnostic_pack_review_artifact(
    artifacts: Sequence[ExternalAnalysisArtifact], run_id: str
) -> ExternalAnalysisArtifact | None:
    for artifact in sorted(artifacts, key=lambda item: item.timestamp, reverse=True):
        if (
            artifact.purpose == ExternalAnalysisPurpose.DIAGNOSTIC_PACK_REVIEW
            and artifact_matches_run(artifact, run_id)
        ):
            return artifact
    return None


def _normalize_sequence(
    payload: Mapping[str, object], *keys: str
) -> tuple[str, ...]:
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return _coerce_sequence(value)
    return ()


def _serialize_diagnostic_pack_review(
    artifacts: Sequence[ExternalAnalysisArtifact],
    root_dir: Path,
    run_id: str,
) -> dict[str, object] | None:
    artifact = _find_diagnostic_pack_review_artifact(artifacts, run_id)
    if not artifact:
        return None
    payload = artifact.payload if isinstance(artifact.payload, Mapping) else {}
    provider_review_raw = payload.get("provider_review") or payload.get("providerReview")
    provider_review = dict(provider_review_raw) if isinstance(provider_review_raw, Mapping) else None
    return {
        "timestamp": artifact.timestamp.isoformat(),
        "summary": payload.get("summary") or artifact.summary,
        "majorDisagreements": _normalize_sequence(
            payload, "major_disagreements", "majorDisagreements"
        ),
        "missingChecks": _normalize_sequence(
            payload, "missing_checks", "missingChecks"
        ),
        "rankingIssues": _normalize_sequence(
            payload, "ranking_issues", "rankingIssues"
        ),
        "genericChecks": _normalize_sequence(
            payload, "generic_checks", "genericChecks"
        ),
        "recommendedNextActions": _normalize_sequence(
            payload,
            "recommended_next_actions",
            "recommendedNextActions",
        ),
        "driftMisprioritized": bool(
            payload.get("drift_misprioritized") or payload.get("driftMisprioritized")
        ),
        "confidence": payload.get("confidence"),
        "providerStatus": payload.get("provider_status") or artifact.status.value,
        "providerSummary": payload.get("provider_summary") or artifact.summary,
        "providerErrorSummary": payload.get("provider_error_summary") or artifact.error_summary,
        "providerSkipReason": payload.get("provider_skip_reason") or artifact.skip_reason,
        "providerReview": provider_review,
        "artifactPath": _relative_path(root_dir, artifact.artifact_path),
    }


_DIAGNOSTIC_PACK_TIMESTAMP_PATTERN = re.compile(r"\d{8}T\d{6}Z")


def _serialize_diagnostic_pack(
    root_dir: Path, run_id: str, run_label: str
) -> dict[str, object] | None:
    packs_dir = root_dir / "diagnostic-packs"
    if not packs_dir.is_dir():
        return None
    glob_pattern = f"diagnostic-pack-{run_id}-*.zip"
    latest_path: Path | None = None
    latest_time: datetime | None = None
    for candidate in packs_dir.glob(glob_pattern):
        if not candidate.is_file():
            continue
        parsed_timestamp: datetime | None = None
        match = _DIAGNOSTIC_PACK_TIMESTAMP_PATTERN.search(candidate.name)
        if match:
            try:
                parsed_timestamp = datetime.strptime(match.group(0), "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
            except ValueError:
                parsed_timestamp = None
        entry_time = parsed_timestamp
        if entry_time is None:
            try:
                entry_time = datetime.fromtimestamp(candidate.stat().st_mtime, UTC)
            except OSError:
                entry_time = None
        if entry_time is None:
            continue
        if latest_time is None or entry_time > latest_time:
            latest_path = candidate
            latest_time = entry_time
    if not latest_path:
        return None
    label_value = run_label.strip() if run_label and run_label.strip() else None

    # Look for the stable "latest" mirror files
    latest_mirror_dir = packs_dir / LATEST_PACK_DIR_NAME
    review_bundle_path: Path | None = None
    review_input_14b_path: Path | None = None
    if latest_mirror_dir.is_dir():
        bundle_candidate = latest_mirror_dir / "review_bundle.json"
        if bundle_candidate.is_file():
            review_bundle_path = bundle_candidate
        input_candidate = latest_mirror_dir / "review_input_14b.json"
        if input_candidate.is_file():
            review_input_14b_path = input_candidate

    result: dict[str, object] = {
        "path": _relative_path(root_dir, latest_path),
        "timestamp": latest_time.isoformat() if latest_time else None,
        "label": label_value,
    }

    # Add mirrored review files if they exist
    if review_bundle_path:
        result["review_bundle_path"] = _relative_path(root_dir, review_bundle_path)
    if review_input_14b_path:
        result["review_input_14b_path"] = _relative_path(root_dir, review_input_14b_path)

    return result


def _plan_paths_match(plan_path: str | None, approval_path: str | None) -> bool:
    if not plan_path or not approval_path:
        return False
    if plan_path == approval_path:
        return True
    try:
        return Path(plan_path).name == Path(approval_path).name
    except Exception:
        return False


def _log_next_check_approval_freshness(
    *,
    run_label: str | None,
    run_id: str,
    candidate_id: str | None,
    candidate_index: int | None,
    plan_artifact_path: str | None,
    approval_plan_path: str | None,
    candidate_description: str | None,
    status: str,
) -> None:
    if not run_label:
        return
    metadata: dict[str, object | None] = {
        "candidateId": candidate_id,
        "candidateIndex": candidate_index,
        "planArtifactPath": plan_artifact_path,
        "approvalPlanPath": approval_plan_path,
        "candidateDescription": candidate_description,
        "status": status,
    }
    emit_structured_log(
        component="next-check-approval",
        message=f"Next-check approval treated as {status}",
        severity="INFO" if status in ("approval-stale", "approval-orphaned") else "DEBUG",
        run_label=run_label,
        run_id=run_id,
        metadata=metadata,
    )
    

@dataclass(frozen=True)
class FailureFollowUp:
    failure_class: str | None
    failure_summary: str | None
    suggested_next_operator_move: str | None


@dataclass(frozen=True)
class ResultInterpretation:
    result_class: str
    result_summary: str | None
    suggested_next_operator_move: str | None


@dataclass(frozen=True)
class NextCheckExecutionRecord:
    candidate_id: str | None
    candidate_index: int | None
    artifact_path: str | None
    timestamp: datetime
    status: str
    timed_out: bool | None
    follow_up: FailureFollowUp | None
    result_interpretation: ResultInterpretation | None


def _collect_next_check_execution_records(
    artifacts: Sequence[ExternalAnalysisArtifact], run_id: str
) -> tuple[dict[str, NextCheckExecutionRecord], dict[int, NextCheckExecutionRecord]]:
    by_id: dict[str, NextCheckExecutionRecord] = {}
    by_index: dict[int, NextCheckExecutionRecord] = {}
    for artifact in sorted(artifacts, key=lambda item: item.timestamp):
        if (
            artifact.purpose != ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION
            or not artifact_matches_run(artifact, run_id)
        ):
            continue
        payload = artifact.payload if isinstance(artifact.payload, Mapping) else {}
        raw_id = payload.get("candidateId")
        raw_index = payload.get("candidateIndex")
        candidate_id = raw_id if isinstance(raw_id, str) and raw_id else None
        candidate_index = raw_index if isinstance(raw_index, int) else None
        follow_up = _classify_execution_failure(artifact)
        result_interpretation = _classify_execution_success(artifact)
        record = NextCheckExecutionRecord(
            candidate_id=candidate_id,
            candidate_index=candidate_index,
            artifact_path=str(artifact.artifact_path) if artifact.artifact_path else None,
            timestamp=artifact.timestamp,
            status=artifact.status.value,
            timed_out=artifact.timed_out,
            follow_up=follow_up,
            result_interpretation=result_interpretation,
        )
        if candidate_id:
            existing = by_id.get(candidate_id)
            if existing is None or record.timestamp >= existing.timestamp:
                by_id[candidate_id] = record
        if candidate_index is not None:
            existing = by_index.get(candidate_index)
            if existing is None or record.timestamp >= existing.timestamp:
                by_index[candidate_index] = record
    return by_id, by_index


def _determine_execution_state(record: NextCheckExecutionRecord | None) -> str:
    if not record:
        return "unexecuted"
    if record.timed_out:
        return "timed-out"
    if record.status == ExternalAnalysisStatus.SUCCESS.value:
        return "executed-success"
    return "executed-failed"


def _derive_outcome_status(approval_state: str | None, execution_state: str) -> str:
    if execution_state == "executed-success":
        return "executed-success"
    if execution_state in ("executed-failed", "timed-out"):
        return "executed-failed"
    if approval_state == "approval-stale":
        return "approval-stale"
    if approval_state == "approved":
        return "approved"
    if approval_state == "approval-required":
        return "approval-required"
    if approval_state == "not-required":
        return "not-used"
    return approval_state or "unknown"


def _latest_outcome_artifact(
    record: NextCheckExecutionRecord | None,
    approval_path: str | None,
    approval_timestamp: str | None,
    root_dir: Path,
) -> tuple[str | None, str | None]:
    latest_time: datetime | None = None
    latest_path: str | None = None
    if record:
        latest_time = record.timestamp
        latest_path = _relative_path(root_dir, record.artifact_path)
    if approval_timestamp:
        parsed = _parse_timestamp(approval_timestamp)
        if parsed and (latest_time is None or parsed > latest_time):
            latest_time = parsed
            latest_path = approval_path
    timestamp = latest_time.isoformat() if latest_time else None
    return latest_path, timestamp


def _determine_next_check_queue_status(candidate: Mapping[str, object]) -> str:
    requires_approval = bool(candidate.get("requiresOperatorApproval"))
    safe_to_automate = bool(candidate.get("safeToAutomate"))
    approval_state = str(candidate.get("approvalState") or "").lower()
    execution_state = str(candidate.get("executionState") or "unexecuted").lower()
    duplicate = bool(candidate.get("duplicateOfExistingEvidence"))
    if duplicate or approval_state in ("approval-stale", "approval-orphaned"):
        return "duplicate-or-stale"
    if execution_state in ("executed-failed", "timed-out"):
        return "failed"
    if execution_state == "executed-success":
        return "completed"
    if requires_approval:
        if approval_state == "approved":
            return "approved-ready"
        return "approval-needed"
    if safe_to_automate and execution_state == "unexecuted":
        return "safe-ready"
    return "duplicate-or-stale"


def _queue_priority_value(value: object | None) -> int:
    label = str(value or "").lower()
    return _NEXT_CHECK_QUEUE_PRIORITY_ORDER.get(label, len(_NEXT_CHECK_QUEUE_PRIORITY_ORDER))


def _queue_sort_key(entry: Mapping[str, object]) -> tuple[int, int, int, str]:
    status = str(entry.get("queueStatus") or "duplicate-or-stale")
    status_index = _QUEUE_STATUS_ORDER.get(status, len(_QUEUE_STATUS_ORDER))
    priority_index = _queue_priority_value(entry.get("priorityLabel"))
    candidate_index = entry.get("candidateIndex")
    index_value = candidate_index if isinstance(candidate_index, int) else 0
    identifier = str(entry.get("candidateId") or "")
    return status_index, priority_index, index_value, identifier


_FAILURE_CLASS_TIMED_OUT = "timed-out"
_FAILURE_CLASS_COMMAND_UNAVAILABLE = "command-unavailable"
_FAILURE_CLASS_CONTEXT_UNAVAILABLE = "context-unavailable"
_FAILURE_CLASS_COMMAND_FAILED = "command-failed"
_FAILURE_CLASS_BLOCKED_BY_GATING = "blocked-by-gating"
_FAILURE_CLASS_APPROVAL_MISSING = "approval-missing-or-stale"
_FAILURE_CLASS_UNKNOWN = "unknown-failure"

_FAILURE_ACTIONS: dict[str, str] = {
    _FAILURE_CLASS_TIMED_OUT: "Retry candidate",
    _FAILURE_CLASS_COMMAND_UNAVAILABLE: "Inspect artifact output",
    _FAILURE_CLASS_CONTEXT_UNAVAILABLE: "Open cluster detail",
    _FAILURE_CLASS_COMMAND_FAILED: "Inspect artifact output",
    _FAILURE_CLASS_BLOCKED_BY_GATING: "Open cluster detail",
    _FAILURE_CLASS_APPROVAL_MISSING: "Review approval state",
    _FAILURE_CLASS_UNKNOWN: "Inspect artifact output",
}

_FAILURE_DEFAULT_SUMMARIES: dict[str, str] = {
    _FAILURE_CLASS_TIMED_OUT: "Command timed out.",
    _FAILURE_CLASS_COMMAND_UNAVAILABLE: "kubectl is unavailable on this host.",
    _FAILURE_CLASS_CONTEXT_UNAVAILABLE: "Unable to resolve the cluster context.",
    _FAILURE_CLASS_COMMAND_FAILED: "Command returned a non-zero exit code.",
    _FAILURE_CLASS_BLOCKED_BY_GATING: "Candidate was blocked by planner gating.",
    _FAILURE_CLASS_APPROVAL_MISSING: "Candidate requires operator approval.",
    _FAILURE_CLASS_UNKNOWN: "Execution failed without details.",
}


_RESULT_CLASS_USEFUL = "useful-signal"
_RESULT_CLASS_EMPTY = "empty-result"
_RESULT_CLASS_NOISY = "noisy-result"
_RESULT_CLASS_INCONCLUSIVE = "inconclusive"
_RESULT_CLASS_PARTIAL = "partial-result"

_RESULT_SUMMARIES: dict[str, str] = {
    _RESULT_CLASS_USEFUL: "Command captured signal-rich output that can guide the diagnosis.",
    _RESULT_CLASS_EMPTY: "Command completed without producing output.",
    _RESULT_CLASS_NOISY: "Command emitted warnings or noise alongside the output.",
    _RESULT_CLASS_INCONCLUSIVE: "Output is limited; it is unclear whether it contains useful signal.",
    _RESULT_CLASS_PARTIAL: "Output was truncated or interrupted before completion.",
}

_RESULT_ACTIONS: dict[str, str] = {
    _RESULT_CLASS_USEFUL: "Correlate this evidence with the target symptom.",
    _RESULT_CLASS_EMPTY: "Rerun with a broader selector or check that the target exists.",
    _RESULT_CLASS_NOISY: "Inspect the artifact for warnings before trusting the signal.",
    _RESULT_CLASS_INCONCLUSIVE: "Open the artifact to confirm whether the result is actionable.",
    _RESULT_CLASS_PARTIAL: "Download the artifact to review the full output or rerun with a higher limit.",
}

_RESULT_USEFUL_OUTPUT_THRESHOLD = 256
_RESULT_USEFUL_FAMILIES = {
    "kubectl-logs",
    "kubectl-describe",
}
_RESULT_NOISE_KEYWORDS = ("warning", "warn", "error", "failed", "denied")


def _classify_execution_failure(artifact: ExternalAnalysisArtifact) -> FailureFollowUp | None:
    if artifact.status == ExternalAnalysisStatus.SUCCESS:
        return None
    summary = artifact.error_summary or artifact.summary
    normalized = (summary or "").lower()
    if artifact.timed_out:
        failure_class = _FAILURE_CLASS_TIMED_OUT
    elif summary and ("kubectl is unavailable" in normalized or "command runner not found" in normalized or "no such file or directory" in normalized):
        failure_class = _FAILURE_CLASS_COMMAND_UNAVAILABLE
    elif summary and "context" in normalized and any(token in normalized for token in ("missing", "unavailable", "not found")):
        failure_class = _FAILURE_CLASS_CONTEXT_UNAVAILABLE
    elif summary:
        failure_class = _FAILURE_CLASS_COMMAND_FAILED
    else:
        failure_class = _FAILURE_CLASS_UNKNOWN
    failure_summary = summary or _FAILURE_DEFAULT_SUMMARIES.get(failure_class)
    suggested = _FAILURE_ACTIONS.get(failure_class)
    return FailureFollowUp(failure_class, failure_summary, suggested)


def _coerce_int_value(value: object | None) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _looks_noisy(output: str) -> bool:
    normalized = output.lower()
    return any(keyword in normalized for keyword in _RESULT_NOISE_KEYWORDS)


def _classify_execution_success(artifact: ExternalAnalysisArtifact) -> ResultInterpretation | None:
    if artifact.status != ExternalAnalysisStatus.SUCCESS:
        return None
    payload = artifact.payload if isinstance(artifact.payload, Mapping) else {}
    timed_out = bool(artifact.timed_out or payload.get("timedOut"))
    stdout_truncated = bool(artifact.stdout_truncated or payload.get("stdoutTruncated"))
    stderr_truncated = bool(artifact.stderr_truncated or payload.get("stderrTruncated"))
    truncated = stdout_truncated or stderr_truncated
    bytes_captured = (
        artifact.output_bytes_captured
        if artifact.output_bytes_captured is not None
        else _coerce_int_value(payload.get("outputBytesCaptured"))
    )
    raw_output = str(artifact.raw_output or "").strip()
    has_output = bool(bytes_captured) or bool(raw_output)
    command_family = str(payload.get("commandFamily") or "").lower()

    if timed_out:
        result_class = _RESULT_CLASS_PARTIAL
    elif not has_output:
        result_class = _RESULT_CLASS_EMPTY
    elif truncated:
        result_class = _RESULT_CLASS_PARTIAL
    elif raw_output and _looks_noisy(raw_output):
        result_class = _RESULT_CLASS_NOISY
    elif bytes_captured >= _RESULT_USEFUL_OUTPUT_THRESHOLD or command_family in _RESULT_USEFUL_FAMILIES:
        result_class = _RESULT_CLASS_USEFUL
    else:
        result_class = _RESULT_CLASS_INCONCLUSIVE

    summary = _RESULT_SUMMARIES.get(result_class) or "Command output requires review."
    suggested = _RESULT_ACTIONS.get(result_class)
    return ResultInterpretation(result_class, summary, suggested)


# Mapping from UsefulnessClass to the internal result class names used in UI
_USE_TO_RESULT_CLASS_MAP: dict[str, str] = {
    "useful": _RESULT_CLASS_USEFUL,
    "partial": _RESULT_CLASS_PARTIAL,
    "noisy": _RESULT_CLASS_NOISY,
    "empty": _RESULT_CLASS_EMPTY,
}


def _map_usefulness_to_result_class(usefulness: UsefulnessClass) -> str:
    """Map persisted usefulness class to UI result class for backward compatibility."""
    return _USE_TO_RESULT_CLASS_MAP.get(usefulness.value, _RESULT_CLASS_INCONCLUSIVE)


def _apply_result_interpretation(candidate: dict[str, object], interpretation: ResultInterpretation | None) -> None:
    if not interpretation:
        return
    candidate["resultClass"] = interpretation.result_class
    candidate["resultSummary"] = interpretation.result_summary
    candidate["suggestedNextOperatorMove"] = interpretation.suggested_next_operator_move

def _classify_blocked_candidate(candidate: Mapping[str, object]) -> FailureFollowUp | None:
    queue_status = str(candidate.get("queueStatus") or "")
    if queue_status == "duplicate-or-stale":
        return None
    requires_approval = bool(candidate.get("requiresOperatorApproval"))
    approval_state = str(candidate.get("approvalState") or "").lower()
    if requires_approval and approval_state not in ("approved", "not-required"):
        if approval_state == "approval-stale":
            summary = "Approval is stale; reapprove this candidate."
        elif approval_state == "approval-orphaned":
            summary = "Approval record is orphaned; reapprove the candidate."
        else:
            summary = "Candidate requires operator approval before execution."
        return FailureFollowUp(
            _FAILURE_CLASS_APPROVAL_MISSING,
            summary,
            _FAILURE_ACTIONS[_FAILURE_CLASS_APPROVAL_MISSING],
        )
    if queue_status in ("failed", "approval-needed", "safe-ready", "approved-ready"):
        gating_reason = candidate.get("gatingReason") or candidate.get("blockingReason")
        reason_text = str(gating_reason).strip() if gating_reason else ""
        if reason_text:
            summary = f"Gating reason: {reason_text}"
            return FailureFollowUp(
                _FAILURE_CLASS_BLOCKED_BY_GATING,
                summary,
                _FAILURE_ACTIONS[_FAILURE_CLASS_BLOCKED_BY_GATING],
            )
    return None


def _apply_failure_follow_up(candidate: dict[str, object], follow_up: FailureFollowUp | None) -> None:
    if not follow_up or not follow_up.failure_class:
        return
    candidate["failureClass"] = follow_up.failure_class
    candidate["failureSummary"] = follow_up.failure_summary
    candidate["suggestedNextOperatorMove"] = follow_up.suggested_next_operator_move


def _strip_context_tokens(tokens: Sequence[str]) -> tuple[str, ...]:
    sanitized: list[str] = []
    iterator = iter(tokens)
    for token in iterator:
        if token in ("--context", "-c"):
            next(iterator, None)
            continue
        if token.startswith("--context=") or token.startswith("-c="):
            continue
        sanitized.append(token)
    return tuple(sanitized)


def _build_command_preview(description: object | None, target_context: str | None) -> str | None:
    if not isinstance(description, str) or not description.strip():
        return None
    try:
        tokens = shlex.split(description)
    except ValueError:
        tokens = description.strip().split()
    if not tokens:
        return None
    if tokens[0] != "kubectl":
        tokens = ["kubectl", *tokens]
    remainder = _strip_context_tokens(tokens[1:])
    if target_context:
        remainder = (*remainder, "--context", target_context)
    preview_tokens = ("kubectl", *remainder)
    return " ".join(shlex.quote(token) for token in preview_tokens)


def _derive_ranking_reason(entry: Mapping[str, object]) -> str | None:
    """Derive a structured ranking-reason/provenance category.

    Returns a compact machine-readable category that explains why a check
    is in its current ranking position. This complements priorityRationale
    (human-readable) with provenance metadata.

    Returns one of:
    - "duplicate": candidate is a duplicate of existing evidence
    - "approval-gated": requires operator approval before execution
    - "stale-approval": approval record is stale or orphaned
    - "execution-gated": blocked by execution gating (blockingReason)
    - "planner-gated": blocked by planner gating (gatingReason)
    - "safety-gated": blocked by safety gating (safetyReason)
    - "deterministic-secondary": secondary priority from deterministic checks
    - "fallback": fallback priority candidate
    - "already-executed": execution completed successfully
    - "execution-failed": execution failed or timed out
    - None: no structured ranking reason applies

    This provides provenance metadata distinct from priorityRationale.
    """
    # 1. Duplicate
    if bool(entry.get("duplicateOfExistingEvidence")):
        return "duplicate"

    # 2. Stale or orphaned approval
    approval_state = str(entry.get("approvalState") or "").lower()
    if approval_state == "approval-stale":
        return "stale-approval"
    if approval_state == "approval-orphaned":
        return "stale-approval"

    # 3. Approval required
    if bool(entry.get("requiresOperatorApproval")):
        return "approval-gated"

    # 4. Blocked by gating reasons (checked in order of specificity)
    if entry.get("safetyReason"):
        return "safety-gated"
    if entry.get("blockingReason"):
        return "execution-gated"
    if entry.get("gatingReason"):
        return "planner-gated"

    # 5. Execution state
    execution_state = str(entry.get("executionState") or "").lower()
    if execution_state == "executed-success":
        return "already-executed"
    if execution_state in ("executed-failed", "timed-out"):
        return "execution-failed"

    # 6. Priority label
    priority_label = str(entry.get("priorityLabel") or "").lower()
    if priority_label == "secondary":
        return "deterministic-secondary"
    if priority_label == "fallback":
        return "fallback"

    return None


def _derive_priority_rationale(entry: Mapping[str, object]) -> str | None:
    """Derive a compact operator-facing explanation for why an item is in its current state.

    Precedence:
    1. If original priorityRationale exists: preserve it (from planner/enrichment)
    2. duplicate / already covered
    3. approval required / stale approval
    4. blocked by safety or normalization gating
    5. completed / already executed
    6. secondary / lower-priority follow-up
    7. null if no meaningful rationale exists

    This is presentation normalization, not a new policy layer.
    """
    # 0. Preserve original priorityRationale from planner/enrichment if present
    original_priority_rationale = entry.get("priorityRationale")
    if isinstance(original_priority_rationale, str) and original_priority_rationale.strip():
        return original_priority_rationale.strip()

    # 1. Duplicate / already covered
    if bool(entry.get("duplicateOfExistingEvidence")):
        dup_reason = entry.get("duplicateReason")
        if dup_reason:
            return "Already covered by existing evidence"
        return "Already covered by existing evidence"

    # 2. Stale or orphaned approval
    approval_state = str(entry.get("approvalState") or "").lower()
    if approval_state == "approval-stale":
        return "Approval is stale"
    if approval_state == "approval-orphaned":
        return "Approval record orphaned"

    # 3. Approval required
    requires_approval = bool(entry.get("requiresOperatorApproval"))
    if requires_approval:
        approval_reason = entry.get("approvalReason")
        if approval_reason:
            return "Approval required before execution"
        return "Approval required before execution"

    # 4. Blocked by safety or normalization gating
    safety_reason = entry.get("safetyReason")
    blocking_reason = entry.get("blockingReason")
    gating_reason = entry.get("gatingReason")
    if safety_reason:
        return "Blocked by safety gating"
    if blocking_reason:
        return "Blocked by execution gating"
    if gating_reason:
        return "Blocked by planner gating"

    # 5. Completed / already executed (checked before priority label)
    execution_state = str(entry.get("executionState") or "").lower()
    if execution_state == "executed-success":
        return "Already executed"
    if execution_state in ("executed-failed", "timed-out"):
        return "Execution failed"

    # 6. Secondary / lower-priority follow-up
    priority_label = str(entry.get("priorityLabel") or "").lower()
    if priority_label == "secondary":
        return "Secondary follow-up"
    if priority_label == "fallback":
        return "Fallback candidate"

    return None


def _build_next_check_queue(
    plan_entry: Mapping[str, object] | None,
    cluster_context_map: Mapping[str, str],
) -> list[dict[str, object]]:
    if not isinstance(plan_entry, Mapping):
        return []
    raw_candidates = plan_entry.get("candidates")
    if isinstance(raw_candidates, Sequence) and not isinstance(raw_candidates, (str, bytes, bytearray)):
        candidates: Sequence[object] = raw_candidates
    else:
        candidates = []
    queue: list[dict[str, object]] = []
    plan_artifact_path = plan_entry.get("artifactPath")
    for index, entry in enumerate(candidates):
        if not isinstance(entry, Mapping):
            continue
        queue_status = _determine_next_check_queue_status(entry)
        raw_index = entry.get("candidateIndex")
        candidate_index = raw_index if isinstance(raw_index, int) else index
        queue_entry: dict[str, object] = dict(entry)
        queue_entry["queueStatus"] = queue_status
        queue_entry["candidateIndex"] = candidate_index
        queue_entry.setdefault("clusterLabel", entry.get("targetCluster"))
        candidate_context = entry.get("targetContext")
        target_context: str | None = None
        if isinstance(candidate_context, str) and candidate_context.strip():
            target_context = candidate_context.strip()
        else:
            cluster_label = entry.get("targetCluster")
            if isinstance(cluster_label, str):
                context_value = cluster_context_map.get(cluster_label)
                if context_value:
                    target_context = context_value
        queue_entry["targetContext"] = target_context
        queue_entry["planArtifactPath"] = plan_artifact_path
        queue_entry["commandPreview"] = _build_command_preview(entry.get("description"), target_context)
        queue_entry["priorityRationale"] = _derive_priority_rationale(queue_entry)
        queue_entry["rankingReason"] = _derive_ranking_reason(queue_entry)
        # Route demoted CRD checks to drift/parity workstream for visibility
        # When a candidate is demoted due to early incident triage context,
        # it should still be visible in drift-oriented workstream
        ranking_policy_reason = entry.get("rankingPolicyReason")
        if isinstance(ranking_policy_reason, str) and "crd-demoted-early-incident-triage" in ranking_policy_reason:
            queue_entry["workstream"] = "drift"
        queue.append(queue_entry)
    queue.sort(key=_queue_sort_key)
    return queue


def _serialize_next_check_plan(
    artifacts: Sequence[ExternalAnalysisArtifact],
    root_dir: Path,
    run_id: str,
) -> dict[str, object] | None:
    artifact = _find_next_check_plan_artifact(artifacts, run_id)
    if not artifact:
        return None
    payload = artifact.payload if isinstance(artifact.payload, Mapping) else {}
    raw_candidates = payload.get("candidates")
    if isinstance(raw_candidates, Sequence) and not isinstance(raw_candidates, (str, bytes, bytearray)):
        candidates_raw: Sequence[object] = raw_candidates
    else:
        candidates_raw = []
    approvals = collect_next_check_approvals(artifacts, run_id)
    used_approvals: set[NextCheckApprovalRecord] = set()
    plan_artifact_path = str(artifact.artifact_path) if artifact.artifact_path else None
    execution_by_id, execution_by_index = _collect_next_check_execution_records(artifacts, run_id)
    status_counter: Counter[str] = Counter()
    candidates: list[dict[str, object]] = []
    for index, entry in enumerate(candidates_raw):
        if not isinstance(entry, Mapping):
            continue
        candidate = dict(entry)
        requires_approval = bool(candidate.get("requiresOperatorApproval"))
        candidate_id_value = candidate.get("candidateId")
        candidate_id_key = candidate_id_value if isinstance(candidate_id_value, str) and candidate_id_value else None
        explicit_index = candidate.get("candidateIndex")
        candidate_index_key = explicit_index if isinstance(explicit_index, int) else index
        approval_record: NextCheckApprovalRecord | None = None
        if requires_approval:
            if candidate_id_key and candidate_id_key in approvals.by_id:
                approval_record = approvals.by_id[candidate_id_key]
            elif candidate_index_key is not None and candidate_index_key in approvals.by_index:
                approval_record = approvals.by_index[candidate_index_key]
        approval_status = "not-required" if not requires_approval else "approval-required"
        if approval_record:
            used_approvals.add(approval_record)
            if _plan_paths_match(plan_artifact_path, approval_record.plan_artifact_path):
                approval_status = "approved"
            else:
                approval_status = "approval-stale"
            candidate["approvalArtifactPath"] = _relative_path(root_dir, approval_record.artifact_path)
            candidate["approvalTimestamp"] = approval_record.timestamp.isoformat()
            if approval_status == "approval-stale":
                _log_next_check_approval_freshness(
                    run_label=artifact.run_label,
                    run_id=run_id,
                    candidate_id=candidate_id_key,
                    candidate_index=candidate_index_key,
                    plan_artifact_path=plan_artifact_path,
                    approval_plan_path=approval_record.plan_artifact_path,
                    candidate_description=candidate.get("description") if isinstance(candidate.get("description"), str) else None,
                    status=approval_status,
                )
        candidate["approvalStatus"] = approval_status
        candidate["approvalState"] = approval_status
        execution_record: NextCheckExecutionRecord | None = None
        if candidate_id_key:
            execution_record = execution_by_id.get(candidate_id_key)
        if execution_record is None and candidate_index_key is not None:
            execution_record = execution_by_index.get(candidate_index_key)
        execution_state = _determine_execution_state(execution_record)
        candidate["executionState"] = execution_state
        outcome_status = _derive_outcome_status(approval_status, execution_state)
        candidate["outcomeStatus"] = outcome_status
        follow_up = execution_record.follow_up if execution_record else None
        if not follow_up or not follow_up.failure_class:
            follow_up = _classify_blocked_candidate(candidate)
        _apply_failure_follow_up(candidate, follow_up)
        execution_result_interpretation = execution_record.result_interpretation if execution_record else None
        _apply_result_interpretation(candidate, execution_result_interpretation)
        latest_artifact, latest_timestamp = _latest_outcome_artifact(
            execution_record,
            candidate.get("approvalArtifactPath"),
            candidate.get("approvalTimestamp"),
            root_dir,
        )
        candidate["latestArtifactPath"] = latest_artifact
        candidate["latestTimestamp"] = latest_timestamp
        status_counter[outcome_status] += 1
        candidates.append(candidate)
    orphaned: list[dict[str, object]] = []
    all_records = set(approvals.by_id.values()) | set(approvals.by_index.values())
    for record in all_records:
        if record in used_approvals:
            continue
        orphaned.append(
            {
                "approvalStatus": "approval-orphaned",
                "candidateId": record.candidate_id,
                "candidateIndex": record.candidate_index,
                "candidateDescription": record.candidate_description,
                "targetCluster": record.cluster_label,
                "planArtifactPath": record.plan_artifact_path,
                "approvalArtifactPath": _relative_path(root_dir, record.artifact_path),
                "approvalTimestamp": record.timestamp.isoformat(),
            }
        )
        _log_next_check_approval_freshness(
            run_label=artifact.run_label,
            run_id=run_id,
            candidate_id=record.candidate_id,
            candidate_index=record.candidate_index,
            plan_artifact_path=plan_artifact_path,
            approval_plan_path=record.plan_artifact_path,
            candidate_description=record.candidate_description,
            status="approval-orphaned",
        )
    status_counter["approval-orphaned"] += len(orphaned)
    return {
        "status": artifact.status.value,
        "summary": artifact.summary,
        "artifactPath": _relative_path(root_dir, artifact.artifact_path),
        "reviewPath": payload.get("review_path"),
        "enrichmentArtifactPath": payload.get("enrichment_artifact_path"),
        "candidateCount": len(candidates),
        "candidates": candidates,
        "orphanedApprovals": orphaned,
        "outcomeCounts": [
            {"status": key, "count": value}
            for key, value in sorted(status_counter.items())
        ],
        "orphanedApprovalCount": len(orphaned),
    }


def _load_usefulness_review_artifacts(
    artifacts: Sequence[ExternalAnalysisArtifact],
) -> dict[str, dict[str, object]]:
    """Discover usefulness review artifacts and return latest per source execution artifact.

    Scans artifacts for review artifacts matching:
    - purpose = NEXT_CHECK_EXECUTION_USEFULNESS_REVIEW

    Returns a dict mapping source_artifact path -> latest review artifact data.
    If multiple reviews exist for the same source, returns the most recent one.

    Args:
        artifacts: Sequence of ExternalAnalysisArtifact to scan

    Returns:
        Dict mapping source artifact relative path -> latest review artifact data
    """
    reviews_by_source: dict[str, dict[str, object]] = {}

    for artifact in artifacts:
        if artifact.purpose != ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION_USEFULNESS_REVIEW:
            continue

        source_artifact = artifact.source_artifact
        if not source_artifact:
            continue

        # Get reviewed_at timestamp for determining "latest"
        # Use the persisted reviewed_at field from the review artifact payload,
        # not artifact.timestamp (which is the execution artifact's timestamp)
        review_dict = artifact.to_dict()
        reviewed_at = str(review_dict.get("reviewed_at") or artifact.timestamp.isoformat())
        existing = reviews_by_source.get(source_artifact)
        existing_reviewed_at: str = str(existing.get("reviewed_at", "")) if existing else ""
        if existing is None or reviewed_at > existing_reviewed_at:
            review_dict["reviewed_at"] = reviewed_at
            reviews_by_source[source_artifact] = review_dict

    return reviews_by_source


def _build_next_check_execution_history(
    artifacts: Sequence[ExternalAnalysisArtifact],
    root_dir: Path,
    run_id: str,
    limit: int = _NEXT_CHECK_EXECUTION_HISTORY_LIMIT,
) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []

    # Pre-load usefulness review artifacts for merging into entries
    usefulness_reviews_by_source = _load_usefulness_review_artifacts(artifacts)

    for artifact in sorted(artifacts, key=lambda item: item.timestamp, reverse=True):
        if (
            artifact.purpose != ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION
            or not artifact_matches_run(artifact, run_id)
        ):
            continue
        payload = artifact.payload if isinstance(artifact.payload, Mapping) else {}
        follow_up = _classify_execution_failure(artifact)
        # Determine pack refresh status from artifact or default to None
        pack_refresh_status: str | None = None
        if artifact.pack_refresh_status:
            pack_refresh_status = artifact.pack_refresh_status.value
        artifact_path_str = _relative_path(root_dir, artifact.artifact_path)
        entry: dict[str, object] = {
            "timestamp": artifact.timestamp.isoformat(),
            "clusterLabel": artifact.cluster_label,
            "candidateDescription": payload.get("candidateDescription"),
            "commandFamily": payload.get("commandFamily"),
            "status": artifact.status.value,
            "durationMs": artifact.duration_ms,
            "artifactPath": artifact_path_str,
            "timedOut": artifact.timed_out,
            "stdoutTruncated": artifact.stdout_truncated,
            "stderrTruncated": artifact.stderr_truncated,
            "outputBytesCaptured": artifact.output_bytes_captured,
            "packRefreshStatus": pack_refresh_status,
            "packRefreshWarning": artifact.pack_refresh_warning,
            # Provenance fields for traceability
            "candidateId": payload.get("candidateId"),
            "candidateIndex": payload.get("candidateIndex"),
        }

        # Get the execution artifact path for review lookup
        # Normalize to relative path for consistent lookup with review artifacts
        # Review artifacts store source_artifact as relative to root_dir
        raw_artifact_path = artifact.artifact_path
        if raw_artifact_path:
            try:
                execution_artifact_path = str(Path(raw_artifact_path).relative_to(root_dir))
            except ValueError:
                # Already relative or cannot normalize - use as-is
                execution_artifact_path = str(raw_artifact_path)
        else:
            execution_artifact_path = ""

        # Check for usefulness review artifact first (new immutability pattern)
        usefulness_review = usefulness_reviews_by_source.get(execution_artifact_path)
        if usefulness_review is not None:
            # Use usefulness from review artifact
            usefulness_class = usefulness_review.get("usefulness_class")
            if isinstance(usefulness_class, str):
                try:
                    usefulness_enum = UsefulnessClass(usefulness_class)
                    entry["usefulnessClass"] = usefulness_enum.value
                    usefulness_summary = usefulness_review.get("usefulness_summary")
                    if usefulness_summary:
                        entry["usefulnessSummary"] = usefulness_summary
                except ValueError:
                    pass  # Invalid usefulness class, fall through

        # Fall back to legacy embedded usefulness fields on execution artifact
        elif artifact.usefulness_class is not None:
            entry["usefulnessClass"] = artifact.usefulness_class.value
            if artifact.usefulness_summary:
                entry["usefulnessSummary"] = artifact.usefulness_summary

        # Include Alertmanager relevance judgment if available
        if artifact.alertmanager_relevance is not None:
            entry["alertmanagerRelevance"] = artifact.alertmanager_relevance.value
            if artifact.alertmanager_relevance_summary:
                entry["alertmanagerRelevanceSummary"] = artifact.alertmanager_relevance_summary
        # Thread Alertmanager provenance from execution artifact
        if artifact.alertmanager_provenance is not None:
            entry["alertmanagerProvenance"] = artifact.alertmanager_provenance
        if follow_up and follow_up.failure_class:
            entry["failureClass"] = follow_up.failure_class
            entry["failureSummary"] = follow_up.failure_summary
            entry["suggestedNextOperatorMove"] = follow_up.suggested_next_operator_move
        else:
            # Use persisted usefulness or compute from output
            if artifact.usefulness_class is None and usefulness_review is None:
                success_interpretation = _classify_execution_success(artifact)
                if success_interpretation:
                    entry["resultClass"] = success_interpretation.result_class
                    entry["resultSummary"] = success_interpretation.result_summary
                    entry["suggestedNextOperatorMove"] = (
                        success_interpretation.suggested_next_operator_move
                    )
            else:
                # Persisted usefulness exists (from review or legacy) - use it as the result interpretation
                usefulness_class_for_result = entry.get("usefulnessClass")
                if isinstance(usefulness_class_for_result, str):
                    try:
                        usefulness_enum = UsefulnessClass(usefulness_class_for_result)
                        entry["resultClass"] = _map_usefulness_to_result_class(usefulness_enum)
                    except ValueError:
                        entry["resultClass"] = _RESULT_CLASS_INCONCLUSIVE
                entry["resultSummary"] = entry.get("usefulnessSummary")
        entries.append(entry)
        if len(entries) >= limit:
            break
    return entries


def _find_next_check_plan_artifact(
    artifacts: Sequence[ExternalAnalysisArtifact], run_id: str
) -> ExternalAnalysisArtifact | None:
    for artifact in sorted(artifacts, key=lambda item: item.timestamp, reverse=True):
        if (
            artifact.purpose == ExternalAnalysisPurpose.NEXT_CHECK_PLANNING
            and artifact_matches_run(artifact, run_id)
        ):
            return artifact
    return None


_PLANNER_STATUS_POLICY_DISABLED = "policy-disabled"
_PLANNER_STATUS_ENRICHMENT_NOT_ATTEMPTED = "enrichment-not-attempted"
_PLANNER_STATUS_ENRICHMENT_FAILED = "enrichment-failed"
_PLANNER_STATUS_ENRICHMENT_SUCCESS_NO_CHECKS = "enrichment-succeeded-without-next-checks"
_PLANNER_STATUS_PLANNER_MISSING = "planner-missing-unexpectedly"
_PLANNER_STATUS_PLANNER_PRESENT = "planner-present"
_PLANNER_HINT_TEXT = (
    "Cluster Detail next checks may still reflect deterministic assessments or review content "
    "even when the planner artifact is absent."
)
_PLANNER_ARTIFACT_KEYS = ("artifactPath", "enrichmentArtifactPath", "reviewPath")
_PLANNER_NEXT_ACTION_HINTS: dict[str, str] = {
    _PLANNER_STATUS_POLICY_DISABLED: (
        "Review the enrichment policy to re-enable provider-assisted planning or rely on deterministic next checks."
    ),
    _PLANNER_STATUS_ENRICHMENT_NOT_ATTEMPTED: (
        "Inspect Review Enrichment configuration or provider registration to understand why the planner didn't run."
    ),
    _PLANNER_STATUS_ENRICHMENT_FAILED: (
        "Inspect the failed review enrichment artifact before relying on deterministic Cluster Detail next checks."
    ),
    _PLANNER_STATUS_ENRICHMENT_SUCCESS_NO_CHECKS: (
        "Review deterministic Cluster Detail next-checks since enrichment returned no planner candidates."
    ),
    _PLANNER_STATUS_PLANNER_MISSING: (
        "The planner artifact is missing despite enrichment success; inspect the enrichment artifact and deterministic evidence chain."
    ),
    _PLANNER_STATUS_PLANNER_PRESENT: (
        "Inspect the planner artifact for candidate context before taking any next-check action."
    ),
}


_NEXT_CHECK_QUEUE_EXPLANATION_HINTS: dict[str, str] = {
    "planner-present-with-candidates": (
        "Planner candidates are available; clear queue filters or focus on a cluster to surface them."
    ),
    "queue-exhausted-by-completion-or-filtering": (
        "All planner candidates were completed or filtered out; check deterministic evidence for remaining work."
    ),
    "enrichment-succeeded-without-next-checks": (
        "Review deterministic Cluster Detail next-checks since enrichment returned no planner candidates."
    ),
    "enrichment-failed": (
        "Inspect the failed review enrichment artifact before relying on deterministic Cluster Detail next checks."
    ),
    "enrichment-not-attempted": (
        "Inspect Review Enrichment configuration or provider registration to understand why the planner didn't run."
    ),
    "planner-missing-unexpectedly": (
        "The planner artifact is missing despite enrichment success; inspect the enrichment artifact and deterministic evidence chain."
    ),
}


def _build_next_check_planner_availability(
    plan_entry: Mapping[str, object] | None,
    review_entry: Mapping[str, object] | None,
    review_status: Mapping[str, object] | None,
) -> dict[str, object]:
    if plan_entry:
        summary = plan_entry.get("summary")
        reason = str(summary) if summary else "Planner candidates were generated for this run."
        status = _PLANNER_STATUS_PLANNER_PRESENT
    else:
        status = _PLANNER_STATUS_PLANNER_MISSING
        reason = "Planner data is not available for this run."
        if review_entry is None:
            if review_status:
                status_value = str(review_status.get("status") or "").lower()
                if status_value == _PLANNER_STATUS_POLICY_DISABLED:
                    status = _PLANNER_STATUS_POLICY_DISABLED
                    reason = (
                        str(review_status.get("reason"))
                        if review_status.get("reason")
                        else "Review enrichment is disabled in the current configuration."
                    )
                else:
                    status = _PLANNER_STATUS_ENRICHMENT_NOT_ATTEMPTED
                    reason = (
                        str(review_status.get("reason"))
                        if review_status.get("reason")
                        else "Review enrichment was not attempted for this run."
                    )
            else:
                status = _PLANNER_STATUS_ENRICHMENT_NOT_ATTEMPTED
                reason = "Review enrichment was not attempted for this run."
        else:
            entry_status = str(review_entry.get("status") or "").lower()
            if entry_status != "success":
                status = _PLANNER_STATUS_ENRICHMENT_FAILED
                error_summary = review_entry.get("errorSummary")
                reason = "Review enrichment ran but failed."
                if error_summary:
                    reason = f"{reason} {error_summary}"
            else:
                next_checks = review_entry.get("nextChecks")
                has_checks = False
                if isinstance(next_checks, Sequence) and not isinstance(next_checks, (str, bytes, bytearray)):
                    has_checks = bool(next_checks)
                else:
                    has_checks = bool(next_checks)
                if not has_checks:
                    status = _PLANNER_STATUS_ENRICHMENT_SUCCESS_NO_CHECKS
                    reason = "Review enrichment succeeded but returned no nextChecks."
                else:
                    status = _PLANNER_STATUS_PLANNER_MISSING
                    summary_value = review_entry.get("summary")
                    reason = (
                        str(summary_value)
                        if summary_value is not None
                        else "Review enrichment returned next checks, but the planner artifact is missing."
                    )
    hint = None
    if status != _PLANNER_STATUS_PLANNER_PRESENT:
        hint = _PLANNER_HINT_TEXT
    artifact_path = None
    if status == _PLANNER_STATUS_PLANNER_PRESENT and plan_entry:
        candidate = plan_entry.get("artifactPath")
        if isinstance(candidate, str) and candidate:
            artifact_path = candidate
    elif review_entry:
        for key in _PLANNER_ARTIFACT_KEYS:
            value = review_entry.get(key)
            if isinstance(value, str) and value:
                artifact_path = value
                break
    next_action_hint = _PLANNER_NEXT_ACTION_HINTS.get(status)
    return {
        "status": status,
        "reason": reason,
        "hint": hint,
        "artifactPath": artifact_path,
        "nextActionHint": next_action_hint,
    }


def _pluck_plan_candidates(plan_entry: Mapping[str, object] | None) -> list[Mapping[str, object]]:
    if not isinstance(plan_entry, Mapping):
        return []
    raw = plan_entry.get("candidates")
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        return [entry for entry in raw if isinstance(entry, Mapping)]
    return []


def _summarize_deterministic_checks(
    deterministic_next_checks: Mapping[str, object] | None,
    clusters: Sequence[dict[str, object]],
    drilldown_availability: dict[str, object],
) -> dict[str, object]:
    deterministic_total = 0
    deterministic_clusters = 0
    if isinstance(deterministic_next_checks, Mapping):
        deterministic_total = _coerce_int_value(
            deterministic_next_checks.get("totalNextCheckCount")
        )
        deterministic_clusters = _coerce_int_value(
            deterministic_next_checks.get("clusterCount")
        )
    degraded_labels = [
        str(cluster.get("label"))
        for cluster in clusters
        if str(cluster.get("health_rating") or "").lower() == "degraded"
    ]
    drilldown_ready = _coerce_int_value(drilldown_availability.get("available", 0))
    return {
        "degradedClusterCount": len(degraded_labels),
        "degradedClusterLabels": degraded_labels,
        "deterministicNextCheckCount": deterministic_total,
        "deterministicClusterCount": deterministic_clusters,
        "drilldownReadyCount": drilldown_ready,
    }


def _summarize_next_evidence_entries(
    artifact: HealthAssessmentArtifact,
) -> list[dict[str, object]]:
    payload = artifact.assessment if isinstance(artifact.assessment, Mapping) else {}
    raw_next_checks = payload.get("next_evidence_to_collect")
    if not isinstance(raw_next_checks, Sequence) or isinstance(raw_next_checks, (str, bytes, bytearray)):
        return []
    summaries: list[dict[str, object]] = []
    for entry in raw_next_checks:
        if not isinstance(entry, Mapping):
            continue
        description = str(entry.get("description") or "").strip()
        owner = str(entry.get("owner") or "platform")
        method = str(entry.get("method") or "").strip()
        evidence_raw = entry.get("evidence_needed")
        if isinstance(evidence_raw, Sequence) and not isinstance(evidence_raw, (str, bytes, bytearray)):
            evidence = [str(item) for item in evidence_raw if item is not None]
        else:
            evidence = []
        summaries.append(
            {
                "description": description or "Next evidence",
                "owner": owner,
                "method": method,
                "evidenceNeeded": evidence,
            }
        )
    return summaries


def _derive_deterministic_context(drilldown: DrilldownArtifact | None) -> dict[str, str | None]:
    if drilldown is None:
        return {"namespace": None, "workload": None}
    workload_namespace: str | None = None
    workload_text: str | None = None
    for entry in drilldown.affected_workloads:
        name = str(entry.get("name") or "").strip()
        kind = str(entry.get("kind") or "").strip()
        namespace = str(entry.get("namespace") or "").strip()
        display = ""
        if kind and name:
            display = f"{kind}/{name}"
        elif name:
            display = name
        elif kind:
            display = kind
        if display:
            if namespace:
                display = f"{display} in {namespace}"
            workload_text = display
            workload_namespace = namespace or workload_namespace
            break
        if namespace and not workload_namespace:
            workload_namespace = namespace
    if not workload_text:
        for ns in drilldown.affected_namespaces:
            if ns:
                workload_namespace = workload_namespace or ns
                break
    if not workload_namespace:
        for event in drilldown.warning_events:
            if event.namespace:
                workload_namespace = workload_namespace or event.namespace
                break
    return {"namespace": workload_namespace, "workload": workload_text}


def _rewrite_deterministic_next_check_description(
    summary: dict[str, object],
    cluster_label: str | None,
    cluster_context: str | None,
    top_problem: str | None,
    context: dict[str, str | None],
) -> None:
    description = str(summary.get("description") or "").strip()
    normalized = description.lower()
    cluster_name = cluster_label or cluster_context or "the cluster"
    namespace = context.get("namespace")
    workload = context.get("workload")
    if normalized == "review node, pod, and control plane status before taking action." or (
        "node" in normalized and "control plane" in normalized and "review" in normalized
    ):
        prefix = f"Review {cluster_name}'s node, pod, and control plane status"
        if workload:
            prefix += f" around {workload}"
        elif namespace:
            prefix += f" in {namespace}"
        if top_problem:
            prefix += f" for {top_problem}"
        summary["description"] = f"{prefix} before taking action."
        summary["_generic_template"] = "status_review"
        return
    if normalized == "investigate the flagged nodes, pods, jobs, and warning events." or "flagged nodes" in normalized:
        prefix = f"Investigate flagged nodes, pods, jobs, and warning events on {cluster_name}"
        if workload:
            prefix += f" targeting {workload}"
        elif namespace:
            prefix += f" in {namespace}"
        if top_problem:
            prefix += f" tied to {top_problem}"
        summary["description"] = f"{prefix}."
        summary["_generic_template"] = "flagged_investigation"


def _mentions_top_problem(description: str | None, top_problem: str | None) -> bool:
    if not top_problem or not description:
        return False
    top_tokens = _tokenize_text(top_problem)
    desc_tokens = _tokenize_text(description)
    return bool(top_tokens and any(token in desc_tokens for token in top_tokens))


_WORKSTREAM_BASE_SCORES = {
    "incident": 60,
    "evidence": 40,
    "drift": 20,
}


def _score_deterministic_next_check(
    summary: dict[str, object],
    top_problem: str | None,
    context: dict[str, str | None],
) -> None:
    generic_template = summary.pop("_generic_template", None)
    workstream = str(summary.get("workstream") or "evidence")
    urgency = str(summary.get("urgency") or "").lower()
    score = _WORKSTREAM_BASE_SCORES.get(workstream, 30)
    if summary.get("isPrimaryTriage"):
        score += 20
    if urgency == "high":
        score += 10
    elif urgency == "medium":
        score += 5
    if _mentions_top_problem(str(summary.get("description")), top_problem):
        score += 8
    workload = context.get("workload")
    namespace = context.get("namespace")
    if workload:
        score += 10
    elif namespace:
        score += 5
    if generic_template == "status_review":
        score -= 15
    elif generic_template == "flagged_investigation":
        score -= 10
    summary["priorityScore"] = max(score, 0)


def _derive_deterministic_top_problem(
    cluster: dict[str, object],
    drilldown: DrilldownArtifact | None,
) -> str | None:
    if drilldown and drilldown.trigger_reasons:
        return drilldown.trigger_reasons[0]
    reason = cluster.get("top_trigger_reason")
    if isinstance(reason, str) and reason.strip():
        return reason.strip()
    return None


_DETERMINISTIC_INCIDENT_KEYWORDS = {
    "pod",
    "pods",
    "container",
    "containers",
    "deployment",
    "deployments",
    "statefulset",
    "statefulsets",
    "daemonset",
    "service",
    "services",
    "restart",
    "crashloop",
    "oom",
    "oomkill",
    "failure",
    "fail",
    "error",
    "timeout",
    "latency",
    "packet",
    "connection",
    "drop",
    "tcpdump",
    "traffic",
    "unhealthy",
    "evict",
    "kubelet",
}

_DETERMINISTIC_DRIFT_KEYWORDS = {
    "baseline",
    "drift",
    "parity",
    "version",
    "channel",
    "crd",
    "helm",
    "release",
    "image",
    "policy",
    "configuration",
    "config",
    "upgrade",
    "sync",
}

_DETERMINISTIC_DRIFT_REASON_LABELS = (
    ("baseline", "Baseline drift"),
    ("parity", "Baseline parity"),
    ("version", "Version parity"),
    ("channel", "Channel parity"),
    ("crd", "CRD parity"),
    ("helm", "Helm release parity"),
    ("release", "Release parity"),
    ("image", "Image parity"),
    ("policy", "Policy parity"),
)

_DETERMINISTIC_INCIDENT_METHODS = ("kubectl exec", "kubectl rollout", "rollout status")


def _tokenize_text(value: str | None) -> set[str]:
    if not value:
        return set()
    return {part for part in re.split(r"[^a-z0-9]+", value.lower()) if part}


def _collect_evidence_tokens(evidence: Sequence[str] | None) -> set[str]:
    tokens: set[str] = set()
    if not evidence:
        return tokens
    for item in evidence:
        if item:
            tokens.update(_tokenize_text(str(item)))
    return tokens


def _token_variants(value: str) -> set[str]:
    normalized = {value}
    if value.endswith("s") and len(value) > 1:
        normalized.add(value[:-1])
    elif not value.endswith("s"):
        normalized.add(f"{value}s")
    return normalized


def _classify_deterministic_next_check(
    summary: Mapping[str, object], top_problem: str | None
) -> dict[str, object]:
    description = str(summary.get("description") or "").lower()
    method = str(summary.get("method") or "").lower()
    evidence_raw = summary.get("evidenceNeeded")
    if isinstance(evidence_raw, Sequence) and not isinstance(evidence_raw, (str, bytes, bytearray)):
        evidence = [str(item) for item in evidence_raw if item is not None]
    else:
        evidence = []
    desc_tokens = _tokenize_text(description)
    method_tokens = _tokenize_text(method)
    evidence_tokens = _collect_evidence_tokens(evidence)
    all_tokens = desc_tokens | method_tokens | evidence_tokens
    top_problem_tokens = _tokenize_text(top_problem)

    def _matches_top_problem() -> bool:
        if not top_problem_tokens:
            return False
        for token in top_problem_tokens:
            if token and any(variant in all_tokens for variant in _token_variants(token)):
                return True
        return False

    def _method_immediate() -> bool:
        for command in _DETERMINISTIC_INCIDENT_METHODS:
            if command in method:
                return True
        return False

    def _method_log_or_describe() -> bool:
        return "describe" in method or "log" in method or "logs" in method

    incident_tokens_match = bool(all_tokens & _DETERMINISTIC_INCIDENT_KEYWORDS)
    if _matches_top_problem() or _method_immediate() or (_method_log_or_describe() and incident_tokens_match):
        summary_reason = (
            f"Immediate triage for {top_problem}" if top_problem else "Immediate triage for degraded cluster"
        )
        return {
            "workstream": "incident",
            "urgency": "high",
            "isPrimaryTriage": True,
            "whyNow": summary_reason,
        }

    drift_tokens_match = bool(all_tokens & _DETERMINISTIC_DRIFT_KEYWORDS)
    if drift_tokens_match:
        drift_reason = next(
            (label for term, label in _DETERMINISTIC_DRIFT_REASON_LABELS if term in all_tokens),
            None,
        )
        if drift_reason:
            why_now = f"{drift_reason} follow-up"
        else:
            why_now = "Drift / toil follow-up"
        return {
            "workstream": "drift",
            "urgency": "low",
            "isPrimaryTriage": False,
            "whyNow": why_now,
        }

    evidence_reason = (
        f"Gather additional evidence for {top_problem}" if top_problem else "Gather additional evidence"
    )
    return {
        "workstream": "evidence",
        "urgency": "medium",
        "isPrimaryTriage": False,
        "whyNow": evidence_reason,
    }


def _build_deterministic_next_checks_projection(
    clusters: Sequence[dict[str, object]],
    assessment_map: Mapping[str, HealthAssessmentArtifact | None],
    drilldown_map: Mapping[str, DrilldownArtifact],
    root_dir: Path,
) -> dict[str, object]:
    entries: list[dict[str, object]] = []
    total_next_checks = 0
    degraded_labels = [
        str(cluster.get("label"))
        for cluster in clusters
        if str(cluster.get("health_rating") or "").lower() == "degraded"
    ]
    for cluster in clusters:
        rating = str(cluster.get("health_rating") or "").lower()
        if rating != "degraded":
            continue
        label = str(cluster.get("label") or "")
        if not label:
            continue
        assessment = assessment_map.get(label)
        if not assessment:
            continue
        summaries = _summarize_next_evidence_entries(assessment)
        if not summaries:
            continue
        drilldown = drilldown_map.get(label)
        top_problem = _derive_deterministic_top_problem(cluster, drilldown)
        context = _derive_deterministic_context(drilldown)
        for summary in summaries:
            _rewrite_deterministic_next_check_description(
                summary,
                label,
                str(cluster.get("context") or ""),
                top_problem,
                context,
            )
        # annotate classification metadata for each predicted check
        for s in summaries:
            s.update(_classify_deterministic_next_check(s, top_problem))
            _score_deterministic_next_check(s, top_problem, context)
        def _priority_sort_key(entry: dict[str, object]) -> tuple[int, str]:
            raw_score = entry.get("priorityScore")
            magnitude = 0
            if isinstance(raw_score, (int, float)):
                magnitude = int(raw_score)
            description = str(entry.get("description") or "")
            return (-magnitude, description)

        summaries.sort(key=_priority_sort_key)
        total_next_checks += len(summaries)
        entries.append(
            {
                "label": label,
                "context": str(cluster.get("context") or ""),
                "topProblem": top_problem,
                "triggerReason": top_problem,
                "deterministicNextCheckCount": len(summaries),
                "deterministicNextCheckSummaries": summaries,
                "drilldownAvailable": bool(drilldown),
                "assessmentArtifactPath": _relative_path(
                    root_dir, assessment.artifact_path
                ),
                "drilldownArtifactPath": _relative_path(
                    root_dir, drilldown.artifact_path if drilldown else None
                ),
            }
        )
    return {
        "clusterCount": len(degraded_labels),
        "totalNextCheckCount": total_next_checks,
        "clusters": entries,
    }


def _build_candidate_accounting(plan_entry: Mapping[str, object] | None) -> dict[str, int]:
    candidates = _pluck_plan_candidates(plan_entry)
    safe = approval_needed = duplicate = completed = stale_orphaned = 0
    approval_needed_states = {"approval-needed"}
    for candidate in candidates:
        status = str(candidate.get("queueStatus") or "").lower()
        if status in ("safe-ready", "approved-ready"):
            safe += 1
        if status in approval_needed_states:
            approval_needed += 1
        if status == "duplicate-or-stale":
            duplicate += 1
        if status == "completed":
            completed += 1
        approval_state = str(candidate.get("approvalState") or "").lower()
        if approval_state in ("approval-stale", "approval-orphaned") or status == "duplicate-or-stale":
            stale_orphaned += 1
    orphaned = plan_entry.get("orphanedApprovalCount") if isinstance(plan_entry, Mapping) else 0
    orphaned_value = _coerce_int_value(orphaned)
    generated = _coerce_int_value(
        plan_entry.get("candidateCount") if isinstance(plan_entry, Mapping) else len(candidates)
    )
    return {
        "generated": generated,
        "safe": safe,
        "approvalNeeded": approval_needed,
        "duplicate": duplicate,
        "completed": completed,
        "staleOrphaned": stale_orphaned,
        "orphanedApprovals": orphaned_value,
    }


def _determine_queue_explanation_status(
    plan_entry: Mapping[str, object] | None,
    review_entry: Mapping[str, object] | None,
    review_status: Mapping[str, object] | None,
) -> str:
    candidates = _pluck_plan_candidates(plan_entry)
    if candidates:
        return "planner-present-with-candidates"
    if plan_entry and not candidates:
        return "queue-exhausted-by-completion-or-filtering"
    if review_entry:
        entry_status = str(review_entry.get("status") or "").lower()
        next_checks = review_entry.get("nextChecks")
        has_checks = (
            isinstance(next_checks, Sequence)
            and not isinstance(next_checks, (str, bytes, bytearray))
            and bool(next_checks)
        )
        if entry_status != "success":
            return "enrichment-failed"
        if has_checks:
            return "planner-missing-unexpectedly"
        return "enrichment-succeeded-without-next-checks"
    if review_status:
        state = str(review_status.get("status") or "").lower()
        if state in (
            "policy-disabled",
            "provider-missing",
            "adapter-unavailable",
            "awaiting-next-run",
        ):
            return "enrichment-not-attempted"
        return "enrichment-not-attempted"
    return "enrichment-not-attempted"


def _collect_queue_explanation_reason(
    plan_entry: Mapping[str, object] | None,
    review_entry: Mapping[str, object] | None,
    review_status: Mapping[str, object] | None,
) -> str | None:
    if plan_entry and isinstance(plan_entry, Mapping):
        summary = plan_entry.get("summary") or plan_entry.get("reason")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
    if review_entry and isinstance(review_entry, Mapping):
        error = review_entry.get("errorSummary")
        if isinstance(error, str) and error.strip():
            return error.strip()
        summary = review_entry.get("reason")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
    if review_status and isinstance(review_status, Mapping):
        reason = review_status.get("reason")
        if isinstance(reason, str) and reason.strip():
            return reason.strip()
    return None


def _derive_queue_artifact_path(
    plan_entry: Mapping[str, object] | None,
    review_entry: Mapping[str, object] | None,
) -> str | None:
    if plan_entry and isinstance(plan_entry, Mapping):
        path = plan_entry.get("artifactPath")
        if isinstance(path, str) and path:
            return path
    if review_entry and isinstance(review_entry, Mapping):
        for key in _PLANNER_ARTIFACT_KEYS:
            value = review_entry.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _build_next_check_queue_explanation(
    clusters: Sequence[dict[str, object]],
    drilldown_availability: dict[str, object],
    plan_entry: Mapping[str, object] | None,
    queue: list[dict[str, object]],
    review_entry: Mapping[str, object] | None,
    review_status: Mapping[str, object] | None,
    deterministic_next_checks: Mapping[str, object] | None,
) -> dict[str, object] | None:
    if queue:
        return None
    status = _determine_queue_explanation_status(plan_entry, review_entry, review_status)
    reason = _collect_queue_explanation_reason(plan_entry, review_entry, review_status)
    cluster_state = _summarize_deterministic_checks(
        deterministic_next_checks, clusters, drilldown_availability
    )
    candidate_accounting = _build_candidate_accounting(plan_entry)
    next_action_hint = _NEXT_CHECK_QUEUE_EXPLANATION_HINTS.get(status)
    recommended_actions: list[str] = []
    if next_action_hint:
        recommended_actions.append(next_action_hint)
    if cluster_state.get("deterministicNextCheckCount"):
        recommended_actions.append(
            "Inspect deterministic Cluster Detail next checks to close the remaining evidence gaps."
        )
    return {
        "status": status,
        "reason": reason,
        "hint": next_action_hint,
        "plannerArtifactPath": _derive_queue_artifact_path(plan_entry, review_entry),
        "clusterState": cluster_state,
        "candidateAccounting": candidate_accounting,
        "deterministicNextChecksAvailable": bool(
            cluster_state.get("deterministicNextCheckCount")
        ),
        "recommendedNextActions": recommended_actions,
    }


def _build_review_enrichment_status(
    settings: ExternalAnalysisSettings | None,
    adapters: Iterable[str] | None,
    has_artifact: bool,
    run_config: Mapping[str, object] | None,
) -> dict[str, object] | None:
    policy = (settings or ExternalAnalysisSettings()).review_enrichment
    provider_raw = policy.provider or ""
    provider = provider_raw.strip()
    provider_name = provider or None
    if has_artifact:
        return None
    adapter_available = _adapter_registered(provider, adapters) if provider else None
    status = "unknown"
    reason: str | None = None
    run_enabled: bool | None = None
    run_provider: str | None = None
    if isinstance(run_config, Mapping):
        if "enabled" in run_config:
            run_enabled = bool(run_config.get("enabled"))
        value = run_config.get("provider")
        run_provider_raw = str(value).strip() if value else ""
        run_provider = run_provider_raw or None
    if not policy.enabled:
        status = "policy-disabled"
        reason = "Review enrichment is disabled in the current configuration."
    elif not provider:
        status = "provider-missing"
        reason = "No provider is configured for review enrichment."
    elif adapter_available is False:
        status = "adapter-unavailable"
        reason = f"Adapter '{provider}' is not registered for review enrichment."
    elif not run_config or "enabled" not in run_config or "provider" not in run_config:
        status = "unknown"
        reason = reason or "Review enrichment metadata is incomplete for this run."
    elif run_enabled is False or not run_provider:
        status = "awaiting-next-run"
        if run_provider:
            reason = (
                "Review enrichment is enabled now, but the latest run was produced before "
                f"'{run_provider}' was active."
            )
        else:
            reason = "Review enrichment is enabled now, but the latest run predates this setting."
    else:
        status = "not-attempted"
        if run_provider:
            reason = (
                f"Review enrichment was enabled for '{run_provider}' in this run, "
                "but no artifact was recorded."
            )
        else:
            reason = "Review enrichment was enabled for this run, but no artifact was recorded."
    return {
        "status": status,
        "reason": reason,
        "provider": provider_name,
        "policyEnabled": policy.enabled,
        "providerConfigured": bool(provider),
        "adapterAvailable": adapter_available,
        "runEnabled": run_enabled,
        "runProvider": run_provider,
    }


def _adapter_registered(provider: str, adapters: Iterable[str] | None) -> bool | None:
    if not adapters:
        return None
    normalized = provider.lower()
    for adapter in adapters:
        if adapter and adapter.lower() == normalized:
            return True
    return False


def _build_llm_policy(
    settings: ExternalAnalysisSettings | None,
    artifacts: Sequence[ExternalAnalysisArtifact],
    drilldown_count: int,
) -> dict[str, object]:
    config = settings or ExternalAnalysisSettings()
    policy = config.auto_drilldown
    auto_artifacts = [
        artifact
        for artifact in artifacts
        if artifact.purpose == ExternalAnalysisPurpose.AUTO_DRILLDOWN
    ]
    used_statuses = {ExternalAnalysisStatus.SUCCESS, ExternalAnalysisStatus.FAILED}
    used_calls = sum(1 for artifact in auto_artifacts if artifact.status in used_statuses)
    successful_calls = sum(1 for artifact in auto_artifacts if artifact.status == ExternalAnalysisStatus.SUCCESS)
    failed_calls = sum(1 for artifact in auto_artifacts if artifact.status == ExternalAnalysisStatus.FAILED)
    skipped_calls = sum(1 for artifact in auto_artifacts if artifact.status == ExternalAnalysisStatus.SKIPPED)
    budget_exhausted: bool | None = None
    if policy.enabled and policy.max_per_run > 0:
        if len(auto_artifacts) >= policy.max_per_run and drilldown_count > len(auto_artifacts):
            budget_exhausted = True
        elif drilldown_count <= len(auto_artifacts):
            budget_exhausted = False
    return {
        "auto_drilldown": {
            "enabled": policy.enabled,
            "provider": policy.provider or "default",
            "maxPerRun": policy.max_per_run,
            "usedThisRun": used_calls,
            "successfulThisRun": successful_calls,
            "failedThisRun": failed_calls,
            "skippedThisRun": skipped_calls,
            "budgetExhausted": budget_exhausted,
        }
    }


def _build_provider_execution(
    settings: ExternalAnalysisSettings | None,
    artifacts: Sequence[ExternalAnalysisArtifact],
    drilldowns: Sequence[DrilldownArtifact],
    review_config: Mapping[str, object] | None,
) -> dict[str, object]:
    config = settings or ExternalAnalysisSettings()
    auto_policy = config.auto_drilldown
    return {
        "auto_drilldown": _build_auto_drilldown_execution(
            auto_policy, artifacts, len(drilldowns)
        ),
        "review_enrichment": _build_review_enrichment_execution(
            artifacts, review_config
        ),
    }


def _execution_counts_for_purpose(
    artifacts: Sequence[ExternalAnalysisArtifact],
    purpose: ExternalAnalysisPurpose,
) -> tuple[int, int, int]:
    success = 0
    failed = 0
    skipped = 0
    for artifact in artifacts:
        if artifact.purpose != purpose:
            continue
        status = artifact.status
        if status == ExternalAnalysisStatus.SUCCESS:
            success += 1
        elif status == ExternalAnalysisStatus.FAILED:
            failed += 1
        elif status == ExternalAnalysisStatus.SKIPPED:
            skipped += 1
    return success, failed, skipped


def _build_auto_drilldown_execution(
    policy: AutoDrilldownPolicy,
    artifacts: Sequence[ExternalAnalysisArtifact],
    eligible_count: int,
) -> dict[str, object]:
    succeeded, failed, skipped = _execution_counts_for_purpose(
        artifacts, ExternalAnalysisPurpose.AUTO_DRILLDOWN
    )
    attempted = succeeded + failed + skipped
    eligible: int | None = eligible_count if policy.enabled else None
    unattempted: int | None = None
    if eligible is not None and eligible > attempted:
        unattempted = eligible - attempted
    budget_limited: int | None = None
    if (
        eligible is not None
        and policy.max_per_run > 0
        and attempted >= policy.max_per_run
        and eligible > attempted
    ):
        budget_limited = eligible - attempted
    notes_parts: list[str] = []
    if budget_limited:
        notes_parts.append(
            f"Reached max per run ({policy.max_per_run}) before processing {budget_limited} eligible drilldown(s)."
        )
    elif unattempted:
        notes_parts.append(
            f"{unattempted} eligible drilldown(s) were not processed by the provider log."  # noqa: E501
        )
    notes = " ".join(notes_parts) if notes_parts else None
    return {
        "enabled": policy.enabled,
        "provider": policy.provider or "default",
        "maxPerRun": policy.max_per_run,
        "eligible": eligible,
        "attempted": attempted,
        "succeeded": succeeded,
        "failed": failed,
        "skipped": skipped,
        "unattempted": unattempted,
        "budgetLimited": budget_limited,
        "notes": notes,
    }


def _extract_review_run_config(run_config: Mapping[str, object] | None) -> tuple[bool | None, str | None]:
    run_enabled: bool | None = None
    run_provider: str | None = None
    if isinstance(run_config, Mapping):
        if "enabled" in run_config:
            run_enabled = bool(run_config.get("enabled"))
        if "provider" in run_config:
            provider_raw = str(run_config.get("provider") or "").strip()
            run_provider = provider_raw or None
    return run_enabled, run_provider


def _build_review_enrichment_execution(
    artifacts: Sequence[ExternalAnalysisArtifact],
    run_config: Mapping[str, object] | None,
) -> dict[str, object]:
    succeeded, failed, skipped = _execution_counts_for_purpose(
        artifacts, ExternalAnalysisPurpose.REVIEW_ENRICHMENT
    )
    attempted = succeeded + failed + skipped
    run_enabled, run_provider = _extract_review_run_config(run_config)
    if run_enabled is None:
        eligible: int | None = None
    elif not run_enabled:
        eligible = 0
    elif run_provider:
        eligible = 1
    else:
        eligible = 0
    unattempted: int | None = None
    if eligible is not None and eligible > attempted:
        unattempted = eligible - attempted
    notes = None
    if unattempted and run_provider:
        notes = (
            f"Run configuration enabled review enrichment for '{run_provider}', but no artifact was recorded."
        )
    elif unattempted:
        notes = "Run configuration enabled review enrichment, but no artifact was recorded."
    return {
        "enabled": run_enabled,
        "eligible": eligible,
        "attempted": attempted,
        "succeeded": succeeded,
        "failed": failed,
        "skipped": skipped,
        "unattempted": unattempted,
        "budgetLimited": None,
        "notes": notes,
    }


# UTC-aware sentinel for sorting (datetime.min is naive, cannot compare with aware datetimes)
_EPOCH_SENTINEL = datetime.min.replace(tzinfo=UTC)


def _serialize_llm_activity(entries: Sequence[Mapping[str, object]], root_dir: Path, limit: int = _LLM_ACTIVITY_LIMIT) -> dict[str, object]:
    normalized: list[tuple[datetime | None, dict[str, object]]] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        timestamp_value = entry.get("timestamp")
        timestamp = _parse_timestamp(timestamp_value)
        if isinstance(timestamp_value, str):
            timestamp_str = timestamp_value
        elif timestamp:
            timestamp_str = timestamp.isoformat()
        else:
            timestamp_str = None
        activity_entry: dict[str, object] = {
            "timestamp": timestamp_str,
            "run_id": _coerce_optional_str(entry.get("run_id")),
            "run_label": _coerce_optional_str(entry.get("run_label")),
            "cluster_label": _coerce_optional_str(entry.get("cluster_label")),
            "tool_name": _coerce_optional_str(entry.get("tool_name")),
            "provider": _coerce_optional_str(entry.get("provider")),
            "purpose": _coerce_optional_str(entry.get("purpose")),
            "status": _coerce_optional_str(entry.get("status")),
            "latency_ms": _parse_optional_int(entry.get("duration_ms")),
            "artifact_path": _relative_path(root_dir, entry.get("artifact_path")),
            "summary": _coerce_optional_str(entry.get("summary")),
            "error_summary": _coerce_optional_str(entry.get("error_summary")),
            "skip_reason": _coerce_optional_str(entry.get("skip_reason")),
        }
        normalized.append((timestamp, activity_entry))
    sorted_entries = sorted(
        normalized,
        key=lambda item: item[0] or _EPOCH_SENTINEL,
        reverse=True,
    )
    trimmed_entries = [payload for _, payload in sorted_entries[:limit]]
    return {
        "entries": trimmed_entries,
        "summary": {"retained_entries": len(normalized)},
    }


def _serialize_auto_drilldown_interpretations(
    artifacts: object | None, root_dir: Path
) -> dict[str, dict[str, object]]:
    interpretations: dict[str, dict[str, object]] = {}
    if not isinstance(artifacts, Sequence):
        return interpretations
    seen: set[str] = set()
    for entry in artifacts:
        if not isinstance(entry, Mapping):
            continue
        if entry.get("purpose") != ExternalAnalysisPurpose.AUTO_DRILLDOWN.value:
            continue
        cluster_label = str(entry.get("cluster_label") or "").strip()
        if not cluster_label or cluster_label in seen:
            continue
        seen.add(cluster_label)
        interpretations[cluster_label] = {
            "adapter": str(entry.get("tool_name") or ""),
            "status": str(entry.get("status") or ""),
            "summary": entry.get("summary"),
            "timestamp": str(entry.get("timestamp") or ""),
            "artifact_path": _relative_path(root_dir, entry.get("artifact_path")),
            "provider": entry.get("provider"),
            "duration_ms": entry.get("duration_ms"),
            "payload": entry.get("payload"),
            "error_summary": entry.get("error_summary"),
            "skip_reason": entry.get("skip_reason"),
        }
    return interpretations


def _parse_optional_int(value: object | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int,)):  # keep ints as is
        return int(value)
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _coerce_sequence(value: object | None) -> tuple[str, ...]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return tuple(str(item) for item in value)
    if value is None:
        return ()
    return (str(value),)


def _parse_timestamp(value: object | None) -> datetime | None:
    """Parse an ISO timestamp string to timezone-aware UTC datetime.

    Uses centralized datetime_utils to ensure all parsed datetimes
    are timezone-aware UTC for safe comparison operations.
    """
    return parse_iso_to_utc(value)


def _coerce_optional_str(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _build_llm_stats(external_analysis: dict[str, object], scope: str = _SCOPE_CURRENT_RUN) -> dict[str, object]:
    artifacts = external_analysis.get("artifacts") or ()
    if not isinstance(artifacts, Sequence):
        artifacts = ()
    filtered = [
        entry
        for entry in artifacts
        if isinstance(entry, Mapping)
        and entry.get("purpose") != ExternalAnalysisPurpose.NEXT_CHECK_PLANNING.value
    ]
    return _compute_llm_stats(filtered, scope)


def _build_historical_llm_stats(
    external_analysis_dir: Path,
    entries: Sequence[Mapping[str, object]] | None = None,
) -> dict[str, object]:
    historical_entries = entries or _collect_historical_external_analysis_entries(external_analysis_dir)
    return _compute_llm_stats(historical_entries, _SCOPE_RETAINED_HISTORY)


def _collect_historical_external_analysis_entries(
    directory: Path,
) -> list[Mapping[str, object]]:
    entries: list[Mapping[str, object]] = []
    if not directory.is_dir():
        return entries
    for path in sorted(directory.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(raw, Mapping):
            entries.append(raw)
    return entries


def _compute_llm_stats(entries: Sequence[object], scope: str) -> dict[str, object]:
    total_calls = 0
    successful_calls = 0
    failed_calls = 0
    durations: list[int] = []
    latest_timestamp: datetime | None = None
    latest_timestamp_str: str | None = None
    provider_counts: dict[str, dict[str, int]] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        status = str(entry.get("status") or "").lower()
        if status not in ("success", "failed"):
            continue
        total_calls += 1
        if status == "success":
            successful_calls += 1
        if status == "failed":
            failed_calls += 1
        raw_timestamp = entry.get("timestamp")
        timestamp = _parse_timestamp(raw_timestamp)
        if timestamp:
            if latest_timestamp is None or timestamp > latest_timestamp:
                latest_timestamp = timestamp
                latest_timestamp_str = raw_timestamp if isinstance(raw_timestamp, str) else latest_timestamp_str
        duration = _parse_optional_int(entry.get("duration_ms"))
        if duration is not None:
            durations.append(duration)
        provider = str(entry.get("tool_name") or "unknown")
        counter = provider_counts.setdefault(provider, {"calls": 0, "failedCalls": 0})
        counter["calls"] += 1
        if status == "failed":
            counter["failedCalls"] += 1
    percentile_values: dict[str, int | None] = {
        "p50": None,
        "p95": None,
        "p99": None,
    }
    if durations:
        float_durations = [float(value) for value in durations]
        float_durations.sort()
        percentile_values["p50"] = _percentile_value(float_durations, 50)
        percentile_values["p95"] = _percentile_value(float_durations, 95)
        percentile_values["p99"] = _percentile_value(float_durations, 99)
    provider_breakdown = [
        {"provider": provider, "calls": data["calls"], "failedCalls": data["failedCalls"]}
        for provider, data in sorted(provider_counts.items())
    ]
    return {
        "totalCalls": total_calls,
        "successfulCalls": successful_calls,
        "failedCalls": failed_calls,
        "lastCallTimestamp": latest_timestamp_str,
        "p50LatencyMs": percentile_values["p50"],
        "p95LatencyMs": percentile_values["p95"],
        "p99LatencyMs": percentile_values["p99"],
        "providerBreakdown": provider_breakdown,
        "scope": scope,
    }


def _serialize_notification_history(
    records: Sequence[NotificationRecord],
    root_dir: Path,
    limit: int = _NOTIFICATION_HISTORY_LIMIT,
) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    sorted_records = sorted(records, key=lambda item: item[0].timestamp, reverse=True)
    for artifact, path in sorted_records[:limit]:
        detail_entries = [
            {"label": str(key), "value": _stringify_notification_value(value)}
            for key, value in sorted(artifact.details.items())
        ]
        entry: dict[str, object] = {
            "kind": artifact.kind,
            "summary": artifact.summary,
            "timestamp": artifact.timestamp,
            "run_id": artifact.run_id,
            "cluster_label": artifact.cluster_label,
            "context": artifact.context,
            "details": detail_entries,
            "artifact_path": _relative_path(root_dir, path),
        }
        # Thread artifact_id for provenance/debugging surfaces (optional)
        if artifact.artifact_id:
            entry["artifact_id"] = artifact.artifact_id
        entries.append(entry)
    return entries


def _stringify_notification_value(value: object | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)


def _serialize_latest_assessment(
    assessments: Sequence[HealthAssessmentArtifact],
    root_dir: Path,
) -> dict[str, object] | None:
    if not assessments:
        return None
    latest = max(assessments, key=lambda artifact: artifact.timestamp)
    return _serialize_assessment(latest, root_dir)


_RUN_ID_TIMESTAMP_PATTERN = re.compile(r"(\d{8}T\d{6}Z)$")


def _build_run_stats(reviews_dir: Path) -> dict[str, object]:
    review_timestamps = _collect_review_timestamps(reviews_dir)
    total_runs = len(review_timestamps)
    measured: list[tuple[datetime, float]] = []
    durations: list[float] = []
    for run_id, finish in review_timestamps.items():
        start = _parse_run_start(run_id)
        if start is None:
            continue
        duration = (finish - start).total_seconds()
        if duration <= 0:
            continue
        measured.append((finish, duration))
        durations.append(duration)
    last_run_duration_seconds: int | None = None
    if measured:
        latest_entry = max(measured, key=lambda entry: entry[0])
        last_run_duration_seconds = int(latest_entry[1])
    percentile_values: dict[str, int | None] = {
        "p50": None,
        "p95": None,
        "p99": None,
    }
    if len(durations) >= 5:
        durations.sort()
        percentile_values["p50"] = _percentile_value(durations, 50)
        percentile_values["p95"] = _percentile_value(durations, 95)
        percentile_values["p99"] = _percentile_value(durations, 99)
    return {
        "last_run_duration_seconds": last_run_duration_seconds,
        "total_runs": total_runs,
        "p50_run_duration_seconds": percentile_values["p50"],
        "p95_run_duration_seconds": percentile_values["p95"],
        "p99_run_duration_seconds": percentile_values["p99"],
    }


def _collect_review_timestamps(reviews_dir: Path) -> dict[str, datetime]:
    timestamps: dict[str, datetime] = {}
    if not reviews_dir.is_dir():
        return timestamps
    for path in reviews_dir.glob("*-review.json"):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        run_id = raw.get("run_id")
        timestamp = raw.get("timestamp")
        if not isinstance(run_id, str) or not isinstance(timestamp, str):
            continue
        finish = parse_iso_to_utc(timestamp)
        if finish is None:
            continue
        existing = timestamps.get(run_id)
        if existing is None or finish > existing:
            timestamps[run_id] = finish
    return timestamps


def _parse_run_start(run_id: str) -> datetime | None:
    match = _RUN_ID_TIMESTAMP_PATTERN.search(run_id or "")
    if not match:
        return None
    try:
        parsed = datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ")
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC)


def _percentile_value(values: list[float], percentile: float) -> int:
    if not values:
        return 0
    idx = math.ceil((percentile / 100) * len(values)) - 1
    idx = max(0, min(idx, len(values) - 1))
    return int(values[idx])


def _serialize_assessment(artifact: HealthAssessmentArtifact, root_dir: Path) -> dict[str, object]:
    data: dict[str, object] = dict(artifact.assessment or {})
    data.update(
        {
            "cluster_label": artifact.label,
            "context": artifact.context,
            "timestamp": artifact.timestamp.isoformat(),
            "health_rating": artifact.health_rating.value,
            "missing_evidence": list(artifact.missing_evidence),
            "artifact_path": _relative_path(root_dir, artifact.artifact_path),
            "snapshot_path": _relative_path(root_dir, artifact.snapshot_path),
        }
    )
    return data


def _serialize_alertmanager_compact(output_dir: Path, run_id: str) -> dict[str, object] | None:
    """Read and serialize Alertmanager compact artifact for UI.
    
    Returns None if the artifact is not available or cannot be read.
    """
    compact = read_alertmanager_compact(output_dir / f"{run_id}-alertmanager-compact.json")
    if compact is None:
        return None
    
    # Build by_cluster summaries
    by_cluster: list[dict[str, Any]] = []
    for summary in compact.by_cluster:
        by_cluster.append({
            "cluster": summary.cluster,
            "alert_count": summary.alert_count,
            "severity_counts": {str(k): v for k, v in summary.severity_counts},
            "state_counts": {str(k): v for k, v in summary.state_counts},
            "top_alert_names": list(summary.top_alert_names),
            "affected_namespaces": list(summary.affected_namespaces),
            "affected_services": list(summary.affected_services),
        })
    
    return {
        "status": compact.status,
        "alert_count": compact.alert_count,
        "severity_counts": {str(k): v for k, v in compact.severity_counts},
        "state_counts": {str(k): v for k, v in compact.state_counts},
        "top_alert_names": list(compact.top_alert_names),
        "affected_namespaces": list(compact.affected_namespaces),
        "affected_clusters": list(compact.affected_clusters),
        "affected_services": list(compact.affected_services),
        "truncated": compact.truncated,
        "captured_at": compact.captured_at,
        "by_cluster": by_cluster,
    }


def _serialize_alertmanager_sources(output_dir: Path, run_id: str) -> dict[str, object] | None:
    """Read and serialize Alertmanager sources inventory artifact for UI.
    
    This function applies operator overrides (promote/disable) to the source
    inventory before serialization. It reads both run-scoped overrides AND the
    durable cross-run registry to ensure promoted sources persist across runs.
    
    UI-derived fields (is_manual, is_tracking, can_disable, can_promote,
    display_origin, display_state, provenance_summary, and aggregate counts)
    are computed by _build_alertmanager_sources_view() in ui/model.py.
    
    Returns None if the artifact is not available or cannot be read.
    """
    inventory = read_alertmanager_sources(output_dir / f"{run_id}-alertmanager-sources.json")
    if inventory is None:
        return None
    
    # Load operator overrides and compute effective states (run-scoped)
    overrides_path = output_dir / f"{run_id}-alertmanager-source-overrides.json"
    overrides = read_source_overrides(overrides_path)
    effective_states: dict[str, str] = {}
    if overrides:
        effective_states = merge_source_overrides(overrides)
    
    # Load the durable cross-run registry for promoted/disabled sources
    # This ensures operator actions persist across runs
    from ..external_analysis.alertmanager_source_registry import (
        RegistryDesiredState,
        read_source_registry,
    )
    registry = read_source_registry(output_dir)
    
    sources = []
    for source in inventory.sources.values():
        source_id = source.source_id
        cluster_context = source.cluster_context or "unknown"
        
        # Apply run-scoped override effective state if present
        effective_state = effective_states.get(source_id)
        
        # Track whether this source was promoted via registry (not just effective_state)
        # Registry entries are keyed by the canonical key (preferring cluster_label over cluster_context)
        # See: build_canonical_registry_key() in alertmanager_source_registry.py
        promoted_via_registry = False
        if registry:
            from ..external_analysis.alertmanager_source_registry import build_canonical_registry_key
            registry_key = build_canonical_registry_key(
                cluster_context=cluster_context,
                cluster_label=source.cluster_label,
                canonical_identity=source.canonical_identity,
            )
            entry = registry.entries.get(registry_key)
            if entry:
                if entry.desired_state == RegistryDesiredState.MANUAL:
                    # Source was promoted by operator - apply promoted state
                    # effective_state takes precedence if set, otherwise use registry state
                    if not effective_state:
                        effective_state = "manual"
                    # Mark as promoted via registry (not run-scoped override)
                    promoted_via_registry = True
                elif entry.desired_state == RegistryDesiredState.DISABLED:
                    # Source was disabled by operator - skip it
                    continue
        
        source_data = {
            "source_id": source_id,
            "endpoint": source.endpoint,
            "namespace": source.namespace,
            "name": source.name,
            "origin": source.origin.value,
            "state": source.state.value,
            "discovered_at": source.discovered_at.isoformat() if source.discovered_at else None,
            "verified_at": source.verified_at.isoformat() if source.verified_at else None,
            "last_check": source.last_check.isoformat() if source.last_check else None,
            "last_error": source.last_error,
            "verified_version": source.verified_version,
            "confidence_hints": list(source.confidence_hints),
            # Include canonical_identity for cross-run registry matching
            # This is the stable identity used by the UI server when writing registry entries
            "canonical_identity": source.canonical_identity,
            # Include cluster_label for per-cluster UI filtering
            # This is the operator-facing cluster label from the discovery context
            "cluster_label": source.cluster_label,
            "cluster_context": source.cluster_context,
        }
        
        # Include manual_source_mode if present (backward compatible)
        # For promoted sources from registry, set manual_source_mode to operator-promoted
        # Only label as promoted if this specific source matched a registry entry
        if source.manual_source_mode.value != "not-manual":
            source_data["manual_source_mode"] = source.manual_source_mode.value
        elif promoted_via_registry:
            # Source was promoted via registry (not run-scoped override)
            # Set manual_source_mode to indicate promoted
            source_data["manual_source_mode"] = "operator-promoted"
        
        # Apply effective state override if present (e.g., "disabled" or "manual")
        if effective_state:
            source_data["effective_state"] = effective_state
        
        sources.append(source_data)
    
    return {
        "sources": sources,
        "total_count": len(sources),
        "discovery_timestamp": inventory.discovered_at.isoformat() if inventory.discovered_at else None,
        "cluster_context": inventory.cluster_context,
        "_has_overrides": bool(overrides),
        "_has_registry": registry is not None and len(registry.entries) > 0,
    }
