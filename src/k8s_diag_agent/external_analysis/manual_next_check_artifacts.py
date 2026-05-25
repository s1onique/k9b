"""Artifact construction helpers for manual next-check execution."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from .artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisPurpose,
    ExternalAnalysisStatus,
)
from .manual_next_check_logging import _artifact_path_for_run


def _extract_alertmanager_provenance(
    candidate: Mapping[str, object],
) -> dict[str, object] | None:
    """Extract Alertmanager provenance from candidate if present.

    The provenance snapshot is preserved when execution is triggered by
    an Alertmanager-ranked queue item. This preserves the ranking influence
    for observability and operator feedback.

    Returns:
        The provenance dict if present, None otherwise.
        No provenance is invented - we only copy what exists.
    """
    raw_provenance = candidate.get("alertmanagerProvenance")
    if isinstance(raw_provenance, dict):
        return dict(raw_provenance)
    return None


def _build_payload(
    candidate: Mapping[str, object],
    candidate_index: int,
    command: list[str],
    plan_artifact: str,
    target_cluster: str | None,
    target_context: str,
    timed_out: bool,
    stdout_truncated: bool,
    stderr_truncated: bool,
    output_bytes_captured: int,
) -> dict[str, object]:
    """Build the payload dict for an execution artifact."""
    raw_candidate_id = candidate.get("candidateId")
    candidate_id_value = raw_candidate_id if isinstance(raw_candidate_id, str) and raw_candidate_id else None
    payload: dict[str, object] = {
        "candidateIndex": candidate_index,
        "candidateId": candidate_id_value,
        "candidateDescription": str(candidate.get("description") or ""),
        "commandFamily": str(candidate.get("suggestedCommandFamily") or ""),
        "command": command,
        "planArtifactPath": plan_artifact,
        "targetCluster": target_cluster,
        "targetContext": target_context,
        "timedOut": timed_out,
        "stdoutTruncated": stdout_truncated,
        "stderrTruncated": stderr_truncated,
        "outputBytesCaptured": output_bytes_captured,
    }
    return payload


def build_validation_failed_artifact(
    *,
    run_id: str,
    run_label: str,
    plan_artifact_path: Path,
    candidate_index: int,
    candidate: Mapping[str, object],
    target_cluster: str,
    target_context: str,
    validation_error: str,
    health_root: Path,
) -> tuple[ExternalAnalysisArtifact, Path]:
    """Build an artifact for validation failure case."""
    duration_ms = 0
    artifact_path = _artifact_path_for_run(health_root, run_id, candidate_index)
    alertmanager_provenance = _extract_alertmanager_provenance(candidate)
    artifact = ExternalAnalysisArtifact(
        tool_name="next-check-runner",
        run_id=run_id,
        cluster_label=target_cluster or run_label,
        run_label=run_label,
        source_artifact=str(plan_artifact_path),
        summary="Manual next-check command validation failed",
        status=ExternalAnalysisStatus.FAILED,
        timestamp=datetime.now(UTC),
        artifact_path=str(artifact_path),
        provider="next-check-runner",
        duration_ms=duration_ms,
        purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION,
        raw_output=None,
        payload=_build_payload(
            candidate,
            candidate_index,
            [],
            str(plan_artifact_path),
            target_cluster,
            target_context,
            timed_out=False,
            stdout_truncated=False,
            stderr_truncated=False,
            output_bytes_captured=0,
        ),
        error_summary=str(validation_error),
        stdout_truncated=False,
        stderr_truncated=False,
        timed_out=False,
        output_bytes_captured=0,
        alertmanager_provenance=alertmanager_provenance,
    )
    return artifact, artifact_path


def build_timeout_artifact(
    *,
    run_id: str,
    run_label: str,
    plan_artifact_path: Path,
    candidate_index: int,
    candidate: Mapping[str, object],
    target_cluster: str,
    target_context: str,
    command: list[str],
    duration_ms: int,
    stdout_text: str | None,
    stderr_text: str | None,
    combined_output: str | None,
    stdout_truncated: bool,
    stderr_truncated: bool,
    output_bytes: int,
    health_root: Path,
) -> tuple[ExternalAnalysisArtifact, Path]:
    """Build an artifact for timeout case."""
    artifact_path = _artifact_path_for_run(health_root, run_id, candidate_index)
    alertmanager_provenance = _extract_alertmanager_provenance(candidate)
    artifact = ExternalAnalysisArtifact(
        tool_name="next-check-runner",
        run_id=run_id,
        cluster_label=target_cluster or run_label,
        run_label=run_label,
        source_artifact=str(plan_artifact_path),
        summary="Manual next-check command timed out",
        status=ExternalAnalysisStatus.FAILED,
        timestamp=datetime.now(UTC),
        artifact_path=str(artifact_path),
        provider="next-check-runner",
        duration_ms=duration_ms,
        purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION,
        raw_output=combined_output,
        payload=_build_payload(
            candidate,
            candidate_index,
            command,
            str(plan_artifact_path),
            target_cluster,
            target_context,
            timed_out=True,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            output_bytes_captured=output_bytes,
        ),
        error_summary="Command timed out.",
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
        timed_out=True,
        output_bytes_captured=output_bytes,
        alertmanager_provenance=alertmanager_provenance,
    )
    return artifact, artifact_path


def build_command_missing_artifact(
    *,
    run_id: str,
    run_label: str,
    plan_artifact_path: Path,
    candidate_index: int,
    candidate: Mapping[str, object],
    target_cluster: str,
    target_context: str,
    command: list[str],
    duration_ms: int,
    error_message: str,
    health_root: Path,
) -> tuple[ExternalAnalysisArtifact, Path]:
    """Build an artifact for command missing (kubectl not found) case."""
    artifact_path = _artifact_path_for_run(health_root, run_id, candidate_index)
    alertmanager_provenance = _extract_alertmanager_provenance(candidate)
    artifact = ExternalAnalysisArtifact(
        tool_name="next-check-runner",
        run_id=run_id,
        cluster_label=target_cluster or run_label,
        run_label=run_label,
        source_artifact=str(plan_artifact_path),
        summary="Command runner not found",
        status=ExternalAnalysisStatus.FAILED,
        timestamp=datetime.now(UTC),
        artifact_path=str(artifact_path),
        provider="next-check-runner",
        duration_ms=duration_ms,
        purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION,
        payload=_build_payload(
            candidate,
            candidate_index,
            command,
            str(plan_artifact_path),
            target_cluster,
            target_context,
            timed_out=False,
            stdout_truncated=False,
            stderr_truncated=False,
            output_bytes_captured=0,
        ),
        raw_output=None,
        error_summary=error_message,
        alertmanager_provenance=alertmanager_provenance,
    )
    return artifact, artifact_path


def build_success_artifact(
    *,
    run_id: str,
    run_label: str,
    plan_artifact_path: Path,
    candidate_index: int,
    candidate: Mapping[str, object],
    target_cluster: str,
    target_context: str,
    command: list[str],
    duration_ms: int,
    status: ExternalAnalysisStatus,
    stdout_text: str | None,
    stderr_text: str | None,
    combined_output: str | None,
    stdout_truncated: bool,
    stderr_truncated: bool,
    output_bytes: int,
    health_root: Path,
) -> tuple[ExternalAnalysisArtifact, Path]:
    """Build an artifact for successful/failed execution case."""
    summary = (
        "Manual next-check command executed"
        if status == ExternalAnalysisStatus.SUCCESS
        else "Manual next-check command failed"
    )
    error_summary = None
    if status == ExternalAnalysisStatus.FAILED:
        error_summary = stderr_text or "Command returned non-zero status."
    artifact_path = _artifact_path_for_run(health_root, run_id, candidate_index)
    alertmanager_provenance = _extract_alertmanager_provenance(candidate)
    artifact = ExternalAnalysisArtifact(
        tool_name="next-check-runner",
        run_id=run_id,
        cluster_label=target_cluster or run_label,
        run_label=run_label,
        source_artifact=str(plan_artifact_path),
        summary=summary,
        status=status,
        timestamp=datetime.now(UTC),
        artifact_path=str(artifact_path),
        provider="next-check-runner",
        duration_ms=duration_ms,
        purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION,
        raw_output=combined_output,
        payload=_build_payload(
            candidate,
            candidate_index,
            command,
            str(plan_artifact_path),
            target_cluster,
            target_context,
            timed_out=False,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            output_bytes_captured=output_bytes,
        ),
        error_summary=error_summary,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
        timed_out=False,
        output_bytes_captured=output_bytes,
        alertmanager_provenance=alertmanager_provenance,
    )
    return artifact, artifact_path
