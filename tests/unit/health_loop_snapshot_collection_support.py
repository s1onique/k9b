"""Shared test support for alertmanager snapshot collection tests.

This module provides shared fixtures, builders, and mock utilities for
test_health_loop_alertmanager_snapshot_collection_*.py test files.

Usage:
    from tests.unit.health_loop_snapshot_collection_support import (
        make_alertmanager_inventory,
        make_runner,
        make_config,
        mock_urlopen_success,
        mock_urlopen_error,
        mock_port_forward_process,
    )
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from k8s_diag_agent.external_analysis.alertmanager_discovery import (
    AlertmanagerSource,
    AlertmanagerSourceInventory,
    AlertmanagerSourceOrigin,
    AlertmanagerSourceState,
)
from k8s_diag_agent.health.loop import HealthLoopRunner, HealthRunConfig, HealthTarget


@pytest.fixture
def temp_dir() -> Iterator[Path]:
    """Create a temporary directory for test output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def minimal_config(temp_dir: Path) -> HealthRunConfig:
    """Create a minimal health run config."""
    target = HealthTarget(
        context="test-cluster",
        label="test-cluster",
        monitor_health=True,
        watched_helm_releases=(),
        watched_crd_families=(),
        cluster_class="production",
        cluster_role="primary",
        baseline_cohort="test",
    )
    return HealthRunConfig(
        run_label="test-run",
        output_dir=temp_dir,
        collector_version="test",
        targets=(target,),
        peers=(),
        trigger_policy=MagicMock(
            control_plane_version=False,
            watched_helm_release=False,
            watched_crd=False,
            health_regression=False,
            missing_evidence=False,
            manual=False,
        ),
        manual_pairs=(),
        baseline_policy=MagicMock(),
    )


@pytest.fixture
def runner(minimal_config: HealthRunConfig) -> HealthLoopRunner:
    """Create a health loop runner."""
    return HealthLoopRunner(
        config=minimal_config,
        available_contexts=["test-cluster"],
        quiet=True,
    )


def make_config(
    temp_dir: Path,
    run_label: str = "test-run",
) -> HealthRunConfig:
    """Create a HealthRunConfig for testing."""
    target = HealthTarget(
        context="test-cluster",
        label="test-cluster",
        monitor_health=True,
        watched_helm_releases=(),
        watched_crd_families=(),
        cluster_class="production",
        cluster_role="primary",
        baseline_cohort="test",
    )
    return HealthRunConfig(
        run_label=run_label,
        output_dir=temp_dir,
        collector_version="test",
        targets=(target,),
        peers=(),
        trigger_policy=MagicMock(
            control_plane_version=False,
            watched_helm_release=False,
            watched_crd=False,
            health_regression=False,
            missing_evidence=False,
            manual=False,
        ),
        manual_pairs=(),
        baseline_policy=MagicMock(),
    )


def make_runner(
    config: HealthRunConfig,
    available_contexts: list[str] | None = None,
) -> HealthLoopRunner:
    """Create a HealthLoopRunner for testing."""
    if available_contexts is None:
        available_contexts = ["test-cluster"]
    return HealthLoopRunner(
        config=config,
        available_contexts=available_contexts,
        quiet=True,
    )


def make_inventory_with_source(
    source_id: str = "test-source",
    endpoint: str = "http://localhost:9093",
    origin: AlertmanagerSourceOrigin = AlertmanagerSourceOrigin.MANUAL,
    state: AlertmanagerSourceState = AlertmanagerSourceState.MANUAL,
    namespace: str | None = None,
    name: str | None = None,
    cluster_label: str | None = None,
) -> AlertmanagerSourceInventory:
    """Create an inventory with a single source."""
    inventory = AlertmanagerSourceInventory()
    source = AlertmanagerSource(
        source_id=source_id,
        endpoint=endpoint,
        origin=origin,
        state=state,
        cluster_context="test-cluster",
        namespace=namespace,
        name=name,
        cluster_label=cluster_label,
    )
    inventory.add_source(source)
    return inventory


def mock_urlopen_success(
    alerts: list[dict] | None = None,
    status: str = "success",
) -> MagicMock:
    """Create a mock urlopen response for successful alertmanager fetch.

    Args:
        alerts: List of alert dicts (empty list if None)
        status: Status field in response

    Returns:
        Mock response object
    """
    if alerts is None:
        alerts = []
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        "status": status,
        "data": {"alerts": alerts},
    }).encode("utf-8")
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)
    return mock_response


def mock_urlopen_empty() -> MagicMock:
    """Create a mock urlopen response for empty alerts."""
    return mock_urlopen_success(alerts=[])


def mock_urlopen_error(code: int, message: str) -> Exception:
    """Create a mock urlopen that raises HTTPError.

    Args:
        code: HTTP error code
        message: Error message

    Returns:
        Exception object to be used as side_effect
    """
    import urllib.error
    from http.client import HTTPMessage

    return urllib.error.HTTPError(
        url="http://localhost:9093/api/v2/alerts",
        code=code,
        msg=message,
        hdrs=HTTPMessage(),
        fp=None,
    )


def mock_port_forward_process(
    local_port: int = 18457,
    target_port: int = 9093,
    stderr_output: str | None = None,
) -> MagicMock:
    """Create a mock port-forward subprocess.

    Args:
        local_port: Local port for port-forward
        target_port: Target port on remote
        stderr_output: Output to return on stderr read

    Returns:
        Mock process object
    """
    if stderr_output is None:
        stderr_output = f"Forwarding from 127.0.0.1:{local_port} -> {target_port}\n"

    mock_process = MagicMock()
    mock_process.poll.return_value = None  # Still running
    mock_process.stderr = MagicMock()
    mock_process.stderr.read.return_value = stderr_output
    mock_process.stdout = MagicMock()
    mock_process.stdout.read.return_value = ""
    return mock_process


def capture_urlopen_calls() -> tuple[list[str], MagicMock]:
    """Create a mock urlopen that captures called URLs.

    Returns:
        Tuple of (called_urls list, mock_response)
    """
    called_urls: list[str] = []
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps([]).encode()
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    def urlopen_mock(*args: object, **kwargs: object) -> MagicMock:
        request = args[0] if args else None
        if hasattr(request, "full_url"):
            called_urls.append(request.full_url)
        elif hasattr(request, "get_full_url"):
            called_urls.append(request.get_full_url())
        else:
            called_urls.append(str(request))
        return mock_response

    return called_urls, urlopen_mock  # type: ignore[return-value]


def capture_popen_calls() -> tuple[list[list[str]], MagicMock]:
    """Create a mock Popen that captures kubectl commands.

    Returns:
        Tuple of (kubectl_cmds list, mock_process)
    """
    kubectl_cmds: list[list[str]] = []

    def capture_popen(*args: object, **kwargs: object) -> MagicMock:
        kubectl_cmds.append(list(args[0]) if args else [])  # type: ignore[call-overload]
        return mock_port_forward_process()

    return kubectl_cmds, capture_popen  # type: ignore[return-value]
