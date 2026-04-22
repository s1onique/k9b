"""Utilities that build a compact artifact index for UI consumers."""

from __future__ import annotations

import json
import re
import shlex
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ..datetime_utils import parse_iso_to_utc
from ..external_analysis.artifact import ExternalAnalysisArtifact, ExternalAnalysisPurpose
from ..external_analysis.config import (
    AutoDrilldownPolicy,
    ExternalAnalysisSettings,
    ReviewEnrichmentPolicy,
)
from ..external_analysis.next_check_approval import NextCheckApprovalRecord, collect_next_check_approvals
from ..external_analysis.utils import artifact_matches_run
from ..structured_logging import emit_structured_log
from .adaptation import HealthProposal
from .notifications import NotificationArtifact
from .ui_deterministic_next_checks import (
    _build_deterministic_next_checks_projection,
    _classify_deterministic_next_check,
)
from .ui_diagnostic_pack import (
    _serialize_alertmanager_compact,
    _serialize_alertmanager_sources,
    _serialize_diagnostic_pack,
    _serialize_diagnostic_pack_review,
)
from .ui_llm_stats import (
    _build_historical_llm_stats,
    _build_llm_policy,
    _build_llm_stats,
    _build_provider_execution,
    _collect_historical_external_analysis_entries,
    _percentile_value,
    _serialize_llm_activity,
)
from .ui_next_check_execution import (
    NextCheckExecutionRecord,
    _apply_failure_follow_up,
    _apply_result_interpretation,
    _build_next_check_execution_history,
    _classify_blocked_candidate,
    _classify_execution_failure,  # noqa: F401  # re-exported for tests
    _classify_execution_success,  # noqa: F401  # re-exported for tests
    _coerce_int_value,
    _collect_next_check_execution_records,
    _derive_outcome_status,
    _determine_execution_state,
    _latest_outcome_artifact,
)
from .ui_serialization import (
    _ANALYSIS_STATUS_ORDER,
    _serialize_cluster,
    _serialize_drilldown,
    _serialize_drilldown_availability,
    _serialize_fleet_status,
    _serialize_latest_assessment,
    _serialize_notification_history,
    _serialize_proposal,
    _serialize_proposal_status_summary,
)
from .ui_shared import _relative_path

# Re-export: required by test_health_ui.py
__all__ = ["_classify_deterministic_next_check"]

if TYPE_CHECKING:
    from .loop import DrilldownArtifact, HealthAssessmentArtifact, HealthSnapshotRecord


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


def _latest_drilldown_map(drilldowns: Sequence[DrilldownArtifact]) -> dict[str, DrilldownArtifact]:
    mapping: dict[str, DrilldownArtifact] = {}
    for artifact in sorted(drilldowns, key=lambda item: item.timestamp, reverse=True):
        mapping.setdefault(artifact.label, artifact)
    return mapping


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
    """Derive a structured ranking-reason/provenance category."""
    if bool(entry.get("duplicateOfExistingEvidence")):
        return "duplicate"

    approval_state = str(entry.get("approvalState") or "").lower()
    if approval_state == "approval-stale":
        return "stale-approval"
    if approval_state == "approval-orphaned":
        return "stale-approval"

    if bool(entry.get("requiresOperatorApproval")):
        return "approval-gated"

    if entry.get("safetyReason"):
        return "safety-gated"
    if entry.get("blockingReason"):
        return "execution-gated"
    if entry.get("gatingReason"):
        return "planner-gated"

    execution_state = str(entry.get("executionState") or "").lower()
    if execution_state == "executed-success":
        return "already-executed"
    if execution_state in ("executed-failed", "timed-out"):
        return "execution-failed"

    priority_label = str(entry.get("priorityLabel") or "").lower()
    if priority_label == "secondary":
        return "deterministic-secondary"
    if priority_label == "fallback":
        return "fallback"

    return None


def _derive_priority_rationale(entry: Mapping[str, object]) -> str | None:
    """Derive a compact operator-facing explanation for why an item is in its current state."""
    original_priority_rationale = entry.get("priorityRationale")
    if isinstance(original_priority_rationale, str) and original_priority_rationale.strip():
        return original_priority_rationale.strip()

    if bool(entry.get("duplicateOfExistingEvidence")):
        dup_reason = entry.get("duplicateReason")
        if dup_reason:
            return "Already covered by existing evidence"
        return "Already covered by existing evidence"

    approval_state = str(entry.get("approvalState") or "").lower()
    if approval_state == "approval-stale":
        return "Approval is stale"
    if approval_state == "approval-orphaned":
        return "Approval record orphaned"

    requires_approval = bool(entry.get("requiresOperatorApproval"))
    if requires_approval:
        approval_reason = entry.get("approvalReason")
        if approval_reason:
            return "Approval required before execution"
        return "Approval required before execution"

    safety_reason = entry.get("safetyReason")
    blocking_reason = entry.get("blockingReason")
    gating_reason = entry.get("gatingReason")
    if safety_reason:
        return "Blocked by safety gating"
    if blocking_reason:
        return "Blocked by execution gating"
    if gating_reason:
        return "Blocked by planner gating"

    execution_state = str(entry.get("executionState") or "").lower()
    if execution_state == "executed-success":
        return "Already executed"
    if execution_state in ("executed-failed", "timed-out"):
        return "Execution failed"

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
