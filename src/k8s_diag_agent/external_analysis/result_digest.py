"""Compact result-digest generation for usefulness review exports.

This module provides deterministic, compact digests of execution results
for external reviewer judgment without dumping full stdout/stderr.

Also provides ExecutionResultDigest for feeding execution results into
next-check planning context.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .result_digest_signals import classify_failure, extract_signal_markers

if TYPE_CHECKING:
    from .artifact import ExternalAnalysisArtifact


def _coerce_optional_int(value: object | None) -> int | None:
    """Coerce a value to int if possible, handling JSON deserialization types."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


@dataclass(frozen=True)
class ResultDigest:
    """Compact digest of execution result for reviewer inspection."""

    result_digest: str
    """Primary digest: short summary of result outcome."""

    result_digest_lines: tuple[str, ...]
    """Most useful output lines, truncated at ~5 lines max."""

    stderr_digest: str | None
    """Compact stderr summary if stderr was non-empty."""

    stdout_digest: str | None
    """Compact stdout summary if stdout was non-empty."""

    signal_markers: tuple[str, ...]
    """Extracted diagnostic signal markers from output."""

    failure_class: str | None
    """Classified failure reason if command failed."""

    exit_code: int | None
    """Exit code if available."""

    output_bytes_captured: int | None
    """Total bytes captured from stdout+stderr."""

    stdout_truncated: bool | None
    """Whether stdout was truncated during capture."""

    stderr_truncated: bool | None
    """Whether stderr was truncated during capture."""


def _build_result_digest(
    status: str,
    error_summary: str | None,
    timed_out: bool | None,
    exit_code: int | None,
    output_bytes_captured: int | None,
) -> str:
    """Build primary result digest string.

    Args:
        status: Execution status value
        error_summary: Error summary text
        timed_out: Whether command timed out
        exit_code: Command exit code
        output_bytes_captured: Total bytes captured

    Returns:
        Short digest string summarizing result
    """
    if timed_out:
        return "TIMED_OUT"

    status_lower = status.lower() if status else ""
    if "fail" in status_lower:
        if error_summary:
            # Truncate error summary for digest
            digest = error_summary[:80]
            if len(error_summary) > 80:
                digest = f"{digest}…"
            return digest
        if exit_code is not None:
            return f"FAILED: exit_code={exit_code}"
        return "FAILED"

    if "success" in status_lower:
        if output_bytes_captured is not None and output_bytes_captured > 0:
            return f"OK ({output_bytes_captured}B)"
        return "OK"

    if "skip" in status_lower:
        return "SKIPPED"

    return status or "UNKNOWN"


def _build_digest_lines(output: str | None, max_lines: int = 5) -> tuple[str, ...]:
    """Extract most useful output lines.

    Args:
        output: Output text to process
        max_lines: Maximum number of lines to return

    Returns:
        Tuple of useful output lines
    """
    if not output:
        return ()

    lines = output.split("\n")
    # Filter empty lines and strip whitespace
    non_empty = [line.strip() for line in lines if line.strip()]

    if not non_empty:
        return ()

    # Return up to max_lines
    result = non_empty[:max_lines]
    truncated = len(non_empty) > max_lines

    if truncated:
        # Add truncation indicator as last line
        excess = len(non_empty) - max_lines
        result = list(result)
        result.append(f"[+{excess} more lines]")

    return tuple(result)


def build_result_digest(artifact: ExternalAnalysisArtifact) -> ResultDigest:
    """Build compact result digest from execution artifact.

    This function is deterministic and safe to call multiple times on the same artifact.

    Args:
        artifact: The execution artifact to digest

    Returns:
        ResultDigest with compact, reviewer-friendly fields
    """
    # Extract execution result from payload if available
    payload = artifact.payload or {}
    command_exit_code = payload.get("exitCode") or payload.get("exit_code")
    exit_code = _coerce_optional_int(command_exit_code)

    # Build primary digest
    result_digest = _build_result_digest(
        status=artifact.status.value if artifact.status else "",
        error_summary=artifact.error_summary,
        timed_out=artifact.timed_out,
        exit_code=exit_code,
        output_bytes_captured=artifact.output_bytes_captured,
    )

    # Extract digest lines from raw_output
    result_digest_lines = _build_digest_lines(artifact.raw_output, max_lines=5)

    # Extract stderr digest if available
    stderr_digest: str | None = None
    if artifact.raw_output and artifact.stderr_truncated is not None:
        # Try to separate stderr from combined output
        lines = artifact.raw_output.split("\n")
        # Heuristic: stderr lines often contain error indicators
        stderr_lines = [ln.strip() for ln in lines if ln.strip() and ("error" in ln.lower() or "fail" in ln.lower())]
        if stderr_lines:
            stderr_digest = stderr_lines[0][:100] if stderr_lines else None

    # Extract stdout digest if available
    stdout_digest: str | None = None
    if artifact.raw_output and artifact.stdout_truncated is not None:
        lines = artifact.raw_output.split("\n")
        # For stdout, take first non-empty line as digest
        non_error_lines = [ln.strip() for ln in lines if ln.strip() and "error" not in ln.lower()]
        if non_error_lines:
            stdout_digest = non_error_lines[0][:100]

    # Extract signal markers from raw output
    signal_markers = extract_signal_markers(artifact.raw_output)

    # Classify failure
    failure_class = classify_failure(
        stderr=artifact.error_summary,
        exit_code=exit_code,
        timed_out=artifact.timed_out,
    )

    return ResultDigest(
        result_digest=result_digest,
        result_digest_lines=result_digest_lines,
        stderr_digest=stderr_digest,
        stdout_digest=stdout_digest,
        signal_markers=signal_markers,
        failure_class=failure_class,
        exit_code=exit_code,
        output_bytes_captured=artifact.output_bytes_captured,
        stdout_truncated=artifact.stdout_truncated,
        stderr_truncated=artifact.stderr_truncated,
    )


def digest_to_dict(digest: ResultDigest) -> dict[str, object]:
    """Convert ResultDigest to a dictionary suitable for JSON export.

    Args:
        digest: The result digest to convert

    Returns:
        Dictionary with export-friendly field names
    """
    return {
        "result_digest": digest.result_digest,
        "result_digest_lines": list(digest.result_digest_lines),
        "stderr_digest": digest.stderr_digest,
        "stdout_digest": digest.stdout_digest,
        "signal_markers": list(digest.signal_markers),
        "failure_class": digest.failure_class,
        "exit_code": digest.exit_code,
        "output_bytes_captured": digest.output_bytes_captured,
        "stdout_truncated": digest.stdout_truncated,
        "stderr_truncated": digest.stderr_truncated,
    }


# =============================================================================
# ExecutionResultDigest - for planning context
# =============================================================================

# Maximum command description length for planning digest
_MAX_COMMAND_DESC_LENGTH = 200
# Maximum summary length for planning digest
_MAX_SUMMARY_LENGTH = 300
# Maximum signals count for planning digest
_MAX_SIGNALS_COUNT = 10


@dataclass(frozen=True)
class ExecutionResultDigest:
    """Compact digest of execution result for next-check planning context.

    This is a smaller, structured digest designed for feeding execution
    results into follow-up next-check planning. Unlike ResultDigest (for
    reviewer inspection), this includes provenance and context needed
    by the planner.

    Design constraints:
    - Keep digest small and boring
    - No raw 512KB command output in planning context
    - Include enough context for the planner to reason about next steps
    """

    # Provenance
    artifact_path: str | None
    """Path to the execution artifact on disk."""

    candidate_id: str | None
    """ID of the candidate that produced this execution."""

    candidate_description: str | None
    """Description of the command that was executed."""

    # Execution result
    status: str
    """Execution status (success, failed, etc.)."""

    usefulness_class: str | None
    """Usefulness classification (useful, partial, noisy, empty)."""

    # Target context
    target_cluster: str | None
    """Target cluster where command was executed."""

    target_context: str | None
    """Target context (usually namespace) for the command."""

    # Extracted content
    summary: str | None
    """Short summary of the result outcome."""

    signals: tuple[str, ...]
    """Extracted diagnostic signal markers from output."""

    # Truncation flags
    stdout_truncated: bool | None
    """Whether stdout was truncated during capture."""

    stderr_truncated: bool | None
    """Whether stderr was truncated during capture."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to serializable dict for planning context."""
        return {
            "artifactPath": self.artifact_path,
            "candidateId": self.candidate_id,
            "candidateDescription": self.candidate_description,
            "status": self.status,
            "usefulnessClass": self.usefulness_class,
            "targetCluster": self.target_cluster,
            "targetContext": self.target_context,
            "summary": self.summary,
            "signals": list(self.signals),
            "stdoutTruncated": self.stdout_truncated,
            "stderrTruncated": self.stderr_truncated,
        }

    @classmethod
    def from_artifact(
        cls,
        artifact: ExternalAnalysisArtifact,
        candidate_id: str | None = None,
        candidate_description: str | None = None,
    ) -> ExecutionResultDigest:
        """Build ExecutionResultDigest from an ExternalAnalysisArtifact.

        Args:
            artifact: The execution artifact to digest
            candidate_id: Optional ID of the candidate that produced this execution
            candidate_description: Optional description of the command executed

        Returns:
            ExecutionResultDigest with compact, planning-friendly fields
        """
        # Extract command from payload if available
        command: str | None = None
        if artifact.payload:
            raw_command = artifact.payload.get("command") or artifact.payload.get("commandText")
            if isinstance(raw_command, str):
                command = raw_command

        # Use provided description or derive from command/summary
        description = candidate_description
        if description is None and command:
            description = command if len(command) <= _MAX_COMMAND_DESC_LENGTH else command[:_MAX_COMMAND_DESC_LENGTH] + "…"
        elif description is None and artifact.summary:
            description = artifact.summary[:_MAX_COMMAND_DESC_LENGTH]

        # Build compact summary
        summary: str | None = None
        if artifact.usefulness_class:
            usefulness = artifact.usefulness_class.value if hasattr(artifact.usefulness_class, 'value') else str(artifact.usefulness_class)
            summary = f"[{usefulness}]"
        if artifact.summary:
            summary = f"{summary} {artifact.summary}" if summary else artifact.summary
            summary = summary[:_MAX_SUMMARY_LENGTH] if len(summary) > _MAX_SUMMARY_LENGTH else summary

        # Extract signal markers from raw output
        signals = extract_signal_markers(artifact.raw_output)[:_MAX_SIGNALS_COUNT]

        return cls(
            artifact_path=artifact.artifact_path,
            candidate_id=candidate_id,
            candidate_description=description,
            status=artifact.status.value if artifact.status else "unknown",
            usefulness_class=(
                artifact.usefulness_class.value if artifact.usefulness_class and hasattr(artifact.usefulness_class, 'value')
                else str(artifact.usefulness_class) if artifact.usefulness_class else None
            ),
            target_cluster=artifact.cluster_label or None,
            target_context=None,  # Would need to extract from payload/context
            summary=summary,
            signals=signals,
            stdout_truncated=artifact.stdout_truncated,
            stderr_truncated=artifact.stderr_truncated,
        )


def build_execution_result_digest(
    artifact: ExternalAnalysisArtifact,
    candidate_id: str | None = None,
    candidate_description: str | None = None,
) -> ExecutionResultDigest:
    """Build compact execution result digest for planning context.

    This function creates a small, structured digest from an execution
    artifact suitable for feeding into next-check planning. It extracts
    key information while avoiding large raw output.

    Args:
        artifact: The execution artifact to digest
        candidate_id: Optional ID of the candidate that produced this execution
        candidate_description: Optional description of the command executed

    Returns:
        ExecutionResultDigest with compact, planning-friendly fields

    Example:
        >>> artifact = ExternalAnalysisArtifact(...)
        >>> digest = build_execution_result_digest(artifact)
        >>> # digest.candidate_description
        >>> # digest.signals
        >>> # digest.summary
    """
    return ExecutionResultDigest.from_artifact(artifact, candidate_id, candidate_description)


def build_execution_result_digests(
    artifacts: tuple[ExternalAnalysisArtifact, ...] | list[ExternalAnalysisArtifact],
    candidate_ids: tuple[str | None, ...] | None = None,
    candidate_descriptions: tuple[str | None, ...] | None = None,
) -> tuple[ExecutionResultDigest, ...]:
    """Build execution result digests from multiple artifacts.

    Args:
        artifacts: Sequence of execution artifacts to digest
        candidate_ids: Optional tuple of candidate IDs corresponding to artifacts
        candidate_descriptions: Optional tuple of candidate descriptions

    Returns:
        Tuple of ExecutionResultDigest for each artifact

    Note:
        If candidate_ids or candidate_descriptions are provided, they must have
        the same length as artifacts. Missing values are treated as None.
    """
    digests: list[ExecutionResultDigest] = []
    for i, artifact in enumerate(artifacts):
        cid = candidate_ids[i] if candidate_ids and i < len(candidate_ids) else None
        cdesc = candidate_descriptions[i] if candidate_descriptions and i < len(candidate_descriptions) else None
        digests.append(build_execution_result_digest(artifact, cid, cdesc))
    return tuple(digests)
