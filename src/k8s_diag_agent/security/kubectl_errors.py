"""Error types for kubectl subprocess execution."""

from __future__ import annotations

from collections.abc import Sequence

# Sentinel error for output size violations
# Used to distinguish intentional size limits from other failures
KUBECTL_OUTPUT_TOO_LARGE = "kubectl_output_too_large"


class KubectlOutputTooLargeError(RuntimeError):
    """Raised when kubectl command output exceeds the configured limit.

    This is a fail-closed error to prevent unbounded memory growth
    when collecting large resources (events, pods) in busy clusters.
    """

    def __init__(self, command: Sequence[str], actual_bytes: int, limit_bytes: int):
        self.command = list(command)
        self.actual_bytes = actual_bytes
        self.limit_bytes = limit_bytes
        super().__init__(
            f"kubectl output ({actual_bytes:,} bytes) exceeds limit ({limit_bytes:,} bytes). "
            f"Command: {' '.join(command[:3])}... "
            f"Consider using --chunk-size, --field-selector, or label selectors."
        )


class KubectlExecutionError(RuntimeError):
    """Raised when kubectl command fails with telemetry."""

    def __init__(
        self,
        message: str,
        command: Sequence[str],
        returncode: int | None = None,
        signal: int | None = None,
        elapsed_seconds: float | None = None,
        max_rss_kb: int | None = None,
    ):
        self.command = list(command)
        self.returncode = returncode
        self.signal = signal
        self.elapsed_seconds = elapsed_seconds
        self.max_rss_kb = max_rss_kb
        super().__init__(message)
