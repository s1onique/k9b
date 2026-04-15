"""Compact result-digest generation for usefulness review exports.

This module provides deterministic, compact digests of execution results
for external reviewer judgment without dumping full stdout/stderr.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

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


# Signal markers to extract from K8s diagnostic output
_SIGNAL_MARKERS: list[tuple[str, str]] = [
    # Pod status issues
    (r"CrashLoopBackOff", "CrashLoopBackOff"),
    (r"ImagePullBackOff", "ImagePullBackOff"),
    (r"ErrImagePull", "ErrImagePull"),
    (r"Evicted", "Evicted"),
    (r"OOMKilled", "OOMKilled"),
    (r"Terminating", "Terminating"),
    (r"FailedScheduling", "FailedScheduling"),
    # Probe/ readiness issues
    (r"ReadinessProbeFailed", "ReadinessProbeFailed"),
    (r"LivenessProbeFailed", "LivenessProbeFailed"),
    (r"StartupProbeFailed", "StartupProbeFailed"),
    (r"probe\s+fail", "ProbeFailed"),
    # Permission/ security issues
    (r"forbidden", "Forbidden"),
    (r"unauthorized", "Unauthorized"),
    (r"permission denied", "PermissionDenied"),
    # Not found / missing
    (r"not found", "NotFound"),
    (r"doesn't exist", "NotFound"),
    (r"no such host", "DNSError"),
    (r"connection refused", "ConnectionRefused"),
    # TLS / cert errors
    (r"TLS|certificate|ssl", "TLSCertError"),
    # Timeout
    (r"timeout|timed out", "Timeout"),
    # Resource issues
    (r"insufficient|quota", "ResourceQuota"),
    (r"memory limit|cpu limit", "ResourceLimit"),
]


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


def _extract_signal_markers(output: str | None) -> tuple[str, ...]:
    """Extract diagnostic signal markers from output text.

    Args:
        output: Combined output text to scan

    Returns:
        Tuple of detected marker names (deduplicated, order-stable)
    """
    if not output:
        return ()

    markers: list[str] = []
    seen: set[str] = set()

    for pattern_str, marker_name in _SIGNAL_MARKERS:
        if marker_name in seen:
            continue
        if re.search(pattern_str, output, re.IGNORECASE):
            markers.append(marker_name)
            seen.add(marker_name)

    return tuple(markers)


def _classify_failure(stderr: str | None, exit_code: int | None, timed_out: bool | None) -> str | None:
    """Classify the failure reason from execution context.

    Args:
        stderr: Stderr output text
        exit_code: Command exit code
        timed_out: Whether command timed out

    Returns:
        Failure classification string or None
    """
    if timed_out:
        return "timeout"

    if stderr:
        stderr_lower = stderr.lower()
        if "not found" in stderr_lower or "no such host" in stderr_lower:
            return "not_found"
        if "forbidden" in stderr_lower or "permission" in stderr_lower:
            return "permission_denied"
        if "timeout" in stderr_lower or "timed out" in stderr_lower:
            return "timeout"
        if "connection refused" in stderr_lower:
            return "connection_refused"
        if "tls" in stderr_lower or "certificate" in stderr_lower:
            return "tls_error"
        if "error" in stderr_lower:
            return "command_error"

    if exit_code is not None and exit_code != 0:
        return f"exit_{exit_code}"

    return None


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
    signal_markers = _extract_signal_markers(artifact.raw_output)

    # Classify failure
    failure_class = _classify_failure(
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
