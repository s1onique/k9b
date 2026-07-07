"""Unit tests for Alertmanager source reconciliation keys.

Tests for LogicalSourceKey and endpoint normalization.
"""

from __future__ import annotations

from k8s_diag_agent.external_analysis.alertmanager_discovery_backing_identity import (
    BackingPodIdentity,
)
from k8s_diag_agent.external_analysis.alertmanager_discovery_models import (
    AlertmanagerSource,
    AlertmanagerSourceOrigin,
    AlertmanagerSourceState,
)
from k8s_diag_agent.external_analysis.alertmanager_source_reconciliation_keys import (
    compute_logical_source_key,
    normalize_endpoint,
)


def _make_source(
    source_id: str,
    endpoint: str,
    namespace: str = "monitoring",
    name: str = "alertmanager",
) -> AlertmanagerSource:
    """Create a test AlertmanagerSource."""
    return AlertmanagerSource(
        source_id=source_id,
        endpoint=endpoint,
        namespace=namespace,
        name=name,
        origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        state=AlertmanagerSourceState.DISCOVERED,
    )


class TestLogicalSourceKey:
    """Tests for LogicalSourceKey computation."""

    def test_pod_uid_based_key(self) -> None:
        """Logical key uses pod UIDs when available."""
        source = _make_source(
            source_id="service:monitoring/alertmanager",
            endpoint="http://alertmanager.monitoring:9093",
            namespace="monitoring",
            name="alertmanager",
        )
        backing = BackingPodIdentity(
            kind="backing_pods",
            uid_set=frozenset({"uid-1", "uid-2"}),
            name_set=frozenset(),
            service_names=("alertmanager",),
        )

        key = compute_logical_source_key(source, backing, "test-context")

        assert key.identity_kind == "backing_pods"
        assert set(key.identity_value) == {"uid-1", "uid-2"}
        assert key.cluster_context == "test-context"
        assert key.namespace == "monitoring"

    def test_endpoint_fallback_key(self) -> None:
        """Logical key uses endpoint when no backing pod info."""
        source = _make_source(
            source_id="service:monitoring/alertmanager",
            endpoint="http://alertmanager.monitoring:9093",
            namespace="monitoring",
            name="alertmanager",
        )

        key = compute_logical_source_key(source, None, "test-context")

        assert key.identity_kind == "endpoint"
        assert key.identity_value == ("alertmanager.monitoring:9093",)


class TestNormalizeEndpoint:
    """Tests for endpoint normalization."""

    def test_strips_http_protocol(self) -> None:
        """HTTP protocol prefix is stripped."""
        assert normalize_endpoint("http://example.com:9093/") == "example.com:9093"

    def test_strips_https_protocol(self) -> None:
        """HTTPS protocol prefix is stripped."""
        assert normalize_endpoint("https://example.com:9093") == "example.com:9093"

    def test_strips_trailing_slash(self) -> None:
        """Trailing slash is stripped."""
        assert normalize_endpoint("example.com:9093/") == "example.com:9093"
