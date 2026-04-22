"""Utilities that build a compact artifact index for UI consumers."""

from __future__ import annotations

import json
import re
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
    _build_next_check_execution_history,
    _classify_blocked_candidate,  # noqa: F401  # re-exported for tests
    _classify_execution_failure,  # noqa: F401  # re-exported for tests
    _classify_execution_success,  # noqa: F401  # re-exported for tests
)
from .ui_planner_queue import (
    _PLANNER_NEXT_ACTION_HINTS,  # noqa: F401  # re-exported for tests
    _PLANNER_STATUS_ENRICHMENT_FAILED,  # noqa: F401  # re-exported for tests
    _PLANNER_STATUS_ENRICHMENT_NOT_ATTEMPTED,  # noqa: F401  # re-exported for tests
    _PLANNER_STATUS_ENRICHMENT_SUCCESS_NO_CHECKS,  # noqa: F401  # re-exported for tests
    _PLANNER_STATUS_PLANNER_MISSING,  # noqa: F401  # re-exported for tests
    _PLANNER_STATUS_PLANNER_PRESENT,  # noqa: F401  # re-exported for tests
    _PLANNER_STATUS_POLICY_DISABLED,  # noqa: F401  # re-exported for tests
    _build_next_check_planner_availability,
    _build_next_check_queue,
    _build_next_check_queue_explanation,
    _derive_priority_rationale,  # noqa: F401  # re-exported for tests
    _serialize_next_check_plan,
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
    from ..external_analysis.utils import artifact_matches_run
    for artifact in sorted(artifacts, key=lambda item: item.timestamp, reverse=True):
        if (
            artifact.purpose == ExternalAnalysisPurpose.REVIEW_ENRICHMENT
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
