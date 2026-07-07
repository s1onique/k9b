"""Tests for kubectl_bounded module - bounded subprocess execution for kubectl."""

from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

from k8s_diag_agent.security.kubectl_bounded import (
    MAX_STDERR_BYTES,
    MAX_STDOUT_BYTES,
    run_bounded,
)
from k8s_diag_agent.security.kubectl_errors import KubectlOutputTooLargeError

# Use sys.executable for consistent Python path
PYTHON = sys.executable


class TestRunBounded:
    """Tests for run_bounded function."""

    def test_success_small_output(self) -> None:
        """Small output within limits should succeed."""
        result = run_bounded(
            command=[PYTHON, "-c", "print('hello')"],
            max_stdout_bytes=MAX_STDOUT_BYTES,
            max_stderr_bytes=MAX_STDERR_BYTES,
            timeout_seconds=10,
            env={},
        )
        assert result.returncode == 0
        assert result.stdout == b"hello\n"

    def test_stdout_capped_at_limit(self) -> None:
        """Stdout exceeding limit should raise KubectlOutputTooLargeError."""
        max_bytes = 1024  # 1 KiB
        large_output = "x" * (max_bytes + 100)

        with pytest.raises(KubectlOutputTooLargeError) as exc_info:
            run_bounded(
                command=[PYTHON, "-c", f"print('{large_output}')"],
                max_stdout_bytes=max_bytes,
                max_stderr_bytes=MAX_STDERR_BYTES,
                timeout_seconds=10,
                env={},
            )

        assert exc_info.value.limit_bytes == max_bytes
        assert exc_info.value.actual_bytes >= max_bytes

    def test_stdout_truncated_on_limit_hit(self) -> None:
        """Stdout should be truncated to exactly the limit."""
        max_bytes = 256
        large_output = "y" * 1024

        with pytest.raises(KubectlOutputTooLargeError):
            run_bounded(
                command=[PYTHON, "-c", f"print('{large_output}')"],
                max_stdout_bytes=max_bytes,
                max_stderr_bytes=MAX_STDERR_BYTES,
                timeout_seconds=10,
                env={},
            )

    def test_stderr_capped_not_raised(self) -> None:
        """Stderr exceeding limit should be truncated, not raise."""
        max_stderr = 128
        # Write large stderr content
        script = textwrap.dedent("""
            import sys
            sys.stderr.write('e' * 1024)
            sys.stderr.flush()
            print('ok')
        """)

        result = run_bounded(
            command=[PYTHON, "-c", script],
            max_stdout_bytes=MAX_STDOUT_BYTES,
            max_stderr_bytes=max_stderr,
            timeout_seconds=10,
            env={},
        )

        assert result.returncode == 0
        # Stderr should be truncated
        assert len(result.stderr) <= max_stderr + 50  # +50 for truncation marker

    def test_timeout_raises_timeout_expired(self) -> None:
        """Long-running command should raise TimeoutExpired."""
        with pytest.raises(subprocess.TimeoutExpired) as exc_info:
            run_bounded(
                command=[PYTHON, "-c", "import time; time.sleep(30)"],
                max_stdout_bytes=MAX_STDOUT_BYTES,
                max_stderr_bytes=MAX_STDERR_BYTES,
                timeout_seconds=1,
                env={},
            )

        assert exc_info.value.timeout == 1

    def test_command_failure_returns_nonzero(self) -> None:
        """Non-zero exit should return CompletedProcess with non-zero returncode."""
        result = run_bounded(
            command=[PYTHON, "-c", "import sys; sys.exit(1)"],
            max_stdout_bytes=MAX_STDOUT_BYTES,
            max_stderr_bytes=MAX_STDERR_BYTES,
            timeout_seconds=10,
            env={},
        )

        assert result.returncode == 1

    def test_stderr_truncated_marker_appended(self) -> None:
        """Stderr truncation marker should be appended when stderr is truncated."""
        max_stderr = 64
        script = textwrap.dedent("""
            import sys
            sys.stderr.write('e' * 1024)
            sys.stderr.flush()
            print('ok')
        """)

        result = run_bounded(
            command=[PYTHON, "-c", script],
            max_stdout_bytes=MAX_STDOUT_BYTES,
            max_stderr_bytes=max_stderr,
            timeout_seconds=10,
            env={},
        )

        assert result.returncode == 0
        # Truncation marker should be present
        assert "... (stderr truncated)" in result.stderr.decode("utf-8", errors="replace")

    def test_empty_output(self) -> None:
        """Command producing no output should succeed."""
        result = run_bounded(
            command=[PYTHON, "-c", "import sys; sys.exit(0)"],
            max_stdout_bytes=MAX_STDOUT_BYTES,
            max_stderr_bytes=MAX_STDERR_BYTES,
            timeout_seconds=10,
            env={},
        )

        assert result.returncode == 0
        assert result.stdout == b""

    def test_binary_stdout_truncated(self) -> None:
        """Binary stdout with null bytes should be handled correctly."""
        max_bytes = 128
        # Generate binary output with null bytes
        script = 'import sys; sys.stdout.buffer.write(b"\\x00" * 1024)'

        with pytest.raises(KubectlOutputTooLargeError):
            run_bounded(
                command=[PYTHON, "-c", script],
                max_stdout_bytes=max_bytes,
                max_stderr_bytes=MAX_STDERR_BYTES,
                timeout_seconds=10,
                env={},
            )

    def test_stderr_independent_of_stdout_limit(self) -> None:
        """Stderr should be enforced independently of stdout limit."""
        max_stdout = 16 * 1024 * 1024  # 16 MiB
        max_stderr = 64 * 1024  # 64 KiB

        script = textwrap.dedent("""
            import sys
            # Write small stdout
            sys.stdout.write('small')
            sys.stdout.flush()
            # Write large stderr
            sys.stderr.write('e' * 102400)
            sys.stderr.flush()
        """)

        result = run_bounded(
            command=[PYTHON, "-c", script],
            max_stdout_bytes=max_stdout,
            max_stderr_bytes=max_stderr,
            timeout_seconds=10,
            env={},
        )

        assert result.returncode == 0
        # stderr should be capped at max_stderr
        assert len(result.stderr) <= max_stderr + 50


class TestMaxConstants:
    """Tests for MAX_* constants."""

    def test_max_stdout_bytes_is_positive(self) -> None:
        """MAX_STDOUT_BYTES should be positive."""
        assert MAX_STDOUT_BYTES > 0

    def test_max_stderr_bytes_is_positive(self) -> None:
        """MAX_STDERR_BYTES should be positive."""
        assert MAX_STDERR_BYTES > 0

    def test_max_stderr_smaller_than_stdout(self) -> None:
        """MAX_STDERR_BYTES should be smaller than MAX_STDOUT_BYTES."""
        assert MAX_STDERR_BYTES < MAX_STDOUT_BYTES
