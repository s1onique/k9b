"""Bounded kubectl subprocess execution with memory-safe collection.

This module provides hardened kubectl subprocess execution that:
1. Logs every kubectl invocation before execution with structured metadata
2. Adds subprocess RSS/resource telemetry on failure
3. Replaces unbounded kubectl JSON collection with bounded collection
4. Adds hard output limits (max stdout/stderr bytes)
5. Uses --chunk-size and --request-timeout for safe collection
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from collections.abc import Sequence
from typing import TYPE_CHECKING

from .kubectl_bounded import MAX_STDERR_BYTES, MAX_STDOUT_BYTES
from .kubectl_bounded import run_bounded as _run_bounded
from .kubectl_collect import (
    DEFAULT_CHUNK_SIZE,
    build_bounded_kubectl_get,
    collect_events_bounded,
    collect_pods_bounded,
)
from .kubectl_errors import (
    KUBECTL_OUTPUT_TOO_LARGE,
    KubectlExecutionError,
    KubectlOutputTooLargeError,
)
from .kubectl_invocation import (
    DEFAULT_TIMEOUT_SECONDS,
    KubectlInvocation,
    log_kubectl_invocation,
)
from .subprocess_helpers import sanitize_subprocess_error

if TYPE_CHECKING:
    from ..kubernetes_auth import AuthMode

_logger = logging.getLogger(__name__)

# Placeholder for run_id context
_run_id_context: str | None = None


def set_run_id_context(run_id: str | None) -> None:
    """Set the run_id context for kubectl invocations."""
    global _run_id_context
    _run_id_context = run_id


def _get_max_rss_kb() -> int | None:
    """Get the max RSS for the current process in KB."""
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF)
        return usage.ru_maxrss
    except (ImportError, AttributeError):
        return None


def run_kubectl(
    command: Sequence[str],
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    max_stdout_bytes: int = MAX_STDOUT_BYTES,
    max_stderr_bytes: int = MAX_STDERR_BYTES,
    run_id: str | None = None,
    chunk_size: int | None = DEFAULT_CHUNK_SIZE,
    auth_mode: AuthMode | None = None,
    env_overrides: dict[str, str | None] | None = None,
) -> str:
    """Execute a kubectl command with bounded output and structured logging.

    This is the primary entry point for kubectl subprocess execution in k9b.
    It provides:
    1. Structured logging before execution
    2. Hard output limits to prevent memory growth
    3. Resource telemetry on failure
    4. Automatic --chunk-size and --request-timeout injection
    """
    if run_id is None:
        run_id = _run_id_context

    invocation = KubectlInvocation.from_command(command, timeout_seconds, run_id)
    cmd_list = _inject_timeout(command, timeout_seconds)

    if chunk_size is not None:
        cmd_list = _maybe_inject_chunk_size(cmd_list)

    log_kubectl_invocation(invocation, "INFO", "Starting kubectl invocation")

    start_time = time.monotonic()
    invocation.started_at = start_time

    env = _build_environment(auth_mode, env_overrides)
    rss_before_kb = _get_max_rss_kb()

    try:
        result = _run_bounded(
            cmd_list,
            max_stdout_bytes=max_stdout_bytes,
            max_stderr_bytes=max_stderr_bytes,
            timeout_seconds=timeout_seconds,
            env=env,
        )

        elapsed = time.monotonic() - start_time
        invocation.completed_at = invocation.started_at + elapsed if invocation.started_at else None
        invocation.elapsed_seconds = elapsed
        invocation.returncode = result.returncode
        invocation.stdout_bytes = len(result.stdout) if result.stdout else 0
        invocation.stderr_bytes = len(result.stderr) if result.stderr else 0

        rss_after_kb = _get_max_rss_kb()
        if rss_after_kb is not None and rss_before_kb is not None:
            invocation.max_rss_kb = max(rss_before_kb, rss_after_kb)

        if result.returncode != 0:
            invocation.failed = True
            stderr_str = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
            invocation.error_message = sanitize_subprocess_error(
                f"`kubectl` exited {result.returncode}",
                stderr_str,
                max_length=500,
            )
            log_kubectl_invocation(
                invocation,
                "ERROR",
                f"kubectl failed with exit code {result.returncode}",
            )
            raise KubectlExecutionError(
                invocation.error_message,
                command=cmd_list,
                returncode=result.returncode,
                elapsed_seconds=elapsed,
                max_rss_kb=invocation.max_rss_kb,
            )

        log_kubectl_invocation(invocation, "DEBUG", f"kubectl completed successfully in {elapsed:.2f}s")

        return result.stdout.decode("utf-8", errors="replace")

    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - start_time
        invocation.completed_at = invocation.started_at + elapsed if invocation.started_at else None
        invocation.elapsed_seconds = elapsed
        invocation.failed = True
        invocation.error_message = f"kubectl timed out after {timeout_seconds}s"

        stderr_bytes = exc.stderr if exc.stderr else b""
        invocation.stderr_bytes = len(stderr_bytes)

        rss_after_kb = _get_max_rss_kb()
        if rss_after_kb is not None and rss_before_kb is not None:
            invocation.max_rss_kb = max(rss_before_kb, rss_after_kb)

        log_kubectl_invocation(invocation, "ERROR", f"kubectl timed out after {timeout_seconds}s")

        raise KubectlExecutionError(
            f"`kubectl` timed out after {timeout_seconds}s. "
            "Cluster may be unresponsive or under load.",
            command=cmd_list,
            elapsed_seconds=elapsed,
            max_rss_kb=invocation.max_rss_kb,
        ) from exc

    except FileNotFoundError as exc:
        elapsed = time.monotonic() - start_time
        invocation.completed_at = invocation.started_at + elapsed if invocation.started_at else None
        invocation.elapsed_seconds = elapsed
        invocation.failed = True
        invocation.error_message = "kubectl not found in PATH"

        log_kubectl_invocation(invocation, "ERROR", "kubectl not found")

        raise KubectlExecutionError(
            f"Command `{command[0]}` not found. Ensure kubectl is on PATH.",
            command=cmd_list,
            elapsed_seconds=elapsed,
        ) from exc

    except OSError as exc:
        elapsed = time.monotonic() - start_time
        invocation.completed_at = invocation.started_at + elapsed if invocation.started_at else None
        invocation.elapsed_seconds = elapsed
        invocation.failed = True
        invocation.error_message = str(exc)

        log_kubectl_invocation(invocation, "ERROR", f"OSError: {exc}")

        raise KubectlExecutionError(
            f"Failed to execute kubectl: {exc}. "
            "Check that the binary exists and matches the container CPU architecture.",
            command=cmd_list,
            elapsed_seconds=elapsed,
        ) from exc


def _inject_timeout(command: Sequence[str], timeout_seconds: int) -> list[str]:
    """Inject --request-timeout if not present in command."""
    cmd_list = list(command)

    has_timeout = any(
        arg.startswith("--request-timeout") or arg.startswith("--request-timeout=")
        for arg in cmd_list
    )

    if not has_timeout:
        cmd_list.append("--request-timeout")
        cmd_list.append(str(timeout_seconds))

    return cmd_list


def _maybe_inject_chunk_size(command: Sequence[str], chunk_size: int = 500) -> list[str]:
    """Inject --chunk-size for kubectl get commands if not present."""
    cmd_list = list(command)

    if len(cmd_list) < 2 or cmd_list[1] != "get":
        return cmd_list

    has_chunk_size = any(
        arg.startswith("--chunk-size") or arg.startswith("--chunk-size=")
        for arg in cmd_list
    )

    if not has_chunk_size:
        cmd_list.append("--chunk-size")
        cmd_list.append(str(chunk_size))

    return cmd_list


def _build_environment(
    auth_mode: AuthMode | None,
    env_overrides: dict[str, str | None] | None,
) -> dict[str, str]:
    """Build subprocess environment with auth mode settings."""
    env: dict[str, str] = {}
    env.update(os.environ)

    if auth_mode is not None:
        from ..kubernetes_auth import build_kubectl_env

        env_updates = build_kubectl_env(auth_mode)
        for key, value in env_updates.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value

    if env_overrides:
        for key, value in env_overrides.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value

    return env


__all__ = [
    "KUBECTL_OUTPUT_TOO_LARGE",
    "KubectlOutputTooLargeError",
    "KubectlExecutionError",
    "KubectlInvocation",
    "set_run_id_context",
    "run_kubectl",
    "build_bounded_kubectl_get",
    "collect_events_bounded",
    "collect_pods_bounded",
    "DEFAULT_TIMEOUT_SECONDS",
    "DEFAULT_CHUNK_SIZE",
    "MAX_STDOUT_BYTES",
    "MAX_STDERR_BYTES",
]
