"""Manual execution helpers for next-check planner candidates."""  # noqa: I001

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from .artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisStatus,
    write_external_analysis_artifact,
)
from .manual_next_check_artifacts import (
    _build_payload,
    _extract_alertmanager_provenance,
    build_command_missing_artifact,
    build_success_artifact,
    build_timeout_artifact,
    build_validation_failed_artifact,
)
from .manual_next_check_commands import (
    _DANGEROUS_CHARS,
    ManualNextCheckError,
    _build_command,
    _strip_context_arguments,
    _validate_command_tokens,
)
from .manual_next_check_gating import (
    _ALLOWED_FAMILIES,
    _candidate_blocking_reason,
    check_candidate_gating,
    validate_command_family,
)
from .manual_next_check_logging import (
    _artifact_path_for_run,
    _log_and_raise_gating,
    _log_artifact_write,
    _log_execution_event,
)
from .manual_next_check_output import (
    _OUTPUT_LIMIT,
    _capture_output,
    _summarize_outputs,
)
from .next_check_planner import BlockingReason, CommandFamily

# Re-export for backward compatibility
__all__ = [
    "ManualNextCheckError",
    "execute_manual_next_check",
    "check_existing_execution_artifact",
    "_ALLOWED_FAMILIES",
    "_build_command",
    "_build_payload",
    "_candidate_blocking_reason",
    "_capture_output",
    "_DANGEROUS_CHARS",
    "_extract_alertmanager_provenance",
    "_OUTPUT_LIMIT",
    "_strip_context_arguments",
    "_validate_command_tokens",
]

CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]

_COMMAND_TIMEOUT_SECONDS = 45


def _default_runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        capture_output=True,
        text=True,
        check=False,
        timeout=_COMMAND_TIMEOUT_SECONDS,
    )


def check_existing_execution_artifact(
    health_root: Path,
    run_id: str,
    candidate_index: int,
    candidate: Mapping[str, object],
) -> ExternalAnalysisArtifact | None:
    """Check if an execution artifact already exists for this candidate."""
    artifact_path = _artifact_path_for_run(health_root, run_id, candidate_index)
    if not artifact_path.exists():
        return None

    try:
        from .artifact_readers import try_read_external_analysis_artifact

        artifact = try_read_external_analysis_artifact(
            artifact_path,
            run_id=run_id,
            artifact_kind="next-check-execution",
            log_failures=False,
        )
        if artifact is None:
            return None

        payload = artifact.payload if isinstance(artifact.payload, Mapping) else {}
        artifact_candidate_index = payload.get("candidateIndex")
        artifact_command_family = payload.get("commandFamily")
        artifact_target_cluster = payload.get("targetCluster")

        candidate_command_family = str(candidate.get("suggestedCommandFamily") or "")
        candidate_target_cluster = str(candidate.get("targetCluster") or "")

        if (
            artifact_candidate_index == candidate_index
            and artifact_command_family == candidate_command_family
            and artifact_target_cluster == candidate_target_cluster
        ):
            return artifact

        return None
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def execute_manual_next_check(
    *,
    health_root: Path,
    run_id: str,
    run_label: str,
    plan_artifact_path: Path,
    candidate_index: int,
    candidate: Mapping[str, object],
    target_context: str,
    target_cluster: str,
    command_runner: CommandRunner | None = None,
) -> ExternalAnalysisArtifact:
    plan_artifact_path_str = str(plan_artifact_path)
    description = str(candidate.get("description") or "").strip()
    raw_candidate_id = candidate.get("candidateId")
    candidate_id_value = raw_candidate_id if isinstance(raw_candidate_id, str) and raw_candidate_id else None

    # Parse and validate command family
    family_raw = str(candidate.get("suggestedCommandFamily") or "").strip()
    if not family_raw:
        _log_and_raise_gating(
            reason="Candidate lacks a command family.",
            run_label=run_label,
            run_id=run_id,
            plan_artifact_path=plan_artifact_path_str,
            candidate_index=candidate_index,
            target_cluster=target_cluster or run_label,
            target_context=target_context,
            candidate_description=description,
            candidate_id=candidate_id_value,
            command_family=None,
            blocking_reason=BlockingReason.UNKNOWN_COMMAND,
            error_class=ManualNextCheckError,
        )
    try:
        family = CommandFamily(family_raw)
    except ValueError:
        _log_and_raise_gating(
            reason=f"Unsupported command family: {family_raw}",
            run_label=run_label,
            run_id=run_id,
            plan_artifact_path=plan_artifact_path_str,
            candidate_index=candidate_index,
            target_cluster=target_cluster or run_label,
            target_context=target_context,
            candidate_description=description,
            candidate_id=candidate_id_value,
            command_family=family_raw,
            blocking_reason=BlockingReason.COMMAND_NOT_ALLOWED,
            error_class=ManualNextCheckError,
        )

    validate_command_family(
        family_raw=family_raw,
        family=family,
        plan_artifact_path=plan_artifact_path_str,
        run_label=run_label,
        run_id=run_id,
        candidate_index=candidate_index,
        target_cluster=target_cluster,
        target_context=target_context,
        description=description,
        candidate_id_value=candidate_id_value,
    )

    check_candidate_gating(
        candidate=candidate,
        family=family,
        description=description,
        target_context=target_context,
        plan_artifact_path=plan_artifact_path_str,
        run_label=run_label,
        run_id=run_id,
        candidate_index=candidate_index,
        target_cluster=target_cluster,
        candidate_id_value=candidate_id_value,
    )

    # IDEMPOTENCY CHECK
    existing_artifact = check_existing_execution_artifact(
        health_root, run_id, candidate_index, candidate
    )
    if existing_artifact is not None:
        _log_execution_event(
            message="Manual next-check execution already exists, returning existing artifact",
            severity="INFO",
            run_label=run_label,
            run_id=run_id,
            plan_artifact_path=str(plan_artifact_path),
            candidate_index=candidate_index,
            target_cluster=target_cluster,
            target_context=target_context,
            candidate_description=description,
            candidate_id=candidate_id_value,
            command=None,
            command_family=family.value,
            status=existing_artifact.status.value,
            artifact_path=existing_artifact.artifact_path,
            event="already-executed",
        )
        return existing_artifact

    runner = command_runner or _default_runner

    # Build command and catch validation failures
    try:
        command = _build_command(description, target_context, family)
    except ManualNextCheckError as validation_error:
        artifact, artifact_path = build_validation_failed_artifact(
            run_id=run_id,
            run_label=run_label,
            plan_artifact_path=plan_artifact_path,
            candidate_index=candidate_index,
            candidate=candidate,
            target_cluster=target_cluster,
            target_context=target_context,
            validation_error=str(validation_error),
            health_root=health_root,
        )
        _log_artifact_write(
            run_id=run_id,
            run_label=run_label,
            artifact_path=artifact_path,
            health_root=health_root,
            purpose="next-check-execution",
        )
        write_external_analysis_artifact(artifact_path, artifact)
        _log_execution_event(
            message="Manual next-check execution validation failed",
            severity="WARNING",
            run_label=run_label,
            run_id=run_id,
            plan_artifact_path=str(plan_artifact_path),
            candidate_index=candidate_index,
            target_cluster=target_cluster,
            target_context=target_context,
            candidate_description=description,
            candidate_id=candidate_id_value,
            command=None,
            command_family=family.value,
            status=artifact.status.value,
            artifact_path=artifact.artifact_path,
            event="validation-failed",
            stdout_truncated=False,
            stderr_truncated=False,
            output_bytes_captured=0,
        )
        raise

    _log_execution_event(
        message="Manual next-check execution requested",
        severity="INFO",
        run_label=run_label,
        run_id=run_id,
        plan_artifact_path=str(plan_artifact_path),
        candidate_index=candidate_index,
        target_cluster=target_cluster,
        target_context=target_context,
        candidate_description=description,
        candidate_id=candidate_id_value,
        command=command,
        command_family=family.value,
        status=None,
        event="requested",
    )
    start = time.perf_counter()
    try:
        result = runner(command)
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.perf_counter() - start) * 1000)
        stdout_text, stderr_text, combined_output, stdout_truncated, stderr_truncated, output_bytes = _summarize_outputs(
            exc.stdout, exc.stderr
        )
        artifact, artifact_path = build_timeout_artifact(
            run_id=run_id,
            run_label=run_label,
            plan_artifact_path=plan_artifact_path,
            candidate_index=candidate_index,
            candidate=candidate,
            target_cluster=target_cluster,
            target_context=target_context,
            command=command,
            duration_ms=duration_ms,
            stdout_text=stdout_text,
            stderr_text=stderr_text,
            combined_output=combined_output,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            output_bytes=output_bytes,
            health_root=health_root,
        )
        _log_artifact_write(
            run_id=run_id,
            run_label=run_label,
            artifact_path=artifact_path,
            health_root=health_root,
            purpose="next-check-execution",
        )
        write_external_analysis_artifact(artifact_path, artifact)
        _log_execution_event(
            message="Manual next-check execution timed out",
            severity="WARNING",
            run_label=run_label,
            run_id=run_id,
            plan_artifact_path=str(plan_artifact_path),
            candidate_index=candidate_index,
            target_cluster=target_cluster,
            target_context=target_context,
            candidate_description=description,
            candidate_id=candidate_id_value,
            command=command,
            command_family=family.value,
            status=artifact.status.value,
            artifact_path=artifact.artifact_path,
            event="timed-out",
            timed_out=True,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            output_bytes_captured=output_bytes,
        )
        return artifact
    except FileNotFoundError as exc:
        duration_ms = int((time.perf_counter() - start) * 1000)
        artifact, artifact_path = build_command_missing_artifact(
            run_id=run_id,
            run_label=run_label,
            plan_artifact_path=plan_artifact_path,
            candidate_index=candidate_index,
            candidate=candidate,
            target_cluster=target_cluster,
            target_context=target_context,
            command=command,
            duration_ms=duration_ms,
            error_message=str(exc),
            health_root=health_root,
        )
        _log_artifact_write(
            run_id=run_id,
            run_label=run_label,
            artifact_path=artifact_path,
            health_root=health_root,
            purpose="next-check-execution",
        )
        write_external_analysis_artifact(artifact_path, artifact)
        _log_execution_event(
            message="Manual next-check execution failed: kubectl unavailable",
            severity="ERROR",
            run_label=run_label,
            run_id=run_id,
            plan_artifact_path=str(plan_artifact_path),
            candidate_index=candidate_index,
            target_cluster=target_cluster,
            target_context=target_context,
            candidate_description=description,
            candidate_id=candidate_id_value,
            command=command,
            command_family=family.value,
            status=artifact.status.value,
            artifact_path=artifact.artifact_path,
            event="command-missing",
        )
        raise ManualNextCheckError("kubectl is unavailable on this host.")

    duration_ms = int((time.perf_counter() - start) * 1000)
    stdout_text, stderr_text, combined_output, stdout_truncated, stderr_truncated, output_bytes = _summarize_outputs(
        result.stdout, result.stderr
    )
    status = ExternalAnalysisStatus.SUCCESS if result.returncode == 0 else ExternalAnalysisStatus.FAILED
    artifact, artifact_path = build_success_artifact(
        run_id=run_id,
        run_label=run_label,
        plan_artifact_path=plan_artifact_path,
        candidate_index=candidate_index,
        candidate=candidate,
        target_cluster=target_cluster,
        target_context=target_context,
        command=command,
        duration_ms=duration_ms,
        status=status,
        stdout_text=stdout_text,
        stderr_text=stderr_text,
        combined_output=combined_output,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
        output_bytes=output_bytes,
        health_root=health_root,
    )
    _log_artifact_write(
        run_id=run_id,
        run_label=run_label,
        artifact_path=artifact_path,
        health_root=health_root,
        purpose="next-check-execution",
    )
    write_external_analysis_artifact(artifact_path, artifact)
    _log_execution_event(
        message="Manual next-check execution completed",
        severity="INFO" if status == ExternalAnalysisStatus.SUCCESS else "WARNING",
        run_label=run_label,
        run_id=run_id,
        plan_artifact_path=str(plan_artifact_path),
        candidate_index=candidate_index,
        target_cluster=target_cluster,
        target_context=target_context,
        candidate_description=description,
        candidate_id=candidate_id_value,
        command=command,
        command_family=family.value,
        status=artifact.status.value,
        artifact_path=artifact.artifact_path,
        event="completed" if status == ExternalAnalysisStatus.SUCCESS else "failed",
        timed_out=False,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
        output_bytes_captured=output_bytes,
    )
    return artifact
