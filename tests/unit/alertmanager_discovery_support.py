"""Shared test support module for Alertmanager discovery tests.

This module provides shared fixtures, builders, and mock helpers for alertmanager
discovery tests. It is NOT a test file (no test_ functions/classes) and will not
be collected by pytest.

Import this module in test files that need shared test infrastructure.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

from k8s_diag_agent.external_analysis.alertmanager_discovery import (
    AlertmanagerSource,
    AlertmanagerSourceInventory,
    AlertmanagerSourceOrigin,
    AlertmanagerSourceState,
    DiscoveryResult,
)

# =============================================================================
# Constants
# =============================================================================

SAMPLE_KUBECTL_ALERTMANAGER_OUTPUT = {
    "apiVersion": "monitoring.coreos.com/v1",
    "kind": "AlertmanagerList",
    "items": [
        {
            "metadata": {"name": "main", "namespace": "monitoring"},
            "spec": {},
        },
        {
            "metadata": {"name": "long-lasting", "namespace": "observability"},
            "spec": {},
        },
    ],
}

SAMPLE_KUBECTL_PROMETHEUS_OUTPUT = {
    "apiVersion": "monitoring.coreos.com/v1",
    "kind": "PrometheusList",
    "items": [
        {
            "metadata": {"name": "k8s", "namespace": "monitoring"},
            "spec": {
                "alerting": {
                    "alertmanagers": [
                        {"name": "main", "namespace": "monitoring"}
                    ]
                }
            },
        }
    ],
}

SAMPLE_KUBECTL_SERVICE_OUTPUT = {
    "apiVersion": "v1",
    "kind": "ServiceList",
    "items": [
        {
            "metadata": {"name": "alertmanager-main", "namespace": "monitoring"},
            "spec": {"ports": [{"port": 9093, "targetPort": 9093}]},
        }
    ],
}

SAMPLE_VERIFICATION_RESPONSE = {
    "status": "success",
    "data": {"versionInfo": {"version": "0.25.0"}},
}


# =============================================================================
# Builder functions
# =============================================================================

def make_source(
    source_id: str = "test:source",
    endpoint: str = "http://alertmanager:9093",
    namespace: str | None = None,
    name: str | None = None,
    origin: AlertmanagerSourceOrigin = AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
    state: AlertmanagerSourceState = AlertmanagerSourceState.DISCOVERED,
    cluster_label: str | None = None,
    cluster_context: str | None = None,
    **kwargs: Any,
) -> AlertmanagerSource:
    """Create an AlertmanagerSource with sensible defaults for testing."""
    return AlertmanagerSource(
        source_id=source_id,
        endpoint=endpoint,
        namespace=namespace,
        name=name,
        origin=origin,
        state=state,
        cluster_label=cluster_label,
        cluster_context=cluster_context,
        **kwargs,
    )


def make_crd_source(
    namespace: str = "monitoring",
    name: str = "alertmanager-main",
    endpoint: str | None = None,
    **kwargs: Any,
) -> AlertmanagerSource:
    """Create a CRD-sourced AlertmanagerSource."""
    if endpoint is None:
        endpoint = f"http://alertmanager-main.{namespace}:9093"
    return make_source(
        source_id=f"crd:{namespace}/{name}",
        endpoint=endpoint,
        namespace=namespace,
        name=name,
        origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
        **kwargs,
    )


def make_manual_source(
    source_id: str = "manual:test",
    endpoint: str = "http://custom:9093",
    **kwargs: Any,
) -> AlertmanagerSource:
    """Create a manual AlertmanagerSource."""
    return make_source(
        source_id=source_id,
        endpoint=endpoint,
        origin=AlertmanagerSourceOrigin.MANUAL,
        state=AlertmanagerSourceState.MANUAL,
        **kwargs,
    )


def make_inventory(*sources: AlertmanagerSource) -> AlertmanagerSourceInventory:
    """Create an inventory with the given sources."""
    inventory = AlertmanagerSourceInventory()
    for source in sources:
        inventory.add_source(source)
    return inventory


def make_discovery_result(
    sources: list[AlertmanagerSource] | tuple[AlertmanagerSource, ...] = (),
    errors: list[str] | tuple[str, ...] = (),
    strategy: str = "test-strategy",
) -> DiscoveryResult:
    """Create a DiscoveryResult with sensible defaults."""
    return DiscoveryResult(
        sources=sources,
        errors=errors,
        strategy=strategy,
    )


# =============================================================================
# Mock helpers
# =============================================================================

def make_mock_kubectl_response(
    output: dict[str, Any],
    returncode: int = 0,
    stderr: str = "",
) -> MagicMock:
    """Create a mock subprocess result for kubectl commands."""
    mock = MagicMock()
    mock.returncode = returncode
    mock.stdout = json.dumps(output)
    mock.stderr = stderr
    return mock


def make_mock_urlopen_response(
    status: int = 200,
    body: dict[str, Any] | None = None,
) -> MagicMock:
    """Create a mock urlopen response."""
    mock = MagicMock()
    mock.status = status
    mock.read.return_value = json.dumps(body or {}).encode()
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    return mock


def mock_successful_verification() -> MagicMock:
    """Create a mock urlopen that returns successful verification."""
    return make_mock_urlopen_response(
        status=200,
        body=SAMPLE_VERIFICATION_RESPONSE,
    )


def mock_failed_verification(reason: str = "Connection refused") -> MagicMock:
    """Create a mock urlopen that raises a verification error."""
    import urllib.error
    mock = MagicMock()
    mock.__enter__ = MagicMock(side_effect=urllib.error.URLError(reason))
    mock.__exit__ = MagicMock(return_value=False)
    return mock
