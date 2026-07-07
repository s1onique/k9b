"""Tests for bounded kubectl subprocess execution.

These tests verify that:
1. Large stdout is rejected without buffering unbounded output
2. Output limits are enforced
3. Memory safety is maintained
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.security.kubectl_subprocess import (
    KubectlExecutionError,
    KubectlInvocation,
    KubectlOutputTooLargeError,
    _inject_timeout,
    _maybe_inject_chunk_size,
    _run_bounded,
    build_bounded_kubectl_get,
    run_kubectl,
)


class TestKubectlInvocation:
    """Tests for KubectlInvocation parsing."""

    def test_parse_simple_command(self):
        """Test parsing a simple kubectl command."""
        cmd = ["kubectl", "get", "pods", "-n", "default", "-o", "json"]
        inv = KubectlInvocation.from_command(cmd)
        assert inv.argv == tuple(cmd)
        assert inv.namespace == "default"
        assert not inv.is_all_namespaces
        assert inv.resource_kind == "pods"
        assert inv.output_format == "json"

    def test_parse_all_namespaces(self):
        """Test parsing kubectl with --all-namespaces."""
        cmd = ["kubectl", "get", "pods", "--all-namespaces", "-o", "wide"]
        inv = KubectlInvocation.from_command(cmd)
        assert inv.is_all_namespaces
        assert inv.namespace is None
        assert inv.resource_kind == "pods"
        assert inv.output_format == "wide"

    def test_parse_short_all_namespaces(self):
        """Test parsing kubectl with -A flag."""
        cmd = ["kubectl", "get", "events", "-A", "-o", "json"]
        inv = KubectlInvocation.from_command(cmd)
        assert inv.is_all_namespaces
        assert inv.resource_kind == "events"

    def test_parse_describe_command(self):
        """Test parsing kubectl describe command."""
        cmd = ["kubectl", "describe", "pod", "my-pod", "-n", "my-ns"]
        inv = KubectlInvocation.from_command(cmd)
        assert inv.namespace == "my-ns"
        assert inv.resource_kind == "pod"

    def test_parse_compact_namespace(self):
        """Test parsing kubectl with -n=value format."""
        cmd = ["kubectl", "get", "pods", "-n=my-ns", "-o", "json"]
        inv = KubectlInvocation.from_command(cmd)
        assert inv.namespace == "my-ns"

    def test_parse_compact_output(self):
        """Test parsing kubectl with -o=value format."""
        cmd = ["kubectl", "get", "pods", "-o=yaml"]
        inv = KubectlInvocation.from_command(cmd)
        assert inv.output_format == "yaml"


class TestTimeoutInjection:
    """Tests for timeout injection."""

    def test_inject_timeout_when_missing(self):
        """Test that timeout is injected when not present."""
        cmd = ["kubectl", "get", "pods", "-n", "default"]
        result = _inject_timeout(cmd, 30)
        assert "--request-timeout" in result
        assert "30" in result

    def test_no_injection_when_present(self):
        """Test that timeout is not injected when already present."""
        cmd = ["kubectl", "get", "pods", "-n", "default", "--request-timeout", "120"]
        result = _inject_timeout(cmd, 30)
        # Should keep original timeout
        assert result.count("--request-timeout") == 1
        assert "120" in result


class TestChunkSizeInjection:
    """Tests for chunk size injection."""

    def test_inject_chunk_size_for_get(self):
        """Test that chunk size is injected for get commands."""
        cmd = ["kubectl", "get", "pods", "-n", "default"]
        result = _maybe_inject_chunk_size(cmd, 500)
        assert "--chunk-size" in result
        assert "500" in result

    def test_no_injection_for_non_get(self):
        """Test that chunk size is not injected for non-get commands."""
        cmd = ["kubectl", "describe", "pod", "my-pod"]
        result = _maybe_inject_chunk_size(cmd, 500)
        assert "--chunk-size" not in result

    def test_no_injection_when_present(self):
        """Test that chunk size is not injected when already present."""
        cmd = ["kubectl", "get", "pods", "--chunk-size", "100"]
        result = _maybe_inject_chunk_size(cmd, 500)
        assert result.count("--chunk-size") == 1
        assert "100" in result


class TestBoundedExecution:
    """Tests for bounded subprocess execution.

    Note: The streaming implementation uses select() which requires real file
    descriptors. These tests use a simpler approach that verifies the output
    limits are correctly enforced. Full streaming behavior should be tested
    with real subprocesses in integration tests.
    """

    def test_large_stdout_rejected(self):
        """Test that output exceeding limit raises error.

        This tests that KubectlOutputTooLargeError is raised when output
        exceeds the limit. The actual streaming behavior (killing child
        before full buffer) is exercised in integration tests with real
        subprocesses.
        """
        # Use a real subprocess that outputs more than the limit
        import os
        import tempfile

        # Create a script that outputs large data
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
            f.write('#!/bin/bash\n')
            f.write('echo "start"\n')
            # Output enough to exceed a small limit
            for i in range(100):
                f.write(f'echo "line{i}: {"x" * 10000}"\n')
            f.write('echo "done"\n')
            script_path = f.name
        os.chmod(script_path, 0o755)

        try:
            with pytest.raises(KubectlOutputTooLargeError) as exc_info:
                _run_bounded(
                    [script_path],
                    max_stdout_bytes=100 * 1024,  # 100KB limit
                    max_stderr_bytes=1024 * 1024,
                    timeout_seconds=10,
                    env={},
                )
            assert exc_info.value.limit_bytes == 100 * 1024
        finally:
            os.unlink(script_path)

    def test_normal_stdout_accepted(self):
        """Test that normal output is accepted."""
        import os
        import tempfile

        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
            f.write('#!/bin/bash\n')
            f.write('echo \'{"items": []}\'\n')
            script_path = f.name
        os.chmod(script_path, 0o755)

        try:
            result = _run_bounded(
                [script_path],
                max_stdout_bytes=50 * 1024 * 1024,
                max_stderr_bytes=1024 * 1024,
                timeout_seconds=10,
                env={},
            )
            assert result.returncode == 0
            assert b'items' in result.stdout
        finally:
            os.unlink(script_path)

    def test_large_stderr_truncated(self):
        """Test that large stderr is truncated but doesn't fail."""
        import os
        import tempfile

        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
            f.write('#!/bin/bash\n')
            f.write('echo \'{"items": []}\' >&2\n')
            f.write('echo \'error message repeated:\' >&2\n')
            # Repeat to exceed 1KB limit
            for i in range(100):
                f.write(f'echo "error line {i}: {"x" * 100}" >&2\n')
            script_path = f.name
        os.chmod(script_path, 0o755)

        try:
            result = _run_bounded(
                [script_path],
                max_stdout_bytes=50 * 1024 * 1024,
                max_stderr_bytes=1024,  # 1KB limit
                timeout_seconds=10,
                env={},
            )
            # Should succeed with truncated stderr
            assert result.returncode == 0
            # stderr should be truncated
            assert len(result.stderr) < 10 * 1024
        finally:
            os.unlink(script_path)

    def test_process_killed_on_limit_exceeded(self):
        """Test that process is killed when stdout exceeds limit."""
        import os
        import tempfile

        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
            f.write('#!/bin/bash\n')
            # Continuously output without end
            f.write('while true; do echo "x"; done\n')
            script_path = f.name
        os.chmod(script_path, 0o755)

        try:
            with pytest.raises(KubectlOutputTooLargeError):
                _run_bounded(
                    [script_path],
                    max_stdout_bytes=50 * 1024,  # 50KB limit
                    max_stderr_bytes=1024 * 1024,
                    timeout_seconds=5,
                    env={},
                )
        finally:
            os.unlink(script_path)


class TestRunKubectl:
    """Tests for the main run_kubectl function.

    Note: Tests for run_kubectl are limited due to the streaming implementation
    using select() which requires real file descriptors. The key behavior
    (bounded execution, output limits, error handling) is tested via
    TestBoundedExecution which uses real subprocesses.
    """

    def test_import_succeeds(self):
        """Test that run_kubectl can be imported and called."""
        # Just verify the function exists and has correct signature
        assert callable(run_kubectl)
        assert callable(KubectlOutputTooLargeError)
        assert callable(KubectlExecutionError)


class TestBuildBoundedKubectlGet:
    """Tests for build_bounded_kubectl_get convenience function."""

    def test_basic_command(self):
        """Test basic command building."""
        cmd = build_bounded_kubectl_get("pods", namespace="default")
        assert cmd == [
            "kubectl", "get", "pods",
            "-n", "default",
            "-o", "json",
            "--request-timeout", "60",
            "--chunk-size", "500",
        ]

    def test_all_namespaces(self):
        """Test command with all namespaces."""
        cmd = build_bounded_kubectl_get("pods", all_namespaces=True)
        assert "--all-namespaces" in cmd

    def test_with_label_selector(self):
        """Test command with label selector."""
        cmd = build_bounded_kubectl_get(
            "pods",
            namespace="default",
            label_selector="app=myapp",
        )
        assert "--label-selector" in cmd
        assert "app=myapp" in cmd

    def test_with_field_selector(self):
        """Test command with field selector."""
        cmd = build_bounded_kubectl_get(
            "events",
            namespace="default",
            field_selector="type=Warning",
        )
        assert "--field-selector" in cmd
        assert "type=Warning" in cmd

    def test_events_with_sort(self):
        """Test events with sort field."""
        cmd = build_bounded_kubectl_get(
            "events",
            namespace="default",
            sort_by=".metadata.creationTimestamp",
        )
        assert "--sort-by" in cmd
        assert ".metadata.creationTimestamp" in cmd


class TestBackwardCompatibility:
    """Tests to ensure backward compatibility with existing callers."""

    def test_kubectl_invocation_to_dict(self):
        """Test that KubectlInvocation can be serialized to dict."""
        cmd = ["kubectl", "get", "pods", "-n", "default"]
        inv = KubectlInvocation.from_command(cmd, timeout_seconds=30, run_id="test-123")
        log_dict = inv.to_log_dict()

        assert log_dict["event"] == "kubectl_invocation"
        assert log_dict["argv"] == cmd
        assert log_dict["namespace"] == "default"
        assert log_dict["timeout_seconds"] == 30
        assert log_dict["run_id"] == "test-123"

    def test_error_attributes(self):
        """Test that KubectlExecutionError has expected attributes."""
        exc = KubectlExecutionError(
            message="test error",
            command=["kubectl", "get", "pods"],
            returncode=1,
            elapsed_seconds=5.0,
            max_rss_kb=102400,
        )

        assert exc.returncode == 1
        assert exc.elapsed_seconds == 5.0
        assert exc.max_rss_kb == 102400
