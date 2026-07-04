# Copyright (c) 2025 Artem Chistyakov
# SPDX-License-Identifier: MIT

"""Regression tests for P0c backend connectivity preflight (k9b_otel_demo_lab_backend_connectivity).

These tests verify that transient backend Service connectivity failures are properly retried
instead of failing immediately. This catches the timing race between deployment readiness
and scheduler-side connectivity where EndpointSlices may not be fully populated yet.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest


class TestBackendConnectivityRetriesTransientFailure:
    """Regression tests for P0c retry behavior on transient connectivity failures."""

    def test_backend_connectivity_retries_transient_connection_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """P0c must retry when first attempt returns reachable=false with Errno 111.

        This is the core regression test for the transient Service/EndpointSlice timing race.
        First attempt simulates Connection refused, second returns healthy HTTP 200.
        """
        from scripts.k9b_otel_demo_lab_backend_connectivity import (
            run_backend_connectivity_preflight,
        )

        calls: dict[str, int] = {"count": 0}
        sleeps: list[float] = []

        def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            calls["count"] += 1

            if calls["count"] == 1:
                # First attempt: transient connection refused (EndpointSlice not ready)
                return subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout=json.dumps(
                        {
                            "reachable": False,
                            "healthy": False,
                            "status": None,
                            "total": 0,
                            "incidents": [],
                            "failure_class": "backend_service_unreachable_from_scheduler",
                            "error": "<urlopen error [Errno 111] Connection refused>",
                        }
                    ),
                    stderr="",
                )

            # Second attempt: backend is now reachable and healthy
            return subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=json.dumps(
                    {
                        "reachable": True,
                        "healthy": True,
                        "status": 200,
                        "total": 0,
                        "incidents": [],
                        "failure_class": None,
                        "error": None,
                    }
                ),
                stderr="",
            )

        monkeypatch.setattr("time.sleep", fake_sleep)
        monkeypatch.setattr("subprocess.run", fake_run)

        result = run_backend_connectivity_preflight(
            kubeconfig="/tmp/kubeconfig",
            namespace="k9b",
            artifact_dir=tmp_path,
            timeout_seconds=30,
        )

        # Must pass after retry
        assert result.passed is True, f"Expected passed=True, got: {result.message}"
        assert result.backend_reachable is True
        assert result.incidents_endpoint_status == 200
        assert result.attempt_count == 2, f"Expected 2 attempts, got {result.attempt_count}"
        assert calls["count"] == 2, f"Expected 2 subprocess calls, got {calls['count']}"

        # Exponential backoff: first sleep should be 2^(1-1) = 1 second
        assert sleeps == [1], f"Expected sleep [1], got {sleeps}"

    def test_backend_connectivity_fails_fast_on_unhealthy_endpoint(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """P0c must fail immediately when backend is reachable but unhealthy (not retryable).

        Reaching the backend but getting HTTP 500 or malformed payload indicates a real
        contract/config failure, not a transient timing issue. This should fail-fast.
        """
        from scripts.k9b_otel_demo_lab_backend_connectivity import (
            run_backend_connectivity_preflight,
        )

        calls: dict[str, int] = {"count": 0}
        sleeps: list[float] = []

        def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            calls["count"] += 1

            # Backend reachable but returns HTTP 500 (real failure, not retryable)
            return subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=json.dumps(
                    {
                        "reachable": True,
                        "healthy": False,
                        "status": 500,
                        "total": 0,
                        "incidents": [],
                        "failure_class": "backend_incidents_endpoint_unhealthy",
                        "error": "HTTPError 500",
                    }
                ),
                stderr="",
            )

        monkeypatch.setattr("time.sleep", fake_sleep)
        monkeypatch.setattr("subprocess.run", fake_run)

        result = run_backend_connectivity_preflight(
            kubeconfig="/tmp/kubeconfig",
            namespace="k9b",
            artifact_dir=tmp_path,
            timeout_seconds=30,
        )

        # Must fail immediately (no retries for unhealthy endpoint)
        assert result.passed is False
        assert result.backend_reachable is True  # Reached the backend
        assert result.incidents_endpoint_status == 500
        assert result.attempt_count == 1, f"Expected 1 attempt (fail-fast), got {result.attempt_count}"
        assert calls["count"] == 1
        assert sleeps == [], "Should not sleep when backend is reachable but unhealthy"

    def test_backend_connectivity_retries_multiple_times_before_success(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """P0c must retry multiple times if backend takes several attempts to become available."""
        from scripts.k9b_otel_demo_lab_backend_connectivity import (
            run_backend_connectivity_preflight,
        )

        calls: dict[str, int] = {"count": 0}
        sleeps: list[float] = []

        def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            calls["count"] += 1

            if calls["count"] <= 4:
                # Attempts 1-4 fail with connection refused
                return subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout=json.dumps(
                        {
                            "reachable": False,
                            "healthy": False,
                            "status": None,
                            "total": 0,
                            "incidents": [],
                            "failure_class": "backend_service_unreachable_from_scheduler",
                            "error": "<urlopen error [Errno 111] Connection refused>",
                        }
                    ),
                    stderr="",
                )

            # Fifth attempt (count == 5): success
            return subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=json.dumps(
                    {
                        "reachable": True,
                        "healthy": True,
                        "status": 200,
                        "total": 5,
                        "incidents": [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}, {"id": 5}],
                        "failure_class": None,
                        "error": None,
                    }
                ),
                stderr="",
            )

        monkeypatch.setattr("time.sleep", fake_sleep)
        monkeypatch.setattr("subprocess.run", fake_run)

        result = run_backend_connectivity_preflight(
            kubeconfig="/tmp/kubeconfig",
            namespace="k9b",
            artifact_dir=tmp_path,
            timeout_seconds=30,
        )

        assert result.passed is True
        assert result.backend_reachable is True
        assert result.attempt_count == 5
        assert result.incidents_total == 5
        assert len(result.incidents_found) == 5

        # Exponential backoff: sleeps should be 1, 2, 4, 8 (capped by remaining time)
        assert len(sleeps) == 4, f"Expected 4 sleeps, got {len(sleeps)}"
        assert sleeps[0] == 1  # 2^0
        assert sleeps[1] == 2  # 2^1
        assert sleeps[2] == 4  # 2^2

    def test_backend_connectivity_exhausts_retries_after_timeout(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """P0c must fail after exhausting all retries within timeout."""
        from scripts.k9b_otel_demo_lab_backend_connectivity import (
            run_backend_connectivity_preflight,
        )

        calls: dict[str, int] = {"count": 0}

        def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            calls["count"] += 1
            # Always fail with connection refused
            return subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=json.dumps(
                    {
                        "reachable": False,
                        "healthy": False,
                        "status": None,
                        "total": 0,
                        "incidents": [],
                        "failure_class": "backend_service_unreachable_from_scheduler",
                        "error": "<urlopen error [Errno 111] Connection refused>",
                    }
                ),
                stderr="",
            )

        # No actual sleep and reduced subprocess timeout for speed
        monkeypatch.setattr("time.sleep", lambda s: None)
        monkeypatch.setattr("subprocess.run", fake_run)

        result = run_backend_connectivity_preflight(
            kubeconfig="/tmp/kubeconfig",
            namespace="k9b",
            artifact_dir=tmp_path,
            timeout_seconds=1,  # Reduced from 2s - retry loop is fast with no-op sleep
        )

        assert result.passed is False
        assert result.backend_reachable is False
        assert result.attempt_count >= 1
        assert "failed after" in result.message
        assert result.failure_class == "backend_service_unreachable_from_scheduler"

    def test_backend_connectivity_result_to_dict_includes_attempt_count(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """BackendConnectivityResult.to_dict() must include attempt_count for artifact visibility."""
        from scripts.k9b_otel_demo_lab_backend_connectivity import (
            BackendConnectivityResult,
        )

        result = BackendConnectivityResult(
            passed=True,
            backend_reachable=True,
            incidents_endpoint_status=200,
            incidents_total=0,
            attempt_count=3,
        )

        result_dict = result.to_dict()
        assert "attempt_count" in result_dict
        assert result_dict["attempt_count"] == 3


class TestBackendConnectivityResultContract:
    """Tests for BackendConnectivityResult data class."""

    def test_result_has_required_fields(self) -> None:
        """Result must have all required fields for artifact compatibility."""
        from scripts.k9b_otel_demo_lab_backend_connectivity import (
            BackendConnectivityResult,
        )

        result = BackendConnectivityResult()

        # All required fields must exist
        assert hasattr(result, "passed")
        assert hasattr(result, "failure_class")
        assert hasattr(result, "message")
        assert hasattr(result, "backend_reachable")
        assert hasattr(result, "incidents_endpoint_status")
        assert hasattr(result, "incidents_total")
        assert hasattr(result, "incidents_found")
        assert hasattr(result, "check_method")
        assert hasattr(result, "duration_seconds")
        assert hasattr(result, "attempt_count")

    def test_result_to_dict_contains_all_fields(self) -> None:
        """to_dict() must serialize all fields for artifact writing."""
        from scripts.k9b_otel_demo_lab_backend_connectivity import (
            BackendConnectivityResult,
        )

        result = BackendConnectivityResult(
            passed=True,
            failure_class=None,
            message="Test message",
            backend_reachable=True,
            incidents_endpoint_status=200,
            incidents_total=5,
            incidents_found=[{"id": 1}],
            check_method="scheduler-exec",
            duration_seconds=1.5,
            attempt_count=2,
        )

        result_dict = result.to_dict()

        assert result_dict["passed"] is True
        assert result_dict["failure_class"] is None
        assert result_dict["message"] == "Test message"
        assert result_dict["backend_reachable"] is True
        assert result_dict["incidents_endpoint_status"] == 200
        assert result_dict["incidents_total"] == 5
        assert result_dict["incidents_found"] == [{"id": 1}]
        assert result_dict["check_method"] == "scheduler-exec"
        assert result_dict["duration_seconds"] == 1.5
        assert result_dict["attempt_count"] == 2
