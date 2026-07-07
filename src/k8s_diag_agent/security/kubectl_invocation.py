"""Invocation metadata tracking for kubectl subprocess execution."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field

_logger = logging.getLogger(__name__)

# Namespace pattern for detection
_ALL_NAMESPACES_FLAG = frozenset({"--all-namespaces", "-A"})

# Default timeout for kubectl commands
DEFAULT_TIMEOUT_SECONDS = 60

# Run label for kubectl invocation logs
_KUBECTL_RUN_LABEL = "kubectl-invocation"


@dataclass
class KubectlInvocation:
    """Structured metadata for a kubectl invocation."""

    # Command components
    argv: tuple[str, ...] = field(default_factory=tuple)
    # Parsed metadata
    namespace: str | None = None  # None means all-namespaces
    is_all_namespaces: bool = False
    resource_kind: str | None = None
    output_format: str | None = None
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    run_id: str | None = None
    # Execution metadata
    started_at: float | None = None
    completed_at: float | None = None
    elapsed_seconds: float | None = None
    returncode: int | None = None
    signal: int | None = None
    max_rss_kb: int | None = None
    stdout_bytes: int | None = None
    stderr_bytes: int | None = None
    failed: bool = False
    error_message: str | None = None

    @classmethod
    def from_command(
        cls,
        command: Sequence[str],
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        run_id: str | None = None,
    ) -> KubectlInvocation:
        """Parse a kubectl command into structured invocation metadata."""
        argv = tuple(command)
        namespace: str | None = None
        is_all_namespaces = False
        resource_kind: str | None = None
        output_format: str | None = None

        # Parse command structure
        i = 1  # Skip 'kubectl'
        while i < len(argv):
            arg = argv[i]

            # Handle --all-namespaces / -A
            if arg in _ALL_NAMESPACES_FLAG:
                is_all_namespaces = True
                i += 1
                continue

            # Handle -n / --namespace
            if arg in ("-n", "--namespace"):
                if i + 1 < len(argv):
                    namespace = argv[i + 1]
                    i += 2
                else:
                    i += 1
                continue

            # Handle -n= / --namespace= (compact form)
            if arg.startswith("-n="):
                namespace = arg[3:]
                i += 1
                continue
            if arg.startswith("--namespace="):
                namespace = arg[12:]
                i += 1
                continue

            # Handle -o / --output
            if arg in ("-o", "--output"):
                if i + 1 < len(argv):
                    output_format = argv[i + 1]
                    i += 2
                else:
                    i += 1
                continue

            # Handle -o= / --output= (compact form)
            if arg.startswith("-o="):
                output_format = arg[3:]
                i += 1
                continue
            if arg.startswith("--output="):
                output_format = arg[9:]
                i += 1
                continue

            # First non-flag argument after 'kubectl' is typically the verb
            # Second non-flag argument is typically the resource kind
            if not arg.startswith("-") and resource_kind is None and arg not in (
                "get",
                "describe",
                "logs",
                "top",
                "apply",
                "delete",
                "patch",
                "replace",
                "create",
                "edit",
                "label",
                "annotate",
                "rollout",
                "scale",
                "version",
                "cluster-info",
                "api-resources",
                "api-versions",
                "config",
                "cordon",
                "uncordon",
                "drain",
                "taint",
                "debug",
                "cp",
                "exec",
                "port-forward",
                "proxy",
                "attach",
            ):
                resource_kind = arg

            i += 1

        return cls(
            argv=argv,
            namespace=namespace,
            is_all_namespaces=is_all_namespaces,
            resource_kind=resource_kind,
            output_format=output_format,
            timeout_seconds=timeout_seconds,
            run_id=run_id,
        )

    def to_log_dict(self) -> dict:
        """Convert to dict for structured logging."""
        return {
            "event": "kubectl_invocation",
            "argv": list(self.argv),
            "namespace": self.namespace,
            "all_namespaces": self.is_all_namespaces,
            "resource_kind": self.resource_kind,
            "output_format": self.output_format,
            "timeout_seconds": self.timeout_seconds,
            "run_id": self.run_id,
            "elapsed_seconds": self.elapsed_seconds,
            "returncode": self.returncode,
            "signal": self.signal,
            "max_rss_kb": self.max_rss_kb,
            "stdout_bytes": self.stdout_bytes,
            "stderr_bytes": self.stderr_bytes,
            "failed": self.failed,
            "error_message": self.error_message,
        }


# INVARIANT: K9B_DEBUG_UNSTRUCTURED_LOGS must be absent or "false" in scheduler runtime.
# This env var is an escape hatch for local debugging only and must never be set
# in production scheduler deployments. Setting it to "true" will emit unstructured
# logs and break the runtime contract (UI warning counts, log queryability).


def log_kubectl_invocation(
    invocation: KubectlInvocation,
    level: str,
    message: str,
) -> None:
    """Log kubectl invocation as a JSONL runtime event only.

    Runtime path emits exactly one scheduler-visible log record per event,
    and it is JSONL. This is the contract for runtime monitoring and UI
    warning counts (12-factor logging / event stream).

    For local debugging, set K9B_DEBUG_UNSTRUCTURED_LOGS=true (NOT in scheduler).
    See module-level INVARIANT about this env var.
    """
    import os

    # Import here to avoid circular import between structured_logging and security modules
    from ..structured_logging import emit_structured_log

    log_data = invocation.to_log_dict()

    # Emit structured log for runtime contract compliance (JSONL-only)
    emit_structured_log(
        component="kubectl-invocation",
        message=message,
        run_label=_KUBECTL_RUN_LABEL,
        severity=level.upper(),
        **log_data,
    )

    # Debug-only: emit standard logger for local debugging (NOT in scheduler runtime path)
    if os.environ.get("K9B_DEBUG_UNSTRUCTURED_LOGS") == "true":
        log_level = getattr(logging, level.upper(), logging.DEBUG)
        if _logger.isEnabledFor(log_level):
            # Use a compact summary for the log message
            summary_parts = [
                f"argv={list(invocation.argv[:4])}..."
                if len(invocation.argv) > 4
                else f"argv={list(invocation.argv)}",
            ]
            if invocation.resource_kind:
                summary_parts.append(f"kind={invocation.resource_kind}")
            if invocation.namespace:
                summary_parts.append(f"ns={invocation.namespace}")
            elif invocation.is_all_namespaces:
                summary_parts.append("ns=all")
            if invocation.output_format:
                summary_parts.append(f"fmt={invocation.output_format}")
            summary_parts.append(f"timeout={invocation.timeout_seconds}s")
            if invocation.run_id:
                summary_parts.append(f"run_id={invocation.run_id[:8]}")

            summary = " | ".join(summary_parts)

            _logger.log(
                log_level,
                f"{message}: {summary}",
                extra={"kubectl_invocation": log_data},
            )
