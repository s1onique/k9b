"""Bounded subprocess execution for kubectl with streaming output capture."""

from __future__ import annotations

import os
import selectors
import signal
import subprocess
import time
from collections.abc import Sequence

from .kubectl_errors import KubectlOutputTooLargeError

# Default output limits
MAX_STDOUT_BYTES = 50 * 1024 * 1024  # 50 MiB
MAX_STDERR_BYTES = 1 * 1024 * 1024  # 1 MiB

# Read chunk size for non-blocking reads
_READ_CHUNK_SIZE = 65536


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

    Uses non-blocking fd-level reads to prevent stream.read() from blocking when
    less than the requested amount is available. Stdout and stderr limits are enforced
    independently - hitting stdout limit does not suppress stderr draining and vice versa.
    """
    process: subprocess.Popen[bytes] | None = None
    selector: selectors.DefaultSelector | None = None

    try:
        # Start process with pipe handles
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            # Start process in new process group for reliable kill
            start_new_session=True,
        )

        stdout_fd = process.stdout.fileno() if process.stdout else -1
        stderr_fd = process.stderr.fileno() if process.stderr else -1

        # Set non-blocking mode on pipe file descriptors
        if stdout_fd >= 0:
            os.set_blocking(stdout_fd, False)
        if stderr_fd >= 0:
            os.set_blocking(stderr_fd, False)

        # Initialize selector for multiplexed I/O
        selector = selectors.DefaultSelector()
        stdout_closed = False
        stderr_closed = False
        stdout_truncated = False
        stderr_truncated = False
        stdout_total = 0
        stderr_total = 0
        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []

        # Register stdout if valid
        if stdout_fd >= 0:
            selector.register(stdout_fd, selectors.EVENT_READ, data="stdout")

        # Register stderr if valid
        if stderr_fd >= 0:
            selector.register(stderr_fd, selectors.EVENT_READ, data="stderr")

        deadline = time.monotonic() + timeout_seconds

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _kill_process_group(process)
                process.wait()
                raise subprocess.TimeoutExpired(cmd=list(command), timeout=timeout_seconds)

            # Compute select timeout - use small intervals for responsiveness
            select_timeout = min(0.1, max(0.01, remaining))

            # Wait for ready file descriptors
            try:
                events = selector.select(timeout=select_timeout)
            except OSError:
                # Selector may fail if fd was closed unexpectedly
                break

            if not events:
                # Timeout with no events - check if process is still running
                if process.poll() is not None:
                    break
                continue

            for key, _ in events:
                fd = key.fd
                stream_type = key.data

                if stream_type == "stdout" and not stdout_closed:
                    if fd == stdout_fd and process.stdout:
                        chunk = _read_fd_nonblocking(stdout_fd)
                        if chunk is None:
                            stdout_closed = True
                            selector.unregister(stdout_fd)
                            continue

                        chunk_len = len(chunk)
                        if stdout_total + chunk_len > max_stdout_bytes:
                            # Truncate at limit
                            available = max_stdout_bytes - stdout_total
                            if available > 0:
                                stdout_chunks.append(chunk[:available])
                            # Track actual bytes produced (includes overflow)
                            stdout_total += chunk_len
                            stdout_truncated = True
                            # Kill child immediately - don't buffer more
                            _kill_process_group(process)
                            stdout_closed = True
                            selector.unregister(stdout_fd)
                            continue

                        stdout_chunks.append(chunk)
                        stdout_total += chunk_len

                elif stream_type == "stderr" and not stderr_closed:
                    if fd == stderr_fd and process.stderr:
                        chunk = _read_fd_nonblocking(stderr_fd)
                        if chunk is None:
                            stderr_closed = True
                            selector.unregister(stderr_fd)
                            continue

                        # Always read stderr to prevent backpressure deadlock,
                        # but only accumulate up to the limit
                        chunk_len = len(chunk)
                        if stderr_total < max_stderr_bytes:
                            available = max_stderr_bytes - stderr_total
                            if available > 0:
                                stderr_chunks.append(chunk[:available])
                                stderr_total += min(chunk_len, available)
                                if stderr_total >= max_stderr_bytes:
                                    stderr_truncated = True
                        # Continue draining stderr even after limit to prevent deadlock

            # Check if process finished and all streams drained
            if process.poll() is not None:
                # Give a moment for final data to arrive
                if not stdout_closed:
                    chunk = _read_fd_nonblocking(stdout_fd)
                    if chunk:
                        chunk_len = len(chunk)
                        if stdout_total + chunk_len > max_stdout_bytes:
                            available = max_stdout_bytes - stdout_total
                            if available > 0:
                                stdout_chunks.append(chunk[:available])
                            stdout_truncated = True
                        else:
                            stdout_chunks.append(chunk)
                        stdout_total += chunk_len
                    else:
                        stdout_closed = True

                if not stderr_closed:
                    chunk = _read_fd_nonblocking(stderr_fd)
                    if chunk:
                        if stderr_total < max_stderr_bytes:
                            available = max_stderr_bytes - stderr_total
                            if available > 0:
                                stderr_chunks.append(chunk[:available])
                                stderr_total += min(len(chunk), available)
                                if stderr_total >= max_stderr_bytes:
                                    stderr_truncated = True
                    else:
                        stderr_closed = True

                if stdout_closed and stderr_closed:
                    break

        # Wait for process to fully exit
        process.wait()

        # Join output
        stdout = b"".join(stdout_chunks)
        stderr = b"".join(stderr_chunks)

        if stdout_truncated or stdout_total > max_stdout_bytes:
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
            _kill_process_group(process)
            process.wait()
        raise
    except Exception:
        if process is not None and process.poll() is None:
            _kill_process_group(process)
            process.wait()
        raise
    finally:
        # Clean up selector
        if selector is not None:
            try:
                selector.close()
            except Exception:
                pass

        # Close pipe handles if still open
        if process is not None:
            if process.stdout is not None:
                try:
                    process.stdout.close()
                except Exception:
                    pass
            if process.stderr is not None:
                try:
                    process.stderr.close()
                except Exception:
                    pass


def _read_fd_nonblocking(fd: int) -> bytes | None:
    """Read from a non-blocking file descriptor.

    Returns:
        bytes: Data read from the fd
        None: EOF reached (fd closed)

    Raises:
        BlockingIOError: If no data available (should not happen with select)
    """
    try:
        chunk = os.read(fd, _READ_CHUNK_SIZE)
        if not chunk:
            return None
        return chunk
    except BlockingIOError:
        # No data available despite select saying ready - this can happen
        # with certain pipe behaviors; treat as no data for now
        return b""
    except OSError as e:
        # EBADF means fd is not valid, EOF for pipe
        if e.errno == 9:  # EBADF
            return None
        raise


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    """Kill process and its entire process group.

    Uses SIGTERM first for graceful shutdown, then SIGKILL if needed.
    """
    if process.poll() is not None:
        # Process already exited
        return

    try:
        # Kill the entire process group
        pgid = os.getpgid(process.pid)
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        # Process already gone or no permission to kill pg
        pass

    # If still running after brief wait, force kill
    if process.poll() is None:
        try:
            pgid = os.getpgid(process.pid)
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    # Final wait with timeout to avoid hanging
    try:
        process.wait(timeout=1.0)
    except subprocess.TimeoutExpired:
        pass
