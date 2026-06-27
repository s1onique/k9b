"""Tests for scheduler health gate rendering."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.scheduler_health_gate.contracts import (
    FAILURE_SCHEDULER_CRASH_LOOP,
    SchedulerHealthResult,
)
from scripts.scheduler_health_gate.render import (
    _bound_log_content,
    _format_crash_evidence,
    render_console_output,
    render_deployment_status,
    render_partial_readiness_warning,
    write_all_artifacts,
    write_bounded_summary,
    write_logs,
    write_pods_json,
    write_result_artifact,
)


class TestRenderConsoleOutput:
    """Tests for console output rendering."""

    def test_renders_passed(self, capsys: pytest.CaptureFixture) -> None:
        """Renders passed result."""
        result = SchedulerHealthResult()
        result.passed = True
        
        render_console_output(result)
        
        captured = capsys.readouterr()
        assert "SCHEDULER HEALTH GATE PASSED" in captured.out

    def test_renders_failed(self, capsys: pytest.CaptureFixture) -> None:
        """Renders failed result with details."""
        result = SchedulerHealthResult()
        result.passed = False
        result.failure_class = FAILURE_SCHEDULER_CRASH_LOOP
        result.failure_reason = "scheduler_crash_loop"
        result.failure_details = "Pod crashing"
        
        render_console_output(result)
        
        captured = capsys.readouterr()
        assert "SCHEDULER HEALTH GATE FAILED" in captured.out
        assert FAILURE_SCHEDULER_CRASH_LOOP in captured.out
        assert "scheduler_crash_loop" in captured.out
        assert "Pod crashing" in captured.out


class TestRenderDeploymentStatus:
    """Tests for deployment status rendering."""

    def test_renders_replicas(self, capsys: pytest.CaptureFixture) -> None:
        """Renders replica counts."""
        render_deployment_status(ready_replicas=1, spec_replicas=2, available_replicas=1)
        
        captured = capsys.readouterr()
        assert "Scheduler deployment status:" in captured.out
        assert "Ready replicas: 1/2" in captured.out
        assert "Available replicas: 1/2" in captured.out


class TestRenderPartialReadinessWarning:
    """Tests for partial readiness warning."""

    def test_renders_warning(self, capsys: pytest.CaptureFixture) -> None:
        """Renders partial readiness warning."""
        render_partial_readiness_warning(ready_replicas=1, spec_replicas=3)
        
        captured = capsys.readouterr()
        assert "WARNING" in captured.out
        assert "partial readiness" in captured.out
        assert "1/3" in captured.out


class TestWriteResultArtifact:
    """Tests for result artifact writing."""

    def test_writes_json_file(self, tmp_path: Path) -> None:
        """Writes result as JSON to file."""
        result = SchedulerHealthResult()
        result.passed = True
        result.deployment_name = "k9b-scheduler"
        
        scheduler_dir = tmp_path / "scheduler"
        scheduler_dir.mkdir()
        
        path = write_result_artifact(scheduler_dir, result)
        
        assert path.name == "scheduler-health-result.json"
        assert path.exists()
        
        data = json.loads(path.read_text())
        assert data["passed"] is True
        assert data["deployment_name"] == "k9b-scheduler"


class TestWriteBoundedSummary:
    """Tests for bounded summary writing."""

    def test_writes_summary_file(self, tmp_path: Path) -> None:
        """Writes summary text file."""
        result = SchedulerHealthResult()
        result.passed = False
        result.failure_class = FAILURE_SCHEDULER_CRASH_LOOP
        result.failure_reason = "test_reason"
        result.failure_details = "Test details"
        result.deployment_name = "test-deploy"
        result.deployment_found = True
        result.pod_count = 2
        result.ready_replicas = 0
        result.available_replicas = 0
        result.crash_loop_pods = [
            {"pod": "p1", "container": "c1", "reason": "CrashLoopBackOff", "restart_count": 5}
        ]
        result.waiting_pods = [
            {"pod": "p2", "container": "c1", "reason": "ContainerCreating", "message": "", "phase": "Pending"}
        ]
        result.namespace_events = [{}]
        
        scheduler_dir = tmp_path / "scheduler"
        scheduler_dir.mkdir()
        
        path = write_bounded_summary(scheduler_dir, result)
        
        assert path.name == "bounded-summary.txt"
        assert path.exists()
        
        content = path.read_text()
        assert "FAILED" in content
        assert FAILURE_SCHEDULER_CRASH_LOOP in content
        assert "p1/c1" in content
        assert "CrashLoopBackOff" in content
        assert "(restarts=5)" in content

    def test_includes_termination_evidence(self, tmp_path: Path) -> None:
        """Includes lastState termination evidence in summary."""
        result = SchedulerHealthResult()
        result.passed = False
        result.failure_class = FAILURE_SCHEDULER_CRASH_LOOP
        result.failure_reason = "scheduler_crash_loop"
        result.failure_details = "Pod crashing"
        result.deployment_name = "k9b-scheduler"
        result.deployment_found = True
        result.pod_count = 1
        result.ready_replicas = 0
        result.available_replicas = 0
        result.crash_loop_pods = [
            {
                "pod": "k9b-scheduler-abc123",
                "container": "scheduler",
                "reason": "CrashLoopBackOff",
                "restart_count": 2,
                "message": "back-off 5m0s starting",
                "last_exit_code": 1,
                "last_exit_reason": "Error",
                "last_exit_message": "ConfigError: missing required env K9B_KUBERNETES_AUTH_MODE",
            }
        ]
        result.waiting_pods = []
        result.namespace_events = []
        
        scheduler_dir = tmp_path / "scheduler"
        scheduler_dir.mkdir()
        
        path = write_bounded_summary(scheduler_dir, result)
        content = path.read_text()
        
        # Should include termination evidence
        assert "Previous termination: exit=1" in content
        assert "Error" in content
        assert "K9B_KUBERNETES_AUTH_MODE" in content
        assert "Waiting message" in content

    def test_includes_log_excerpts(self, tmp_path: Path) -> None:
        """Includes bounded log excerpts for crash loop pods."""
        result = SchedulerHealthResult()
        result.passed = False
        result.failure_class = FAILURE_SCHEDULER_CRASH_LOOP
        result.failure_reason = "scheduler_crash_loop"
        result.failure_details = "Pod crashing"
        result.deployment_name = "k9b-scheduler"
        result.deployment_found = True
        result.pod_count = 1
        result.ready_replicas = 0
        result.available_replicas = 0
        result.crash_loop_pods = [
            {
                "pod": "k9b-scheduler-abc123",
                "container": "scheduler",
                "reason": "CrashLoopBackOff",
                "restart_count": 2,
                "message": "back-off 5m0s starting",
            }
        ]
        result.waiting_pods = []
        result.namespace_events = []
        # Include log excerpts in result
        result.scheduler_logs = {
            "k9b-scheduler-abc123": "Starting scheduler...\nLoading config...\nERROR: ConfigError: missing env\nShutting down...",
            "k9b-scheduler-abc123.previous": "Starting scheduler...\nPrevious run crashed",
        }
        
        scheduler_dir = tmp_path / "scheduler"
        scheduler_dir.mkdir()
        
        path = write_bounded_summary(scheduler_dir, result)
        content = path.read_text()
        
        # Should include log excerpts
        assert "Current log excerpt" in content
        assert "Previous log excerpt" in content
        assert "Starting scheduler" in content
        assert "ERROR: ConfigError" in content


class TestWritePodsJson:
    """Tests for pods JSON artifact writing."""

    def test_writes_pods_json(self, tmp_path: Path) -> None:
        """Writes pods JSON file."""
        scheduler_dir = tmp_path / "scheduler"
        scheduler_dir.mkdir()
        
        pods_json = '{"items": [{"name": "test-pod"}]}'
        path = write_pods_json(scheduler_dir, pods_json)
        
        assert path is not None
        assert path.name == "scheduler-pods.json"
        assert path.exists()
        
        data = json.loads(path.read_text())
        assert len(data["items"]) == 1

    def test_returns_none_for_empty(self, tmp_path: Path) -> None:
        """Returns None when pods_json is empty."""
        scheduler_dir = tmp_path / "scheduler"
        scheduler_dir.mkdir()
        
        path = write_pods_json(scheduler_dir, "")
        
        assert path is None


class TestWriteLogs:
    """Tests for logs writing."""

    def test_writes_log_files(self, tmp_path: Path) -> None:
        """Writes log files to directory."""
        scheduler_dir = tmp_path / "scheduler"
        scheduler_dir.mkdir()
        
        logs = {
            "pod-1": "Log line 1\nLog line 2",
            "pod-1.previous": "Previous log line",
        }
        
        logs_dir = write_logs(scheduler_dir, logs)
        
        assert logs_dir.name == "logs"
        assert logs_dir.exists()
        assert (logs_dir / "pod-1.log").exists()
        assert (logs_dir / "pod-1.previous.log").exists()
        assert "Log line 1" in (logs_dir / "pod-1.log").read_text()


class TestWriteAllArtifacts:
    """Tests for writing all artifacts at once."""

    def test_writes_all_artifact_types(self, tmp_path: Path) -> None:
        """Writes result, summary, pods, and logs artifacts."""
        result = SchedulerHealthResult()
        result.passed = True
        result.deployment_name = "test-scheduler"
        result.scheduler_pods_json = '{"items": []}'
        
        scheduler_dir = tmp_path / "scheduler"
        scheduler_dir.mkdir()
        
        logs = {"pod-1": "Log content"}
        
        write_all_artifacts(scheduler_dir, result, logs)
        
        assert (scheduler_dir / "scheduler-health-result.json").exists()
        assert (scheduler_dir / "bounded-summary.txt").exists()
        assert (scheduler_dir / "scheduler-pods.json").exists()
        assert (scheduler_dir / "logs" / "pod-1.log").exists()


class TestBoundLogContent:
    """Tests for log bounding utility."""

    def test_short_content_returns_as_is(self) -> None:
        """Content under max lines returns unchanged."""
        content = "line1\nline2\nline3"
        result = _bound_log_content(content, max_lines=10)
        assert result == content

    def test_long_content_is_bounded(self) -> None:
        """Content over max lines is truncated with ellipsis."""
        lines = [f"line {i}" for i in range(100)]
        content = "\n".join(lines)
        result = _bound_log_content(content, max_lines=20)
        
        # Should have ellipsis marker on its own line
        # For max_lines=20: retained=19, so 81 lines omitted (100-19)
        assert "... [81 more lines] ..." in result
        # For max_lines=20, we get 9 head + 1 marker + 10 tail = 20 lines
        result_lines = result.split("\n")
        assert len(result_lines) == 20

    def test_empty_content_handled(self) -> None:
        """Empty content returns placeholder."""
        result = _bound_log_content("")
        assert result == "(no log content)"

    def test_none_content_handled(self) -> None:
        """None content returns placeholder."""
        result = _bound_log_content(None)
        assert result == "(no log content)"


class TestFormatCrashEvidence:
    """Tests for crash evidence formatting."""

    def test_basic_crash_loop_info(self) -> None:
        """Formats basic crash loop information."""
        crash = {
            "pod": "test-pod",
            "container": "scheduler",
            "reason": "CrashLoopBackOff",
            "restart_count": 5,
        }
        logs: dict[str, str] = {}
        
        result = _format_crash_evidence(crash, logs)
        
        assert any("test-pod/scheduler" in line for line in result)
        assert any("CrashLoopBackOff" in line for line in result)
        assert any("restarts=5" in line for line in result)

    def test_includes_termination_details(self) -> None:
        """Includes previous termination details."""
        crash = {
            "pod": "test-pod",
            "container": "scheduler",
            "reason": "CrashLoopBackOff",
            "restart_count": 2,
            "last_exit_code": 1,
            "last_exit_reason": "Error",
            "last_exit_message": "ConfigError: missing env",
        }
        logs: dict[str, str] = {}
        
        result = _format_crash_evidence(crash, logs)
        
        joined = "\n".join(result)
        assert "Previous termination: exit=1" in joined
        assert "Error" in joined
        assert "ConfigError" in joined

    def test_includes_log_excerpts(self) -> None:
        """Includes bounded log excerpts."""
        crash = {
            "pod": "test-pod",
            "container": "scheduler",
            "reason": "CrashLoopBackOff",
            "restart_count": 1,
        }
        logs: dict[str, str] = {
            "test-pod": "Starting up...\nConfig loaded\nERROR: crash\nDone",
        }
        
        result = _format_crash_evidence(crash, logs)
        joined = "\n".join(result)
        
        assert "Current log" in joined
        assert "Starting up" in joined

    def test_includes_previous_log(self) -> None:
        """Includes previous container log."""
        crash = {
            "pod": "test-pod",
            "container": "scheduler",
            "reason": "CrashLoopBackOff",
            "restart_count": 1,
        }
        logs = {
            "test-pod": "Current log",
            "test-pod.previous": "Previous log with error",
        }
        
        result = _format_crash_evidence(crash, logs)
        joined = "\n".join(result)
        
        assert "Previous log" in joined
        assert "Previous log with error" in joined
