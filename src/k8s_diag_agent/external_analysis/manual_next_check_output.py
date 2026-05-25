"""Output capture and summarization helpers for manual next-check execution."""

from __future__ import annotations

_OUTPUT_LIMIT = 8192


def _capture_output(
    value: str | bytes | None,
    limit: int = _OUTPUT_LIMIT,
) -> tuple[str | None, bool, int]:
    """Capture and truncate command output.

    Args:
        value: The raw output string, bytes, or None.
        limit: Maximum character length before truncation.

    Returns:
        A tuple of (trimmed_text, was_truncated, byte_count).
    """
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


def _summarize_outputs(
    stdout: str | bytes | None,
    stderr: str | bytes | None,
) -> tuple[str | None, str | None, str | None, bool, bool, int]:
    """Summarize stdout and stderr with truncation tracking.

    Args:
        stdout: Standard output from command execution.
        stderr: Standard error from command execution.

    Returns:
        A 6-tuple of (stdout_text, stderr_text, combined, stdout_truncated,
        stderr_truncated, total_bytes).
    """
    stdout_text, stdout_truncated, stdout_bytes = _capture_output(stdout)
    stderr_text, stderr_truncated, stderr_bytes = _capture_output(stderr)
    combined = "\n".join(filter(None, (stdout_text, stderr_text))) or None
    return stdout_text, stderr_text, combined, stdout_truncated, stderr_truncated, (
        stdout_bytes + stderr_bytes
    )
