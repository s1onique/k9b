"""Bounded kubectl logs collection with strict output limits.

This module provides kubectl logs collection with:
1. Hard byte caps on stdout/stderr
2. Kubernetes-side --limit-bytes enforcement
3. Line/time bounds (--tail, --since)
4. Truncation metadata in result
5. Memory-safe incremental reading

Non-goals:
- Streaming log collection (future work via K8s Python client)
- Log tailing/following (not needed for health loop snapshots)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .kubectl_bounded import run_bounded as _run_bounded
from .kubectl_errors import KubectlExecutionError

if TYPE_CHECKING:
    pass

_logger = logging.getLogger(__name__)

# Defaults for pod log collection
DEFAULT_LOG_TIMEOUT_SECONDS = 30
DEFAULT_LOG_MAX_BYTES = 1 * 1024 * 1024  # 1 MiB per pod/container
DEFAULT_LOG_TAIL_LINES = 500
DEFAULT_LOG_STDERR_MAX_BYTES = 256 * 1024  # 256 KiB


@dataclass(frozen=True)
class BoundedKubectlLogsResult:
    """Result from bounded kubectl logs collection."""

    argv: tuple[str, ...]
    returncode: int
    stdout: bytes
    stderr: bytes
    stdout_truncated: bool
    stderr_truncated: bool
    timed_out: bool
    duration_seconds: float
    stdout_bytes_read: int
    stderr_bytes_read: int
    limit_bytes: int | None
    tail_lines: int | None
    since_hours: int | None

    @property
    def stdout_text(self) -> str:
        """Decode stdout with replacement for invalid UTF-8."""
        return self.stdout.decode("utf-8", errors="replace")

    @property
    def stderr_text(self) -> str:
        """Decode stderr with replacement for invalid UTF-8."""
        return self.stderr.decode("utf-8", errors="replace")

    def to_truncation_metadata(self) -> dict[str, object]:
        """Convert to artifact-compatible truncation metadata."""
        return {
            "kind": "kubectl_output_truncated",
            "command_kind": "pod_logs",
            "stdout_truncated": self.stdout_truncated,
            "stderr_truncated": self.stderr_truncated,
            "stdout_bytes_read": self.stdout_bytes_read,
            "max_stdout_bytes": self.limit_bytes or 0,
            "timed_out": self.timed_out,
            "duration_seconds": round(self.duration_seconds, 2),
        }


def build_bounded_kubectl_logs(
    *,
    namespace: str,
    pod: str,
    container: str | None = None,
    tail_lines: int = DEFAULT_LOG_TAIL_LINES,
    limit_bytes: int = DEFAULT_LOG_MAX_BYTES,
    since_hours: int | None = None,
    previous: bool = False,
    context: str | None = None,
) -> list[str]:
    """Build a bounded kubectl logs command with Kubernetes-side limits.

    Args:
        namespace: Kubernetes namespace
        pod: Pod name
        container: Container name (optional for single-container pods)
        tail_lines: Number of recent lines to fetch
        limit_bytes: Maximum bytes to fetch from server
        since_hours: Fetch logs from the last N hours
        previous: Fetch previous (crashed) container logs
        context: Kubernetes context

    Returns:
        List of command arguments for run_bounded_kubectl_logs()
    """
    cmd = ["kubectl", "logs"]

    if context:
        cmd.extend(["--context", context])

    if previous:
        cmd.append("--previous")

    if container:
        cmd.extend(["-c", container])

    cmd.extend(["-n", namespace, pod])

    # Kubernetes-side bounds (critical for safety)
    cmd.extend(["--limit-bytes", str(limit_bytes)])
    cmd.extend(["--tail", str(tail_lines)])

    if since_hours is not None:
        cmd.extend(["--since", f"{since_hours}h"])

    return cmd


def run_bounded_kubectl_logs(
    *,
    argv: list[str],
    timeout_seconds: float = DEFAULT_LOG_TIMEOUT_SECONDS,
    max_stdout_bytes: int = DEFAULT_LOG_MAX_BYTES,
    max_stderr_bytes: int = DEFAULT_LOG_STDERR_MAX_BYTES,
    env: dict[str, str] | None = None,
) -> BoundedKubectlLogsResult:
    """Execute kubectl logs with bounded output and memory safety.

    This function:
    1. Uses subprocess.Popen for incremental reading
    2. Enforces independent stdout/stderr byte caps
    3. Kills child immediately on output cap violation
    4. Reports truncation metadata

    Args:
        argv: Command arguments (must start with kubectl logs)
        timeout_seconds: Execution timeout
        max_stdout_bytes: Maximum stdout bytes to retain
        max_stderr_bytes: Maximum stderr bytes to retain
        env: Environment variables

    Returns:
        BoundedKubectlLogsResult with output and metadata

    Raises:
        KubectlExecutionError: On non-zero exit or timeout
        KubectlOutputTooLargeError: If output exceeds max_stdout_bytes
    """
    import time

    if not argv or argv[0] != "kubectl":
        raise ValueError("Command must start with 'kubectl'")
    if len(argv) < 2 or argv[1] != "logs":
        raise ValueError("Command must be 'kubectl logs ...'")

    # Extract bounds for metadata and validation
    limit_bytes: int | None = None
    tail_lines: int | None = None
    since_hours: int | None = None
    since_time: str | None = None

    for i, arg in enumerate(argv):
        if arg == "--limit-bytes" and i + 1 < len(argv):
            limit_bytes = int(argv[i + 1])
        elif arg.startswith("--limit-bytes="):
            limit_bytes = int(arg.split("=", 1)[1])
        elif arg == "--tail" and i + 1 < len(argv):
            tail_lines = int(argv[i + 1])
        elif arg.startswith("--tail="):
            tail_lines = int(arg.split("=", 1)[1])
        elif arg == "--since" and i + 1 < len(argv):
            since_val = argv[i + 1]
            if since_val.endswith("h"):
                since_hours = int(since_val[:-1])
        elif arg.startswith("--since="):
            since_val = arg.split("=", 1)[1]
            if since_val.endswith("h"):
                since_hours = int(since_val[:-1])
        elif arg == "--since-time" and i + 1 < len(argv):
            since_time = argv[i + 1]
        elif arg.startswith("--since-time="):
            since_time = arg.split("=", 1)[1]

    # Fail-closed: validate required bounds are present
    if limit_bytes is None:
        raise ValueError(
            "kubectl logs argv must include --limit-bytes to prevent unbounded output. "
            "Use build_bounded_kubectl_logs() or add --limit-bytes=<N> to argv."
        )
    if limit_bytes <= 0:
        raise ValueError(f"--limit-bytes must be positive, got {limit_bytes}")

    # At least one time bound must be present
    has_time_bound = tail_lines is not None or since_hours is not None or since_time is not None
    if not has_time_bound:
        raise ValueError(
            "kubectl logs argv must include at least one time bound: "
            "--tail=<N>, --since=<Nh>, or --since-time=<RFC3339>. "
            "Use build_bounded_kubectl_logs() or add one of these flags to argv."
        )

    # Validate tail_lines if present
    if tail_lines is not None and tail_lines <= 0:
        raise ValueError(f"--tail must be positive, got {tail_lines}")

    start_time = time.monotonic()

    # Normalize env to satisfy run_bounded's dict[str, str] requirement
    run_env: dict[str, str] = env or {}
    result = _run_bounded(
        argv,
        max_stdout_bytes=max_stdout_bytes,
        max_stderr_bytes=max_stderr_bytes,
        timeout_seconds=int(timeout_seconds),
        env=run_env,
    )

    duration_seconds = time.monotonic() - start_time
    stdout_bytes_read = len(result.stdout)
    stderr_bytes_read = len(result.stderr)

    stdout_truncated = stdout_bytes_read >= max_stdout_bytes
    stderr_truncated = stderr_bytes_read >= max_stderr_bytes

    return BoundedKubectlLogsResult(
        argv=tuple(argv),
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
        timed_out=False,
        duration_seconds=duration_seconds,
        stdout_bytes_read=stdout_bytes_read,
        stderr_bytes_read=stderr_bytes_read,
        limit_bytes=limit_bytes,
        tail_lines=tail_lines,
        since_hours=since_hours,
    )


def collect_pod_logs_bounded(
    *,
    context: str | None,
    namespace: str,
    pod: str,
    container: str | None = None,
    tail_lines: int = DEFAULT_LOG_TAIL_LINES,
    limit_bytes: int = DEFAULT_LOG_MAX_BYTES,
    since_hours: int | None = None,
    previous: bool = False,
    timeout_seconds: float = DEFAULT_LOG_TIMEOUT_SECONDS,
) -> tuple[str, dict[str, object]]:
    """Collect pod logs with bounds and return (output, metadata).

    This is the primary entry point for health loop log collection.

    Args:
        context: Kubernetes context
        namespace: Namespace name
        pod: Pod name
        container: Container name
        tail_lines: Lines to fetch
        limit_bytes: Server-side byte limit
        since_hours: Time-based filtering
        previous: Get previous container logs
        timeout_seconds: Execution timeout

    Returns:
        Tuple of (output_text, truncation_metadata_dict)

    Raises:
        KubectlExecutionError: On command failure
    """
    import os

    cmd = build_bounded_kubectl_logs(
        namespace=namespace,
        pod=pod,
        container=container,
        tail_lines=tail_lines,
        limit_bytes=limit_bytes,
        since_hours=since_hours,
        previous=previous,
        context=context,
    )

    # Build environment
    env: dict[str, str] = {}
    env.update(os.environ)

    result = run_bounded_kubectl_logs(
        argv=cmd,
        timeout_seconds=timeout_seconds,
        max_stdout_bytes=limit_bytes,  # Match server-side limit
        max_stderr_bytes=DEFAULT_LOG_STDERR_MAX_BYTES,
        env=env,
    )

    if result.returncode != 0:
        error_msg = result.stderr_text.strip() or "kubectl logs failed"
        raise KubectlExecutionError(
            error_msg,
            command=cmd,
            returncode=result.returncode,
            elapsed_seconds=result.duration_seconds,
        )

    metadata = result.to_truncation_metadata()
    return result.stdout_text, metadata


__all__ = [
    "DEFAULT_LOG_TIMEOUT_SECONDS",
    "DEFAULT_LOG_MAX_BYTES",
    "DEFAULT_LOG_TAIL_LINES",
    "DEFAULT_LOG_STDERR_MAX_BYTES",
    "BoundedKubectlLogsResult",
    "build_bounded_kubectl_logs",
    "run_bounded_kubectl_logs",
    "collect_pod_logs_bounded",
]
