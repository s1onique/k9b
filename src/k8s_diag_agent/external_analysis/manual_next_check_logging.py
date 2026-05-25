"""Logging helpers for manual next-check execution."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ..structured_logging import emit_structured_log
from .manual_next_check_commands import ManualNextCheckError
from .next_check_planner import BlockingReason

_LOG_COMPONENT = "manual-next-check"


def _log_execution_event(
    *,
    message: str,
    severity: str,
    run_label: str,
    run_id: str,
    plan_artifact_path: str,
    candidate_index: int,
    target_cluster: str | None,
    target_context: str | None,
    candidate_description: str | None,
    candidate_id: str | None,
    command: Sequence[str] | None,
    command_family: str | None,
    status: str | None = None,
    artifact_path: str | None = None,
    event: str | None = None,
    gating_reason: str | None = None,
    blocking_reason: str | None = None,
    timed_out: bool | None = None,
    stdout_truncated: bool | None = None,
    stderr_truncated: bool | None = None,
    output_bytes_captured: int | None = None,
) -> dict[str, object]:
    """Log structured execution events for manual next-check operations.

    Args:
        message: Human-readable log message
        severity: Log severity level (INFO, WARNING, ERROR, DEBUG)
        run_label: Human-readable run identifier
        run_id: Unique run identifier
        plan_artifact_path: Path to the plan artifact
        candidate_index: Index of the candidate in the plan
        target_cluster: Cluster label
        target_context: kubectl context
        candidate_description: LLM-generated command description
        candidate_id: Unique candidate identifier
        command: The kubectl command being executed
        command_family: Command family (kubectl-get, kubectl-logs, etc.)
        status: Execution status
        artifact_path: Path to the execution artifact
        event: Event type (requested, completed, failed, etc.)
        gating_reason: Reason for gating rejection
        blocking_reason: Blocking reason enum value
        timed_out: Whether command timed out
        stdout_truncated: Whether stdout was truncated
        stderr_truncated: Whether stderr was truncated
        output_bytes_captured: Total output bytes captured

    Returns:
        The structured log dict that was emitted
    """
    metadata: dict[str, object] = {
        "candidateIndex": candidate_index,
        "planArtifactPath": plan_artifact_path,
    }
    if target_cluster:
        metadata["clusterLabel"] = target_cluster
    if target_context:
        metadata["targetContext"] = target_context
    if candidate_description:
        metadata["candidateDescription"] = candidate_description
    if candidate_id:
        metadata["candidateId"] = candidate_id
    if command_family:
        metadata["commandFamily"] = command_family
    if command:
        metadata["command"] = list(command)
    if status:
        metadata["status"] = status
    if artifact_path:
        metadata["artifactPath"] = artifact_path
    if event:
        metadata["event"] = event
    if gating_reason:
        metadata["gatingReason"] = gating_reason
    if blocking_reason:
        metadata["blockingReason"] = blocking_reason
    if timed_out is not None:
        metadata["timedOut"] = timed_out
    if stdout_truncated is not None:
        metadata["stdoutTruncated"] = stdout_truncated
    if stderr_truncated is not None:
        metadata["stderrTruncated"] = stderr_truncated
    if output_bytes_captured is not None:
        metadata["outputBytesCaptured"] = output_bytes_captured
    return emit_structured_log(
        component=_LOG_COMPONENT,
        message=message,
        severity=severity,
        run_label=run_label,
        run_id=run_id,
        metadata=metadata,
    )


def _log_and_raise_gating(
    *,
    reason: str,
    run_label: str,
    run_id: str,
    plan_artifact_path: str,
    candidate_index: int,
    target_cluster: str | None,
    target_context: str | None,
    candidate_description: str | None,
    candidate_id: str | None,
    command_family: str | None,
    blocking_reason: BlockingReason | None = None,
    error_class: type[Exception],
) -> None:
    """Log a gating rejection and raise an exception.

    Args:
        reason: Human-readable gating rejection reason
        run_label: Human-readable run identifier
        run_id: Unique run identifier
        plan_artifact_path: Path to the plan artifact
        candidate_index: Index of the candidate
        target_cluster: Cluster label
        target_context: kubectl context
        candidate_description: LLM-generated command description
        candidate_id: Unique candidate identifier
        command_family: Command family
        blocking_reason: Blocking reason enum
        error_class: Exception class to raise
    """
    _log_execution_event(
        message="Manual next-check execution rejected by gating",
        severity="WARNING",
        run_label=run_label,
        run_id=run_id,
        plan_artifact_path=plan_artifact_path,
        candidate_index=candidate_index,
        target_cluster=target_cluster,
        target_context=target_context,
        candidate_description=candidate_description,
        candidate_id=candidate_id,
        command=None,
        command_family=command_family,
        status=None,
        event="gating-rejected",
        gating_reason=reason,
        blocking_reason=blocking_reason.value if blocking_reason else None,
    )
    # ManualNextCheckError accepts blocking_reason as a keyword argument
    if error_class is ManualNextCheckError:
        raise error_class(reason, blocking_reason=blocking_reason)
    raise error_class(reason)


def _artifact_path_for_run(health_root: Path, run_id: str, candidate_index: int) -> Path:
    """Compute the artifact path for a next-check execution artifact.

    Execution artifacts live under health_root/external-analysis/, not runs_root/external-analysis/.
    This is critical because the UI scans runs/health/external-analysis/ to find execution artifacts.

    Args:
        health_root: The health root directory (runs/health or runs depending on setup)
        run_id: The run ID
        candidate_index: The candidate index

    Returns:
        Path to the execution artifact
    """
    directory = health_root / "external-analysis"
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{run_id}-next-check-execution-{candidate_index}.json"
    return directory / filename


def _log_artifact_write(
    *,
    run_id: str,
    run_label: str,
    artifact_path: Path,
    health_root: Path,
    purpose: str = "next-check-execution",
) -> None:
    """Log structured information about execution artifact writes.

    This provides observability into where artifacts are being written,
    which is critical for debugging path-related issues.

    Args:
        run_id: The run ID
        run_label: The run label
        artifact_path: The full path to the artifact being written
        health_root: The health root directory used
        purpose: The purpose of the artifact
    """
    emit_structured_log(
        component="next-check-execution",
        message="Writing execution artifact",
        run_label=run_label,
        run_id=run_id,
        severity="DEBUG",
        metadata={
            "artifact_path": str(artifact_path),
            "health_root": str(health_root),
            "runs_root": str(health_root.parent),  # Parent of health_root is runs_root
            "purpose": purpose,
            "artifact_relative_path": str(artifact_path.relative_to(health_root)),
        },
    )
