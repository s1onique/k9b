"""Signal extraction and failure classification for result digests.

Extracted from result_digest.py to reduce file size.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


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


def extract_signal_markers(output: str | None) -> tuple[str, ...]:
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


def classify_failure(
    stderr: str | None, exit_code: int | None, timed_out: bool | None
) -> str | None:
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


def truncate_signals(signals: tuple[str, ...], max_count: int) -> tuple[str, ...]:
    """Truncate signals tuple to maximum count.

    Args:
        signals: Input signals tuple
        max_count: Maximum number of signals to return

    Returns:
        Truncated signals tuple
    """
    return signals[:max_count]