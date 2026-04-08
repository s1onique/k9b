"""Utilities that build a compact artifact index for UI consumers."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ..external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisPurpose,
    ExternalAnalysisStatus,
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
    return {
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
    settings = external_analysis_settings or ExternalAnalysisSettings()
    review_config = _serialize_review_enrichment_policy(settings.review_enrichment)
    review_status = _build_review_enrichment_status(
        external_analysis_settings,
        available_adapters,
        bool(review_enrichment_entry),
        review_config,
    )
    auto_config = _serialize_auto_drilldown_policy(settings.auto_drilldown)
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
        "next_check_plan": plan_entry,
        "next_check_execution_history": _build_next_check_execution_history(
            external_analysis, output_dir, run_id
        ),
        "scheduler_interval_seconds": expected_scheduler_interval_seconds,
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
        entries.append(
            {
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
        )
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
    payload = artifact.payload if isinstance(artifact.payload, Mapping) else {}

    def _list_from(*keys: str) -> list[str]:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                return [str(item) for item in value]
            if value is not None:
                return [str(value)]
        return []

    return {
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
    return {
        "status": artifact.status.value,
        "summary": artifact.summary,
        "artifactPath": _relative_path(root_dir, artifact.artifact_path),
        "reviewPath": payload.get("review_path"),
        "enrichmentArtifactPath": payload.get("enrichment_artifact_path"),
        "candidateCount": len(candidates),
        "candidates": candidates,
        "orphanedApprovals": orphaned,
    }


def _build_next_check_execution_history(
    artifacts: Sequence[ExternalAnalysisArtifact],
    root_dir: Path,
    run_id: str,
    limit: int = _NEXT_CHECK_EXECUTION_HISTORY_LIMIT,
) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for artifact in sorted(artifacts, key=lambda item: item.timestamp, reverse=True):
        if (
            artifact.purpose != ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION
            or not artifact_matches_run(artifact, run_id)
        ):
            continue
        payload = artifact.payload if isinstance(artifact.payload, Mapping) else {}
        entries.append(
            {
                "timestamp": artifact.timestamp.isoformat(),
                "clusterLabel": artifact.cluster_label,
                "candidateDescription": payload.get("candidateDescription"),
                "commandFamily": payload.get("commandFamily"),
                "status": artifact.status.value,
                "durationMs": artifact.duration_ms,
                "artifactPath": _relative_path(root_dir, artifact.artifact_path),
                "timedOut": artifact.timed_out,
                "stdoutTruncated": artifact.stdout_truncated,
                "stderrTruncated": artifact.stderr_truncated,
                "outputBytesCaptured": artifact.output_bytes_captured,
            }
        )
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
        key=lambda item: item[0] or datetime.min,
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


def _parse_timestamp(value: object | None) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


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
        entries.append(
            {
                "kind": artifact.kind,
                "summary": artifact.summary,
                "timestamp": artifact.timestamp,
                "run_id": artifact.run_id,
                "cluster_label": artifact.cluster_label,
                "context": artifact.context,
                "details": detail_entries,
                "artifact_path": _relative_path(root_dir, path),
            }
        )
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
        try:
            finish = datetime.fromisoformat(timestamp)
        except ValueError:
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
