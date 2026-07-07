"""Tests for kubectl_logs module - bounded kubectl logs with fail-closed validation."""

from __future__ import annotations

import select as _select
import subprocess

import pytest

from k8s_diag_agent.security.kubectl_logs import (
    DEFAULT_LOG_MAX_BYTES,
    DEFAULT_LOG_TAIL_LINES,
    build_bounded_kubectl_logs,
    run_bounded_kubectl_logs,
)


class _FakeStream:
    """Fake stream for stdout/stderr that works with run_bounded's select loop."""
    
    def __init__(self, data: bytes = b"") -> None:
        self._data = data
        self._read = False
    
    def read(self, size: int = -1) -> bytes:
        if size < 0:
            result = self._data
        else:
            result = self._data[:size]
        if not self._read:
            self._data = b""
            self._read = True
        return result
    
    def readable(self) -> bool:
        return True
    
    def fileno(self) -> int:
        """Return a fake file descriptor - select.select will be patched anyway."""
        return -1


class _FakePopen:
    """Fake Popen that works with run_bounded for run_bounded tests.
    
    This is needed because conftest_kubectl_guard.py patches subprocess.Popen
    with a blocking function that raises pytest.fail. Tests that actually
    execute the bounded runner need to patch at the correct seam.
    """
    
    def __init__(self) -> None:
        self.returncode = 0
        self._poll_count = 0
    
    @property
    def stdout(self) -> _FakeStream:
        return _FakeStream(b"")
    
    @property
    def stderr(self) -> _FakeStream:
        return _FakeStream(b"")
    
    def poll(self) -> int | None:
        self._poll_count += 1
        if self._poll_count > 1:
            return 0  # Process has finished
        return None
    
    def wait(self, timeout: float | None = None) -> int:
        return 0
    
    def kill(self) -> None:
        pass
    
    def terminate(self) -> None:
        pass
    
    def communicate(self, input: bytes | None = None, timeout: float | None = None) -> tuple[bytes, bytes]:
        return b"", b""


def _make_fake_popen() -> _FakePopen:
    """Create a fake Popen that returns successful empty output."""
    return _FakePopen()


def _fake_select(rlist: list, wlist: list, xlist: list, timeout: float = 0.0) -> tuple[list, list, list]:
    """Fake select that works with _FakeStream objects.
    
    Since our fake streams don't have real file descriptors, we return immediately
    with empty lists to terminate the select loop quickly.
    """
    return [], [], []


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

    def test_builder_passes_validation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Builder output should pass run_bounded_kubectl_logs() validation."""
        cmd = build_bounded_kubectl_logs(
            namespace="default",
            pod="my-pod",
        )
        
        # Patch subprocess.Popen at the module where kubectl_bounded uses it
        fake_popen = _make_fake_popen()
        monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: fake_popen)
        # Also patch select.select since our fake Popen uses non-standard streams
        monkeypatch.setattr(_select, "select", _fake_select)
        
        # This should NOT raise - builder output is valid
        try:
            run_bounded_kubectl_logs(argv=cmd, timeout_seconds=1, max_stdout_bytes=1024, max_stderr_bytes=256)
        except ValueError as e:
            pytest.fail(f"Builder output should pass validation: {e}")


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

    def test_accepts_tail_bound(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should accept argv with --tail."""
        # Patch subprocess.Popen to avoid guard blocking kubectl execution
        fake_popen = _make_fake_popen()
        monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: fake_popen)
        monkeypatch.setattr(_select, "select", _fake_select)
        
        try:
            run_bounded_kubectl_logs(
                argv=["kubectl", "logs", "pod", "-n", "default", "--limit-bytes=1024", "--tail=100"],
                timeout_seconds=1,
                max_stdout_bytes=1024,
                max_stderr_bytes=256,
            )
        except ValueError as e:
            pytest.fail(f"--tail should be accepted: {e}")

    def test_accepts_since_bound(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should accept argv with --since."""
        fake_popen = _make_fake_popen()
        monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: fake_popen)
        monkeypatch.setattr(_select, "select", _fake_select)
        
        try:
            run_bounded_kubectl_logs(
                argv=["kubectl", "logs", "pod", "-n", "default", "--limit-bytes=1024", "--since=1h"],
                timeout_seconds=1,
                max_stdout_bytes=1024,
                max_stderr_bytes=256,
            )
        except ValueError as e:
            pytest.fail(f"--since should be accepted: {e}")

    def test_accepts_since_time_bound(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should accept argv with --since-time."""
        fake_popen = _make_fake_popen()
        monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: fake_popen)
        monkeypatch.setattr(_select, "select", _fake_select)
        
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

    def test_accepts_limit_bytes_equals_form(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should accept --limit-bytes=<N> form."""
        fake_popen = _make_fake_popen()
        monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: fake_popen)
        monkeypatch.setattr(_select, "select", _fake_select)
        
        try:
            run_bounded_kubectl_logs(
                argv=["kubectl", "logs", "pod", "-n", "default", "--limit-bytes=1048576", "--tail=500"],
                timeout_seconds=1,
                max_stdout_bytes=1024,
                max_stderr_bytes=256,
            )
        except ValueError as e:
            pytest.fail(f"--limit-bytes= form should be accepted: {e}")

    def test_accepts_tail_equals_form(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should accept --tail=<N> form."""
        fake_popen = _make_fake_popen()
        monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: fake_popen)
        monkeypatch.setattr(_select, "select", _fake_select)
        
        try:
            run_bounded_kubectl_logs(
                argv=["kubectl", "logs", "pod", "-n", "default", "--limit-bytes=1024", "--tail=500"],
                timeout_seconds=1,
                max_stdout_bytes=1024,
                max_stderr_bytes=256,
            )
        except ValueError as e:
            pytest.fail(f"--tail= form should be accepted: {e}")

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
