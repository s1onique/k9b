"""Helpers for recording operator approval of planned next-check candidates."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..structured_logging import emit_structured_log
from .artifact import ExternalAnalysisArtifact, ExternalAnalysisPurpose, ExternalAnalysisStatus, write_external_analysis_artifact
from .utils import artifact_matches_run

_APPROVAL_LOG_COMPONENT = "next-check-approval"


@dataclass(frozen=True)
class NextCheckApprovalRecord:
    candidate_index: int | None
    candidate_id: str | None
    artifact_path: str | None
    timestamp: datetime
    cluster_label: str | None
    plan_artifact_path: str | None
    candidate_description: str | None


@dataclass(frozen=True)
class NextCheckApprovals:
    by_id: dict[str, NextCheckApprovalRecord]
    by_index: dict[int, NextCheckApprovalRecord]


def _approval_artifact_path(runs_dir: Path, run_id: str, candidate_index: int) -> Path:
    directory = runs_dir / "external-analysis"
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{run_id}-next-check-approval-{candidate_index}.json"
    return directory / filename


def log_next_check_approval_event(
    *,
    severity: str,
    message: str,
    run_label: str,
    run_id: str,
    plan_artifact_path: str | None,
    candidate_index: int | None,
    candidate_id: str | None = None,
    candidate_description: str | None,
    target_cluster: str | None,
    event: str,
) -> None:
    metadata: dict[str, object] = {"event": event}
    if plan_artifact_path:
        metadata["planArtifactPath"] = plan_artifact_path
    if candidate_description:
        metadata["candidateDescription"] = candidate_description
    if target_cluster:
        metadata["clusterLabel"] = target_cluster
    if candidate_index is not None:
        metadata["candidateIndex"] = candidate_index
    if candidate_id:
        metadata["candidateId"] = candidate_id
    emit_structured_log(
        component=_APPROVAL_LOG_COMPONENT,
        message=message,
        severity=severity,
        run_label=run_label,
        run_id=run_id,
        metadata=metadata,
    )


def record_next_check_approval(
    *,
    runs_dir: Path,
    run_id: str,
    run_label: str,
    plan_artifact_path: str,
    candidate_index: int,
    candidate_id: str | None = None,
    candidate_description: str | None,
    target_cluster: str | None,
) -> ExternalAnalysisArtifact:
    artifact_path = _approval_artifact_path(runs_dir, run_id, candidate_index)
    artifact = ExternalAnalysisArtifact(
        tool_name="next-check-approval",
        run_id=run_id,
        cluster_label=target_cluster or run_label,
        run_label=run_label,
        source_artifact=plan_artifact_path,
        summary="Operator approved next-check candidate",
        findings=(),
        suggested_next_checks=(),
        status=ExternalAnalysisStatus.SUCCESS,
        timestamp=datetime.now(UTC),
        artifact_path=str(artifact_path),
        provider="operator",
        duration_ms=0,
        purpose=ExternalAnalysisPurpose.NEXT_CHECK_APPROVAL,
        payload={
            "planArtifactPath": plan_artifact_path,
            "candidateIndex": candidate_index,
            "candidateId": candidate_id,
            "candidateDescription": candidate_description,
            "targetCluster": target_cluster,
        },
    )
    write_external_analysis_artifact(artifact_path, artifact)
    log_next_check_approval_event(
        severity="INFO",
        message="Operator next-check approval recorded",
        run_label=run_label,
        run_id=run_id,
        plan_artifact_path=plan_artifact_path,
        candidate_index=candidate_index,
        candidate_id=candidate_id,
        candidate_description=candidate_description,
        target_cluster=target_cluster,
        event="approval-recorded",
    )
    return artifact


def collect_next_check_approvals(
    artifacts: Iterable[ExternalAnalysisArtifact], run_id: str
) -> NextCheckApprovals:
    by_id: dict[str, NextCheckApprovalRecord] = {}
    by_index: dict[int, NextCheckApprovalRecord] = {}
    for artifact in sorted(artifacts, key=lambda item: item.timestamp, reverse=True):
        if artifact.purpose != ExternalAnalysisPurpose.NEXT_CHECK_APPROVAL:
            continue
        if not artifact_matches_run(artifact, run_id):
            continue
        payload = artifact.payload if isinstance(artifact.payload, Mapping) else {}
        raw_index = payload.get("candidateIndex")
        raw_id = payload.get("candidateId")
        index_val = raw_index if isinstance(raw_index, int) else None
        id_val = raw_id if isinstance(raw_id, str) else None
        record = NextCheckApprovalRecord(
            candidate_index=index_val,
            candidate_id=id_val,
            artifact_path=str(artifact.artifact_path) if artifact.artifact_path else None,
            timestamp=artifact.timestamp,
            cluster_label=artifact.cluster_label,
            plan_artifact_path=str(payload.get("planArtifactPath"))
            if payload.get("planArtifactPath")
            else None,
            candidate_description=str(payload.get("candidateDescription"))
            if payload.get("candidateDescription")
            else None,
        )
        if id_val:
            by_id[id_val] = record
        if index_val is not None:
            by_index[index_val] = record
    return NextCheckApprovals(by_id=by_id, by_index=by_index)
