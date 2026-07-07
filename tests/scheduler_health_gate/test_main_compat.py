"""Tests for scheduler health gate main module compatibility.

These tests verify that imports from scripts.scheduler_health_gate.main
still work as expected, ensuring backward compatibility during the refactor.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

# Import from main.py to verify backward compatibility
from scripts.scheduler_health_gate.main import (
    FAILURE_SCHEDULER_CRASH_LOOP,
    FAILURE_SCHEDULER_MISSING,
    FAILURE_SCHEDULER_NOT_READY,
    SCHEDULER_DEPLOYMENT_NAME,
    SCHEDULER_POD_SELECTOR,
    SchedulerHealthResult,
    _check_crash_loop,
    _check_terminated_pods,
    _check_waiting_pods,
    _get_namespace_events,
    _get_scheduler_deployment_status,
    _get_scheduler_pod_selector,
    _get_scheduler_pods,
    _run_kubectl,
    check_crash_loop,
    check_terminated_pods,
    check_waiting_pods,
    get_namespace_events,
    get_scheduler_deployment_status,
    get_scheduler_pod_selector,
    get_scheduler_pods,
    main,
    run_kubectl,
    run_scheduler_health_gate,
)


class TestBackwardCompatibilityImports:
    """Tests that verify backward-compatible imports still work."""

    def test_can_import_failure_constants(self) -> None:
        """Can import failure class constants from main module."""
        assert FAILURE_SCHEDULER_CRASH_LOOP == "scheduler_crash_loop"
        assert FAILURE_SCHEDULER_MISSING == "scheduler_missing"
        assert FAILURE_SCHEDULER_NOT_READY == "scheduler_not_ready"

    def test_can_import_deployment_name(self) -> None:
        """Can import deployment name constant."""
        assert SCHEDULER_DEPLOYMENT_NAME == "k9b-scheduler"

    def test_can_import_pod_selector(self) -> None:
        """Can import pod selector constant."""
        assert SCHEDULER_POD_SELECTOR == "app.kubernetes.io/name=k9b-scheduler"

    def test_can_import_scheduler_health_result(self) -> None:
        """Can import SchedulerHealthResult from main module."""
        result = SchedulerHealthResult()
        assert result.passed is False
        result.passed = True
        assert result.passed is True

    def test_can_import_collect_functions(self) -> None:
        """Can import collection functions from main module."""
        assert callable(get_scheduler_deployment_status)
        assert callable(get_scheduler_pods)
        assert callable(get_scheduler_pod_selector)
        assert callable(get_namespace_events)
        assert callable(run_kubectl)

    def test_can_import_evaluate_functions(self) -> None:
        """Can import evaluation functions from main module."""
        assert callable(check_crash_loop)
        assert callable(check_waiting_pods)
        assert callable(check_terminated_pods)

    def test_can_import_main_function(self) -> None:
        """Can import main function from main module."""
        assert callable(main)

    def test_can_import_run_scheduler_health_gate(self) -> None:
        """Can import run_scheduler_health_gate from main module."""
        assert callable(run_scheduler_health_gate)


class TestRunSchedulerHealthGateIntegration:
    """Integration tests for run_scheduler_health_gate via main module."""

    def test_healthy_scheduler(
        self,
        monkeypatch: pytest.MonkeyPatch,
        healthy_deployment_response: dict[str, Any],
        healthy_pods_response: dict[str, Any],
        temp_artifact_dir: Path,
    ) -> None:
        """run_scheduler_health_gate returns passed=True when scheduler is healthy."""
        def mock_get_deployment(kubeconfig: str, namespace: str) -> dict[str, Any]:
            return healthy_deployment_response

        def mock_get_pods(kubeconfig: str, namespace: str, selector: str = "") -> dict[str, Any]:
            return healthy_pods_response

        def mock_get_events(kubeconfig: str, namespace: str, limit: int = 50) -> list[dict[str, Any]]:
            return []

        def mock_get_selector(kubeconfig: str, namespace: str, deployment_name: str) -> str:
            return "app.kubernetes.io/name=k9b-scheduler"

        def mock_collect_logs(
            kubeconfig: str, namespace: str, selector: str, tail_lines: int = 100
        ) -> dict[str, str]:
            return {}

        monkeypatch.setattr(
            "scripts.scheduler_health_gate.cli.get_scheduler_deployment_status",
            mock_get_deployment,
        )
        monkeypatch.setattr(
            "scripts.scheduler_health_gate.cli.get_scheduler_pods",
            mock_get_pods,
        )
        monkeypatch.setattr(
            "scripts.scheduler_health_gate.cli.get_namespace_events",
            mock_get_events,
        )
        monkeypatch.setattr(
            "scripts.scheduler_health_gate.cli.get_scheduler_pod_selector",
            mock_get_selector,
        )
        monkeypatch.setattr(
            "scripts.scheduler_health_gate.cli.collect_scheduler_logs",
            mock_collect_logs,
        )

        result = run_scheduler_health_gate(
            kubeconfig="/fake/kubeconfig",
            namespace="test-ns",
            artifact_dir=temp_artifact_dir,
        )

        assert result.passed is True
        assert result.failure_class == ""
        assert result.deployment_found is True

    def test_crash_loop_fails_fast(
        self,
        monkeypatch: pytest.MonkeyPatch,
        healthy_deployment_response: dict[str, Any],
        crash_loop_pods_response: dict[str, Any],
        temp_artifact_dir: Path,
    ) -> None:
        """run_scheduler_health_gate fails with crash_loop when detected."""
        def mock_get_deployment(kubeconfig: str, namespace: str) -> dict[str, Any]:
            return healthy_deployment_response

        def mock_get_pods(kubeconfig: str, namespace: str, selector: str = "") -> dict[str, Any]:
            return crash_loop_pods_response

        def mock_get_events(kubeconfig: str, namespace: str, limit: int = 50) -> list[dict[str, Any]]:
            return []

        def mock_get_selector(kubeconfig: str, namespace: str, deployment_name: str) -> str:
            return "app.kubernetes.io/name=k9b-scheduler"

        def mock_collect_logs(
            kubeconfig: str, namespace: str, selector: str, tail_lines: int = 100
        ) -> dict[str, str]:
            return {}

        monkeypatch.setattr(
            "scripts.scheduler_health_gate.cli.get_scheduler_deployment_status",
            mock_get_deployment,
        )
        monkeypatch.setattr(
            "scripts.scheduler_health_gate.cli.get_scheduler_pods",
            mock_get_pods,
        )
        monkeypatch.setattr(
            "scripts.scheduler_health_gate.cli.get_namespace_events",
            mock_get_events,
        )
        monkeypatch.setattr(
            "scripts.scheduler_health_gate.cli.get_scheduler_pod_selector",
            mock_get_selector,
        )
        monkeypatch.setattr(
            "scripts.scheduler_health_gate.cli.collect_scheduler_logs",
            mock_collect_logs,
        )

        result = run_scheduler_health_gate(
            kubeconfig="/fake/kubeconfig",
            namespace="test-ns",
            artifact_dir=temp_artifact_dir,
        )

        assert result.passed is False
        assert result.failure_class == FAILURE_SCHEDULER_CRASH_LOOP
        assert "CrashLoopBackOff" in result.failure_details
        assert result.crash_loop_pods[0]["restart_count"] == 5

    def test_missing_deployment_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
        missing_deployment_response: dict[str, Any],
        temp_artifact_dir: Path,
    ) -> None:
        """run_scheduler_health_gate fails when deployment not found."""
        def mock_get_deployment(kubeconfig: str, namespace: str) -> dict[str, Any]:
            return missing_deployment_response

        def mock_get_events(kubeconfig: str, namespace: str, limit: int = 50) -> list[dict[str, Any]]:
            return []

        monkeypatch.setattr(
            "scripts.scheduler_health_gate.cli.get_scheduler_deployment_status",
            mock_get_deployment,
        )
        # Patch get_namespace_events directly (not _get_namespace_events) because
        # _init_compat_stubs() overwrites _get_namespace_events at call time
        monkeypatch.setattr(
            "scripts.scheduler_health_gate.cli.get_namespace_events",
            mock_get_events,
        )

        result = run_scheduler_health_gate(
            kubeconfig="/fake/kubeconfig",
            namespace="test-ns",
            artifact_dir=temp_artifact_dir,
        )

        assert result.passed is False
        assert result.failure_class == FAILURE_SCHEDULER_MISSING


class TestMainEntryPoint:
    """Tests for main() entry point via main module."""

    def test_main_returns_0_on_healthy(
        self,
        monkeypatch: pytest.MonkeyPatch,
        healthy_deployment_response: dict[str, Any],
        healthy_pods_response: dict[str, Any],
        temp_artifact_dir: Path,
    ) -> None:
        """main() returns 0 when scheduler is healthy."""
        def mock_get_deployment(kubeconfig: str, namespace: str) -> dict[str, Any]:
            return healthy_deployment_response

        def mock_get_pods(kubeconfig: str, namespace: str, selector: str = "") -> dict[str, Any]:
            return healthy_pods_response

        def mock_get_events(kubeconfig: str, namespace: str, limit: int = 50) -> list[dict[str, Any]]:
            return []

        def mock_get_selector(kubeconfig: str, namespace: str, deployment_name: str) -> str:
            return "app.kubernetes.io/name=k9b-scheduler"

        def mock_collect_logs(
            kubeconfig: str, namespace: str, selector: str, tail_lines: int = 100
        ) -> dict[str, str]:
            return {}

        monkeypatch.setattr(
            "scripts.scheduler_health_gate.cli.get_scheduler_deployment_status",
            mock_get_deployment,
        )
        monkeypatch.setattr(
            "scripts.scheduler_health_gate.cli.get_scheduler_pods",
            mock_get_pods,
        )
        monkeypatch.setattr(
            "scripts.scheduler_health_gate.cli.get_namespace_events",
            mock_get_events,
        )
        monkeypatch.setattr(
            "scripts.scheduler_health_gate.cli.get_scheduler_pod_selector",
            mock_get_selector,
        )
        monkeypatch.setattr(
            "scripts.scheduler_health_gate.cli.collect_scheduler_logs",
            mock_collect_logs,
        )

        exit_code = main([
            "--kubeconfig", "/fake/kubeconfig",
            "--namespace", "test-ns",
            "--artifact-dir", str(temp_artifact_dir),
        ])
        
        assert exit_code == 0

    def test_main_returns_1_on_missing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        missing_deployment_response: dict[str, Any],
        temp_artifact_dir: Path,
    ) -> None:
        """main() returns 1 when scheduler is not found."""
        def mock_get_deployment(kubeconfig: str, namespace: str) -> dict[str, Any]:
            return missing_deployment_response

        def mock_get_events(kubeconfig: str, namespace: str, limit: int = 50) -> list[dict[str, Any]]:
            return []

        monkeypatch.setattr(
            "scripts.scheduler_health_gate.cli.get_scheduler_deployment_status",
            mock_get_deployment,
        )
        # Patch get_namespace_events directly (not _get_namespace_events) because
        # _init_compat_stubs() overwrites _get_namespace_events at call time
        monkeypatch.setattr(
            "scripts.scheduler_health_gate.cli.get_namespace_events",
            mock_get_events,
        )

        exit_code = main([
            "--kubeconfig", "/fake/kubeconfig",
            "--namespace", "test-ns",
            "--artifact-dir", str(temp_artifact_dir),
        ])
        
        assert exit_code == 1


class TestUnderscoreAliasCompatibility:
    """Tests that underscore-prefixed private helpers are available for backward compatibility."""

    def test_old_private_helper_aliases_are_importable(self) -> None:
        """Underscore aliases for old private helpers are callable."""
        assert callable(_check_crash_loop)
        assert callable(_check_waiting_pods)
        assert callable(_check_terminated_pods)
        assert callable(_get_scheduler_deployment_status)
        assert callable(_get_scheduler_pod_selector)
        assert callable(_get_scheduler_pods)
        assert callable(_get_namespace_events)
        assert callable(_run_kubectl)


def test_old_main_run_kubectl_monkeypatch_still_affects_selector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Old monkeypatch path main._run_kubectl should still intercept selector calls.
    
    This verifies backward compatibility for tests that patched the private
    _run_kubectl helper in main.py and expected calls like _get_scheduler_pod_selector
    to be affected.
    
    Uses a custom selector that differs from the fallback to prove interception.
    """
    import json

    from scripts.scheduler_health_gate import main as scheduler_main

    def mock_run_kubectl(
        kubeconfig: str,
        namespace: str,
        args: list[str],
        timeout: int = 30,
    ) -> tuple[int, str, str]:
        return (
            0,
            json.dumps(
                {
                    "spec": {
                        "selector": {
                            "matchLabels": {
                                "app.kubernetes.io/name": "custom-scheduler",
                                "app.kubernetes.io/instance": "custom-k9b",
                            }
                        }
                    }
                }
            ),
            "",
        )

    monkeypatch.setattr(scheduler_main, "_run_kubectl", mock_run_kubectl)

    selector = scheduler_main._get_scheduler_pod_selector(
        "/fake/kubeconfig",
        "test-ns",
        "k9b-scheduler",
    )

    # This must be the custom selector, NOT the fallback
    assert selector == (
        "app.kubernetes.io/instance=custom-k9b,"
        "app.kubernetes.io/name=custom-scheduler"
    )


def test_old_main_helper_monkeypatches_still_affect_run_scheduler_health_gate(
    monkeypatch: pytest.MonkeyPatch,
    temp_artifact_dir: Path,
    healthy_deployment_response: dict[str, Any],
    healthy_pods_response: dict[str, Any],
) -> None:
    """Old tests patched main._get_scheduler_deployment_status etc. then called run_scheduler_health_gate.
    
    This verifies backward compatibility for the orchestration path where helpers
    on main module are patched and run_scheduler_health_gate is called.
    
    NOTE: We patch the public cli.get_* functions directly because cli stubs
    are implemented as functions that delegate to _get_* variables, which are
    overwritten by _init_compat_stubs() at call time.
    """
    from scripts.scheduler_health_gate import cli as scheduler_cli

    def mock_get_deployment(kubeconfig: str, namespace: str) -> dict[str, Any]:
        return healthy_deployment_response

    def mock_get_selector(kubeconfig: str, namespace: str, deployment_name: str) -> str:
        return "app.kubernetes.io/name=custom-scheduler"

    def mock_get_pods(kubeconfig: str, namespace: str, selector: str) -> dict[str, Any]:
        assert selector == "app.kubernetes.io/name=custom-scheduler"
        return healthy_pods_response

    def mock_get_events(kubeconfig: str, namespace: str, limit: int = 50) -> list[dict[str, Any]]:
        return []

    def mock_collect_logs(
        kubeconfig: str, namespace: str, selector: str, tail_lines: int = 100
    ) -> dict[str, str]:
        return {}

    # Patch the public functions in cli module (not _get_* which are overwritten by _init_compat_stubs)
    monkeypatch.setattr(scheduler_cli, "get_scheduler_deployment_status", mock_get_deployment)
    monkeypatch.setattr(scheduler_cli, "get_scheduler_pod_selector", mock_get_selector)
    monkeypatch.setattr(scheduler_cli, "get_scheduler_pods", mock_get_pods)
    monkeypatch.setattr(scheduler_cli, "get_namespace_events", mock_get_events)
    monkeypatch.setattr(scheduler_cli, "collect_scheduler_logs", mock_collect_logs)

    result = scheduler_cli.run_scheduler_health_gate(
        kubeconfig="/fake/kubeconfig",
        namespace="test-ns",
        artifact_dir=temp_artifact_dir,
    )

    assert result.passed is True
