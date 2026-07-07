"""Tests for kubectl_logs module - bounded kubectl logs with fail-closed validation."""

from __future__ import annotations

import pytest

from k8s_diag_agent.security.kubectl_logs import (
    DEFAULT_LOG_MAX_BYTES,
    DEFAULT_LOG_TAIL_LINES,
    build_bounded_kubectl_logs,
    run_bounded_kubectl_logs,
)


class TestBuildBoundedKubectlLogs:
    """Tests for build_bounded_kubectl_logs() - verifies builder output passes validation."""

    def test_builder_adds_limit_bytes(self) -> None:
        """Builder should add --limit-bytes flag."""
        cmd = build_bounded_kubectl_logs(
            namespace="default",
            pod="my-pod",
        )
        
        assert "--limit-bytes" in cmd
        limit_idx = cmd.index("--limit-bytes")
        assert cmd[limit_idx + 1] == str(DEFAULT_LOG_MAX_BYTES)

    def test_builder_adds_tail(self) -> None:
        """Builder should add --tail flag."""
        cmd = build_bounded_kubectl_logs(
            namespace="default",
            pod="my-pod",
        )
        
        assert "--tail" in cmd
        tail_idx = cmd.index("--tail")
        assert cmd[tail_idx + 1] == str(DEFAULT_LOG_TAIL_LINES)

    def test_builder_adds_since_hours(self) -> None:
        """Builder should add --since when since_hours is provided."""
        cmd = build_bounded_kubectl_logs(
            namespace="default",
            pod="my-pod",
            since_hours=2,
        )
        
        assert "--since" in cmd
        since_idx = cmd.index("--since")
        assert cmd[since_idx + 1] == "2h"

    def test_builder_passes_validation(self) -> None:
        """Builder output should pass run_bounded_kubectl_logs() validation."""
        cmd = build_bounded_kubectl_logs(
            namespace="default",
            pod="my-pod",
        )
        
        # This should NOT raise - builder output is valid
        # Note: We can't actually run the command without a cluster,
        # but we can verify the validation doesn't reject it
        try:
            run_bounded_kubectl_logs(argv=cmd, timeout_seconds=1, max_stdout_bytes=1024, max_stderr_bytes=256)
        except ValueError as e:
            pytest.fail(f"Builder output should pass validation: {e}")
        except Exception:
            # Other exceptions (like cluster not available) are expected
            pass


class TestRunBoundedKubectlLogsValidation:
    """Tests for run_bounded_kubectl_logs() fail-closed validation."""

    def test_rejects_missing_limit_bytes(self) -> None:
        """Should reject argv without --limit-bytes."""
        with pytest.raises(ValueError) as exc_info:
            run_bounded_kubectl_logs(
                argv=["kubectl", "logs", "pod", "-n", "default"],
                timeout_seconds=1,
                max_stdout_bytes=1024,
                max_stderr_bytes=256,
            )
        
        assert "--limit-bytes" in str(exc_info.value)

    def test_rejects_zero_limit_bytes(self) -> None:
        """Should reject argv with --limit-bytes=0."""
        with pytest.raises(ValueError) as exc_info:
            run_bounded_kubectl_logs(
                argv=["kubectl", "logs", "pod", "-n", "default", "--limit-bytes=0", "--tail=100"],
                timeout_seconds=1,
                max_stdout_bytes=1024,
                max_stderr_bytes=256,
            )
        
        assert "positive" in str(exc_info.value).lower()

    def test_rejects_negative_limit_bytes(self) -> None:
        """Should reject argv with --limit-bytes=-1."""
        with pytest.raises(ValueError) as exc_info:
            run_bounded_kubectl_logs(
                argv=["kubectl", "logs", "pod", "-n", "default", "--limit-bytes=-1", "--tail=100"],
                timeout_seconds=1,
                max_stdout_bytes=1024,
                max_stderr_bytes=256,
            )
        
        assert "positive" in str(exc_info.value).lower()

    def test_rejects_missing_time_bound(self) -> None:
        """Should reject argv without --tail, --since, or --since-time."""
        with pytest.raises(ValueError) as exc_info:
            run_bounded_kubectl_logs(
                argv=["kubectl", "logs", "pod", "-n", "default", "--limit-bytes=1024"],
                timeout_seconds=1,
                max_stdout_bytes=1024,
                max_stderr_bytes=256,
            )
        
        assert "time bound" in str(exc_info.value).lower()

    def test_rejects_zero_tail(self) -> None:
        """Should reject argv with --tail=0."""
        with pytest.raises(ValueError) as exc_info:
            run_bounded_kubectl_logs(
                argv=["kubectl", "logs", "pod", "-n", "default", "--limit-bytes=1024", "--tail=0"],
                timeout_seconds=1,
                max_stdout_bytes=1024,
                max_stderr_bytes=256,
            )
        
        assert "tail" in str(exc_info.value).lower()

    def test_accepts_tail_bound(self) -> None:
        """Should accept argv with --tail."""
        # Note: Can't actually execute without cluster, but validation should pass
        try:
            run_bounded_kubectl_logs(
                argv=["kubectl", "logs", "pod", "-n", "default", "--limit-bytes=1024", "--tail=100"],
                timeout_seconds=1,
                max_stdout_bytes=1024,
                max_stderr_bytes=256,
            )
        except ValueError as e:
            pytest.fail(f"--tail should be accepted: {e}")
        except Exception:
            # Other exceptions (cluster not available) are expected
            pass

    def test_accepts_since_bound(self) -> None:
        """Should accept argv with --since."""
        try:
            run_bounded_kubectl_logs(
                argv=["kubectl", "logs", "pod", "-n", "default", "--limit-bytes=1024", "--since=1h"],
                timeout_seconds=1,
                max_stdout_bytes=1024,
                max_stderr_bytes=256,
            )
        except ValueError as e:
            pytest.fail(f"--since should be accepted: {e}")
        except Exception:
            pass

    def test_accepts_since_time_bound(self) -> None:
        """Should accept argv with --since-time."""
        try:
            run_bounded_kubectl_logs(
                argv=[
                    "kubectl", "logs", "pod", "-n", "default",
                    "--limit-bytes=1024",
                    "--since-time=2024-01-01T00:00:00Z"
                ],
                timeout_seconds=1,
                max_stdout_bytes=1024,
                max_stderr_bytes=256,
            )
        except ValueError as e:
            pytest.fail(f"--since-time should be accepted: {e}")
        except Exception:
            pass

    def test_accepts_limit_bytes_equals_form(self) -> None:
        """Should accept --limit-bytes=<N> form."""
        try:
            run_bounded_kubectl_logs(
                argv=["kubectl", "logs", "pod", "-n", "default", "--limit-bytes=1048576", "--tail=500"],
                timeout_seconds=1,
                max_stdout_bytes=1024,
                max_stderr_bytes=256,
            )
        except ValueError as e:
            pytest.fail(f"--limit-bytes= form should be accepted: {e}")
        except Exception:
            pass

    def test_accepts_tail_equals_form(self) -> None:
        """Should accept --tail=<N> form."""
        try:
            run_bounded_kubectl_logs(
                argv=["kubectl", "logs", "pod", "-n", "default", "--limit-bytes=1024", "--tail=500"],
                timeout_seconds=1,
                max_stdout_bytes=1024,
                max_stderr_bytes=256,
            )
        except ValueError as e:
            pytest.fail(f"--tail= form should be accepted: {e}")
        except Exception:
            pass

    def test_rejects_non_kubectl_command(self) -> None:
        """Should reject non-kubectl commands."""
        with pytest.raises(ValueError) as exc_info:
            run_bounded_kubectl_logs(
                argv=["helm", "list"],
                timeout_seconds=1,
                max_stdout_bytes=1024,
                max_stderr_bytes=256,
            )
        
        assert "kubectl" in str(exc_info.value).lower()

    def test_rejects_non_logs_command(self) -> None:
        """Should reject kubectl commands that aren't logs."""
        with pytest.raises(ValueError) as exc_info:
            run_bounded_kubectl_logs(
                argv=["kubectl", "get", "pods"],
                timeout_seconds=1,
                max_stdout_bytes=1024,
                max_stderr_bytes=256,
            )
        
        assert "logs" in str(exc_info.value).lower()
