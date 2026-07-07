"""Pytest configuration for kubectl execution guard.

This module provides a tripwire fixture that prevents unit tests from executing
real kubectl commands. This catches boundary inversion issues where tests patch
the wrong seam (e.g., subprocess.run instead of the actual kubectl execution path).

Usage:
    - All unit tests have real kubectl blocked by default via autouse fixture
    - Mark tests with @pytest.mark.live_kubernetes to allow real kubectl
    - Tests should patch at the call-site seam (e.g., k8s_diag_agent.collect.incident_collectors.kubectl)
      NOT at subprocess.run or other internal paths

Reference: ACT-K9B-KUBECTL-BOUNDARY-REGRESSION01
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "live_kubernetes: mark test as requiring real Kubernetes cluster (skips kubectl guard)",
    )


def _looks_like_kubectl(cmd: object) -> bool:
    """Check if a command looks like a kubectl invocation."""
    # Handle list/tuple form: subprocess.run(["kubectl", "get", "pods"])
    if isinstance(cmd, (list, tuple)) and len(cmd) > 0:
        first_arg = cmd[0]
        cmd_str = str(first_arg)
        return "kubectl" in cmd_str
    # Handle string form: subprocess.run("kubectl get pods", shell=True)
    if isinstance(cmd, str):
        return "kubectl" in cmd
    return False


@pytest.fixture(autouse=True)
def forbid_real_kubectl(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    """Prevent unit tests from executing real kubectl commands.

    This fixture blocks all kubectl execution paths in unit tests by raising
    pytest.fail.Exception if any of the bounded execution functions are called.

    Tests that need real kubectl should be marked with @pytest.mark.live_kubernetes.

    The correct seam to patch in unit tests is at the call site, e.g.:
        monkeypatch.setattr("k8s_diag_agent.collect.incident_collectors.kubectl", fake_kubectl)

    NOT at subprocess.run or other internal paths.
    """
    # Skip guard for tests explicitly marked as live/integration
    if request.node.get_closest_marker("live_kubernetes"):
        return

    def _blocked_kubectl(*args: object, **kwargs: object) -> object:
        pytest.fail(
            "Unit test attempted real kubectl execution. "
            "Patch the call-site seam instead of subprocess.run or run_bounded. "
            "For example: monkeypatch.setattr('k8s_diag_agent.collect.incident_collectors.kubectl', fake_kubectl)"
        )

    # Block the primary bounded execution entry points
    # These are where production code actually spawns kubectl subprocesses
    try:
        from k8s_diag_agent.security import kubectl_bounded

        monkeypatch.setattr(kubectl_bounded, "run_bounded", _blocked_kubectl)
    except ImportError:
        pass  # Module structure may differ; guard at import path

    # Block subprocess.Popen for kubectl commands
    if "subprocess" in sys.modules:
        real_popen = subprocess.Popen

        def _blocked_popen(*args: Any, **kwargs: Any) -> Any:
            cmd = args[0] if args else kwargs.get("args", [])
            if _looks_like_kubectl(cmd):
                pytest.fail(
                    f"Unit test attempted real kubectl via subprocess.Popen: {cmd}. "
                    "Patch the call-site seam instead. "
                    "For example: monkeypatch.setattr('k8s_diag_agent.collect.incident_collectors.kubectl', fake_kubectl)"
                )
            return real_popen(*args, **kwargs)

        monkeypatch.setattr(subprocess, "Popen", _blocked_popen)

    # Block subprocess.run for kubectl commands
    if "subprocess" in sys.modules:
        real_run = subprocess.run

        def _blocked_run(*args: Any, **kwargs: Any) -> Any:
            cmd = args[0] if args else kwargs.get("args", [])
            if _looks_like_kubectl(cmd):
                pytest.fail(
                    f"Unit test attempted real kubectl via subprocess.run: {cmd}. "
                    "Patch the call-site seam instead. "
                    "For example: monkeypatch.setattr('k8s_diag_agent.collect.incident_collectors.kubectl', fake_kubectl)"
                )
            return real_run(*args, **kwargs)

        monkeypatch.setattr(subprocess, "run", _blocked_run)


__all__ = ["forbid_real_kubectl"]
