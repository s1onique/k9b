"""Manual execution helpers for next-check planner candidates."""  # noqa: I001

from __future__ import annotations

import shlex
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from ..structured_logging import emit_structured_log
from .artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisPurpose,
    ExternalAnalysisStatus,
    write_external_analysis_artifact,
)
from .next_check_planner import MUTATION_KEYWORDS, BlockingReason, CommandFamily

CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]

_ALLOWED_FAMILIES = {
    CommandFamily.KUBECTL_GET,
    CommandFamily.KUBECTL_DESCRIBE,
    CommandFamily.KUBECTL_LOGS,
    CommandFamily.KUBECTL_GET_CRD,
    CommandFamily.KUBECTL_TOP,
}
_DANGEROUS_CHARS = {";", "&&", "||", "|", "<", ">", "$", "`"}
_OUTPUT_LIMIT = 8192
_COMMAND_TIMEOUT_SECONDS = 45
_LOG_COMPONENT = "manual-next-check"


class ManualNextCheckError(RuntimeError):
    """Raised when a manual next-check execution is not allowed."""

    def __init__(self, message: str, *, blocking_reason: BlockingReason | None = None) -> None:
        super().__init__(message)
        self.blocking_reason = blocking_reason


def _default_runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        capture_output=True,
        text=True,
        check=False,
        timeout=_COMMAND_TIMEOUT_SECONDS,
    )


def _capture_output(value: str | bytes | None, limit: int = _OUTPUT_LIMIT) -> tuple[str | None, bool, int]:
    if value is None:
        return None, False, 0
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if not value:
        return None, False, 0
    trimmed = value.strip()
    if not trimmed:
        return None, False, 0
    truncated = len(trimmed) > limit
    if truncated and limit > 1:
        trimmed = trimmed[: limit - 1].rstrip()
        trimmed = f"{trimmed}…"
    elif truncated:
        trimmed = "…"
    bytes_captured = len(trimmed.encode("utf-8"))
    return trimmed, truncated, bytes_captured


def _strip_context_arguments(tokens: Sequence[str]) -> tuple[str, ...]:
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


def _validate_command_tokens(family: CommandFamily, tokens: Sequence[str]) -> None:
    if not tokens:
        raise ManualNextCheckError("Command text must include a kubectl subcommand.")
    subcommand = tokens[0]
    if family == CommandFamily.KUBECTL_LOGS and subcommand != "logs":
        raise ManualNextCheckError("Logs candidate must use `kubectl logs`.")
    if family == CommandFamily.KUBECTL_DESCRIBE and subcommand != "describe":
        raise ManualNextCheckError("Describe candidate must use `kubectl describe`.")
    if family == CommandFamily.KUBECTL_GET and subcommand != "get":
        raise ManualNextCheckError("Get candidate must use `kubectl get`.")
    if family == CommandFamily.KUBECTL_GET_CRD:
        if subcommand != "get":
            raise ManualNextCheckError("CRD candidate must use `kubectl get`.")
        tokens_lower = " ".join(tokens).lower()
        if "crd" not in tokens_lower and "customresourcedefinition" not in tokens_lower:
            raise ManualNextCheckError("CRD candidate must reference CRDs.")
    for token in tokens:
        lowered = token.lower()
        if any(keyword in lowered for keyword in MUTATION_KEYWORDS):
            raise ManualNextCheckError("Command references a potentially mutating keyword.")
        if any(danger in token for danger in _DANGEROUS_CHARS):
            raise ManualNextCheckError("Command contains unsupported punctuation for manual execution.")


def _candidate_blocking_reason(candidate: Mapping[str, object]) -> BlockingReason | None:
    raw = candidate.get("blockingReason")
    if isinstance(raw, str) and raw:
        try:
            return BlockingReason(raw)
        except ValueError:
            return None
    return None


def _build_command(description: str, target_context: str, family: CommandFamily) -> list[str]:
    try:
        tokens = shlex.split(description)
    except ValueError as exc:
        raise ManualNextCheckError(f"Unable to parse candidate command: {exc}") from exc
    if not tokens or tokens[0] != "kubectl":
        raise ManualNextCheckError("Candidate command must begin with `kubectl`.")
    remainder = _strip_context_arguments(tokens[1:])
    _validate_command_tokens(family, remainder)
    if not remainder:
        raise ManualNextCheckError("Candidate command does not include a subcommand.")
    return ["kubectl", *remainder, "--context", target_context]


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


def _summarize_outputs(
    stdout: str | bytes | None,
    stderr: str | bytes | None,
 ) -> tuple[str | None, str | None, str | None, bool, bool, int]:
    stdout_text, stdout_truncated, stdout_bytes = _capture_output(stdout)
    stderr_text, stderr_truncated, stderr_bytes = _capture_output(stderr)
    combined = "\n".join(filter(None, (stdout_text, stderr_text))) or None
    return stdout_text, stderr_text, combined, stdout_truncated, stderr_truncated, (
        stdout_bytes + stderr_bytes
    )


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
) -> None:
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
    raise ManualNextCheckError(reason, blocking_reason=blocking_reason)


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
    if not candidate.get("safeToAutomate"):
        blocking_reason = _candidate_blocking_reason(candidate)
        _log_and_raise_gating(
            reason="Candidate is not marked safe to automate.",
            run_label=run_label,
            run_id=run_id,
            plan_artifact_path=plan_artifact_path_str,
            candidate_index=candidate_index,
            target_cluster=target_cluster or run_label,
            target_context=target_context,
            candidate_description=description,
            candidate_id=candidate_id_value,
            command_family=None,
            blocking_reason=blocking_reason,
        )
    requires_approval = bool(candidate.get("requiresOperatorApproval"))
    approval_status = str(candidate.get("approvalStatus") or "").lower()
    if requires_approval and approval_status != "approved":
        blocking_reason = _candidate_blocking_reason(candidate) or BlockingReason.REQUIRES_APPROVAL
        _log_and_raise_gating(
            reason="Candidate requires operator approval before execution.",
            run_label=run_label,
            run_id=run_id,
            plan_artifact_path=plan_artifact_path_str,
            candidate_index=candidate_index,
            target_cluster=target_cluster or run_label,
            target_context=target_context,
            candidate_description=description,
            candidate_id=candidate_id_value,
            command_family=None,
            blocking_reason=blocking_reason,
        )
    if candidate.get("duplicateOfExistingEvidence"):
        _log_and_raise_gating(
            reason="Candidate is a duplicate of existing evidence.",
            run_label=run_label,
            run_id=run_id,
            plan_artifact_path=plan_artifact_path_str,
            candidate_index=candidate_index,
            target_cluster=target_cluster or run_label,
            target_context=target_context,
            candidate_description=description,
            candidate_id=candidate_id_value,
            command_family=None,
            blocking_reason=_candidate_blocking_reason(candidate) or BlockingReason.DUPLICATE,
        )
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
        )
    if family not in _ALLOWED_FAMILIES:
        _log_and_raise_gating(
            reason=f"Command family '{family.value}' is not allowed for manual execution.",
            run_label=run_label,
            run_id=run_id,
            plan_artifact_path=plan_artifact_path_str,
            candidate_index=candidate_index,
            target_cluster=target_cluster or run_label,
            target_context=target_context,
            candidate_description=description,
            candidate_id=candidate_id_value,
            command_family=family.value,
            blocking_reason=BlockingReason.COMMAND_NOT_ALLOWED,
        )
    if not description:
        _log_and_raise_gating(
            reason="Candidate description is missing.",
            run_label=run_label,
            run_id=run_id,
            plan_artifact_path=plan_artifact_path_str,
            candidate_index=candidate_index,
            target_cluster=target_cluster or run_label,
            target_context=target_context,
            candidate_description="",
            candidate_id=candidate_id_value,
            command_family=family.value,
            blocking_reason=BlockingReason.MISSING_DESCRIPTION,
        )
    if not target_context:
        _log_and_raise_gating(
            reason="Unable to determine kubectl context for the target cluster.",
            run_label=run_label,
            run_id=run_id,
            plan_artifact_path=plan_artifact_path_str,
            candidate_index=candidate_index,
            target_cluster=target_cluster or run_label,
            target_context=target_context,
            candidate_description=description,
            candidate_id=candidate_id_value,
            command_family=family.value,
            blocking_reason=BlockingReason.MISSING_CONTEXT,
        )
    runner = command_runner or _default_runner
    command = _build_command(description, target_context, family)
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
        (
            _stdout_text,
            stderr_text,
            combined_output,
            stdout_truncated,
            stderr_truncated,
            output_bytes,
        ) = _summarize_outputs(exc.stdout, exc.stderr)
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
        _log_artifact_write(
            run_id=run_id,
            run_label=run_label,
            artifact_path=artifact_path,
            health_root=health_root,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION.value,
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
            error_summary=f"{exc}",
            alertmanager_provenance=alertmanager_provenance,
        )
        _log_artifact_write(
            run_id=run_id,
            run_label=run_label,
            artifact_path=artifact_path,
            health_root=health_root,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION.value,
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
    (
        _stdout_text,
        stderr_text,
        combined_output,
        stdout_truncated,
        stderr_truncated,
        output_bytes,
    ) = _summarize_outputs(result.stdout, result.stderr)
    status = ExternalAnalysisStatus.SUCCESS if result.returncode == 0 else ExternalAnalysisStatus.FAILED
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
    _log_artifact_write(
        run_id=run_id,
        run_label=run_label,
        artifact_path=artifact_path,
        health_root=health_root,
        purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION.value,
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
