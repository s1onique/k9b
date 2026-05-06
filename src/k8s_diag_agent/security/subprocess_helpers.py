"""Subprocess helpers for security-conscious stderr capture and safe logging.

This module provides utilities for handling subprocess stderr in diagnostic paths
while avoiding secret leakage in logs.

Key design principles:
- stderr is captured, not discarded, for operational forensics
- stderr tail is bounded to prevent log bloat
- output sanitization removes sensitive patterns before inclusion in errors/logs
- command summaries redact secret-bearing tokens
- failure logging includes safe metadata only
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from typing import Any

# Maximum stderr tail length to prevent log bloat
_STDERR_TAIL_LIMIT = 4000

# Secret-bearing argument patterns that should be redacted
_SECRET_ARG_PATTERNS = (
    "--token",
    "--bearer",
    "--password",
    "--secret",
    "--credentials",
    "--kubeconfig",
    "--auth",
)

# Sensitive patterns that may appear in stderr output
# These patterns are redacted when found in stderr to prevent credential leakage
_SENSITIVE_OUTPUT_PATTERNS: list[re.Pattern[str]] = [
    # Bearer token patterns
    re.compile(r"(?i)bearer\s+[A-Za-z0-9\-_.=]+"),
    re.compile(r"(?i)Authorization:\s*Bearer\s+[^\r\n]+"),
    # Authorization headers (any scheme: Basic, Bearer, Token, etc.) - match until end of line
    re.compile(r"(?i)Authorization:\s+[^\r\n]+"),
    # Token flag values
    re.compile(r'(?i)--token[=:]"?[A-Za-z0-9\-_.=]+"?'),
    re.compile(r"(?i)token[=:][\s]*['\"]?[A-Za-z0-9\-_.=]+['\"]?"),
    # Kubeconfig paths (may contain cluster info)
    re.compile(r"(?i)--kubeconfig[=:]?[^\s]+"),
    re.compile(r"(?i)kubeconfig[=:][^\s]+"),
    # Secret values in JSON/YAML (double-quoted)
    re.compile(r'(?i)"(password|passwd|pwd|secret|token|apikey|api_key|bearer)"\s*:\s*"[^"]*"'),
    # Secret values in JSON/YAML (single-quoted)
    re.compile(r"(?i)'(password|passwd|pwd|secret|token|apikey|api_key|bearer)'\s*:\s*'[^']*'"),
    # Key: value patterns for credentials (key=value or key: value format)
    re.compile(r"(?i)(password|passwd|pwd|secret|token|apikey|api_key|bearer)\s*[=:]\s*['\"]?[A-Za-z0-9\-_.=]+['\"]?"),
    # API keys
    re.compile(r"(?i)api[_-]?key\s*[=:]\s*['\"]?[A-Za-z0-9\-_.=]+['\"]?"),
    # Client secrets
    re.compile(r"(?i)client[_-]?secret\s*[=:]\s*['\"]?[A-Za-z0-9\-_.=]+['\"]?"),
    # Access tokens
    re.compile(r"(?i)access[_-]?token\s*[=:]\s*['\"]?[A-Za-z0-9\-_.=]+['\"]?"),
]

# Placeholder for redacted values
_REDACTED = "[REDACTED]"

_logger = logging.getLogger(__name__)


def _stderr_tail(stderr: bytes | str | None, limit: int = _STDERR_TAIL_LIMIT) -> str:
    """Extract a bounded tail from stderr output.

    Args:
        stderr: Raw stderr output (bytes or str)
        limit: Maximum characters to return (default 4000)

    Returns:
        Bounded stderr tail string, or empty string if stderr is None/empty
    """
    if stderr is None:
        return ""

    # Decode bytes if needed
    if isinstance(stderr, bytes):
        try:
            stderr = stderr.decode("utf-8", errors="replace")
        except Exception:  # REVIEWED: safe fallback for non-UTF8 stderr
            return "[binary stderr]"

    # Normalize newlines for consistent output
    stderr = stderr.replace("\r\n", "\n").replace("\r", "\n")

    # Get the tail
    if len(stderr) > limit:
        return stderr[-limit:]
    return stderr


def _sanitize_output(output: str | None) -> str:
    """Sanitize subprocess output to remove sensitive patterns.

    Removes bearer tokens, authorization headers, API keys, kubeconfig paths,
    and other credential-like values from output before inclusion in errors,
    logs, or artifacts.

    Args:
        output: Raw output string to sanitize (None or empty returns empty string)

    Returns:
        Sanitized output with sensitive patterns replaced by [REDACTED]
    """
    if not output:
        return ""

    sanitized = output
    for pattern in _SENSITIVE_OUTPUT_PATTERNS:
        sanitized = pattern.sub(_REDACTED, sanitized)
    return sanitized


def sanitize_subprocess_error(
    message: str,
    stderr: bytes | str | None,
    *,
    max_length: int | None = None,
) -> str:
    """Create a safe error message from subprocess failure.

    Combines error message with sanitized and truncated stderr output.
    Ensures no bearer tokens, kubeconfig paths, or credential values leak
    into the error message.

    Args:
        message: Base error message
        stderr: Raw stderr output (will be sanitized and truncated)
        max_length: Optional maximum length for stderr tail (default: 2000)

    Returns:
        Safe error message with sanitized stderr
    """
    if stderr is None:
        return message

    # First, truncate to limit
    stderr_str = _stderr_tail(stderr, limit=max_length or 2000)
    if not stderr_str:
        return message

    # Then sanitize to remove any sensitive patterns that might be in stderr
    sanitized_stderr = _sanitize_output(stderr_str)

    # Combine message with sanitized stderr
    return f"{message}: {sanitized_stderr}"


def _safe_command_summary(args: Sequence[str]) -> str:
    """Generate a safe command summary without secret-bearing arguments.

    Redacts tokens, passwords, and other sensitive arguments that might
    appear in kubectl/helm command arguments.

    Args:
        args: Command argument sequence

    Returns:
        Safe command summary string with secrets redacted
    """
    if not args:
        return ""

    # Get command family (first argument)
    cmd_parts = [args[0]] if args else []

    # Check remaining arguments for secrets
    for i, arg in enumerate(args[1:], start=1):
        # Check if this arg contains secret patterns
        arg_lower = arg.lower()
        is_secret = any(
            pattern in arg_lower for pattern in _SECRET_ARG_PATTERNS
        )

        if is_secret:
            cmd_parts.append("[REDACTED]")
        elif arg.startswith("--"):
            # Safe to include flag names but not values
            if "=" in arg:
                # Flag with value like --context=foo -> include flag name only
                flag_name = arg.split("=", 1)[0]
                cmd_parts.append(flag_name)
                cmd_parts.append("[VALUE]")
            else:
                cmd_parts.append(arg)
        else:
            cmd_parts.append(arg)

    return " ".join(cmd_parts)


def _log_subprocess_failure(
    *,
    operation: str,
    command_args: Sequence[str] | None,
    return_code: int | None,
    stderr: bytes | str | None,
    run_id: str | None = None,
    cluster_label: str | None = None,
    logger: logging.Logger | None = None,
    exc_info: bool = False,
    severity: str = "WARNING",
) -> None:
    """Log subprocess failure with safe metadata.

    Captures stderr tail and safe command summary while avoiding secret leakage.
    Does NOT log raw kubeconfig, bearer tokens, environment variables, or
    request bodies.

    Args:
        operation: Operation name (e.g., "port_forward", "kubectl", "helm")
        command_args: Full command arguments (will be sanitized)
        return_code: Process exit code
        stderr: Process stderr output (will be tail-bounded)
        run_id: Optional run identifier
        cluster_label: Optional cluster label for context
        logger: Logger to use (defaults to module logger)
        exc_info: Whether to include exception traceback
        severity: Log severity level
    """
    target_logger = logger or _logger

    # Build safe metadata
    metadata: dict[str, Any] = {
        "operation": operation,
        "return_code": return_code,
    }

    # Add stderr tail if available
    stderr_tail = _stderr_tail(stderr)
    if stderr_tail:
        metadata["stderr_tail"] = stderr_tail

    # Add safe command summary if command_args provided
    if command_args:
        metadata["command_summary"] = _safe_command_summary(command_args)

    # Add optional context
    if run_id:
        metadata["run_id"] = run_id
    if cluster_label:
        metadata["cluster_label"] = cluster_label

    # Log the failure
    target_logger.log(
        getattr(logging, severity.upper(), logging.WARNING),
        f"Subprocess {operation} failed with return code {return_code}",
        exc_info=exc_info,
        extra={"metadata": metadata},
    )