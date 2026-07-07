"""Bounded subprocess execution for kubectl with streaming output capture."""

from __future__ import annotations

import select as _select
import subprocess
import time
from collections.abc import Sequence

from .kubectl_errors import KubectlOutputTooLargeError

# Default output limits
MAX_STDOUT_BYTES = 50 * 1024 * 1024  # 50 MiB
MAX_STDERR_BYTES = 1 * 1024 * 1024  # 1 MiB


def run_bounded(
    command: Sequence[str],
    max_stdout_bytes: int,
    max_stderr_bytes: int,
    timeout_seconds: int,
    env: dict[str, str],
) -> subprocess.CompletedProcess[bytes]:
    """Execute subprocess with streaming bounded output capture.

    This bounds parent-side output retention and terminates verbose children after
    the output limit is crossed. It does not replace a child process RSS/cgroup/rlimit cap.

    Unlike communicate(), this approach:
    - Does NOT buffer all stdout in memory before checking limits
    - Kills the child immediately when limits are exceeded
    - Provides early termination for large outputs
    - Prevents stderr backpressure deadlock by always draining stderr
    """
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

        # Read stdout/stderr incrementally with size limits
        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []
        stdout_total = 0
        stderr_total = 0
        stdout_closed = False
        stderr_closed = False
        stderr_truncated = False

        deadline = time.monotonic() + timeout_seconds

        while True:
            # Calculate remaining timeout - use real value, not clamped
            remaining = deadline - time.monotonic()

            # Check for timeout before selecting
            if remaining <= 0:
                process.kill()
                process.wait()
                raise subprocess.TimeoutExpired(cmd=list(command), timeout=timeout_seconds)

            # Use select to check if stdout/stderr are ready
            readable: list = []
            if not stdout_closed and process.stdout is not None:
                readable.append(process.stdout)
            if not stderr_closed and process.stderr is not None:
                readable.append(process.stderr)

            if not readable:
                # Both streams closed
                break

            # Use real remaining time for select, capped at 0.5s
            select_timeout = min(0.5, max(0.01, remaining))
            ready, _, _ = _select.select(readable, [], [], select_timeout)

            for stream in ready:
                if process.stdout is not None and stream is process.stdout:
                    chunk = stream.read(65536)  # Read 64KB at a time
                    if not chunk:
                        stdout_closed = True
                        continue
                    chunk_len = len(chunk)
                    if stdout_total + chunk_len > max_stdout_bytes:
                        # Kill child immediately - don't buffer more
                        process.kill()
                        stdout_closed = True
                        stdout_chunks.append(chunk[: max_stdout_bytes - stdout_total])
                        stdout_total = max(stdout_total + chunk_len, max_stdout_bytes + 1)
                        break
                    stdout_chunks.append(chunk)
                    stdout_total += chunk_len

                elif process.stderr is not None and stream is process.stderr:
                    chunk = stream.read(65536)
                    if not chunk:
                        stderr_closed = True
                        continue
                    # Always read stderr to prevent backpressure deadlock,
                    # but only keep up to the limit
                    if stderr_total < max_stderr_bytes:
                        available = max_stderr_bytes - stderr_total
                        stderr_chunks.append(chunk[:available])
                        stderr_total += min(len(chunk), available)
                        if stderr_total >= max_stderr_bytes:
                            stderr_truncated = True
                    # Continue draining stderr even after limit to prevent deadlock

            # Check if process finished
            if process.poll() is not None:
                # Drain any remaining stderr
                if process.stderr is not None and not stderr_closed:
                    remaining_stderr = process.stderr.read()
                    if remaining_stderr and stderr_total < max_stderr_bytes:
                        stderr_chunks.append(remaining_stderr[: max_stderr_bytes - stderr_total])
                break

        # Wait for process to fully exit
        process.wait()

        # Join output
        stdout = b"".join(stdout_chunks)
        stderr = b"".join(stderr_chunks)

        if stdout_total > max_stdout_bytes:
            raise KubectlOutputTooLargeError(
                command=command,
                actual_bytes=stdout_total,
                limit_bytes=max_stdout_bytes,
            )

        return subprocess.CompletedProcess(
            args=command,
            returncode=process.returncode,
            stdout=stdout,
            stderr=stderr + (b"\n... (stderr truncated)" if stderr_truncated else b""),
        )

    except subprocess.TimeoutExpired:
        if process is not None:
            process.kill()
            process.wait()
        raise
    except Exception:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        raise
