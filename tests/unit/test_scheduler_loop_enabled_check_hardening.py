"""Hardening tests for scheduler-based automatic diagnosis loop enabled check.

These tests cover:
- kubeconfig handling (passed to k8s client)
- allow_env_fallback parameter behavior for fail-closed live-lab mode

Architecture note:
    The automatic diagnosis loop is a SCHEDULER feature, not a backend feature.
    These tests verify the checker handles edge cases correctly for live-lab deployment.
    
    After ACT-K9B-K8S-CLIENT-TEST-HARNESS-UPDATE01, these tests mock
    get_cached_kubernetes_client() instead of subprocess.run since production
    code now uses the Kubernetes Python client boundary.
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
    _get_deployment_env_value,
    is_automatic_diagnosis_loop_enabled,
)
from tests.unit.k8s_fake_client import FakeKubernetesReadClient


class TestKubeconfigHandling:
    """Tests for kubeconfig parameter handling in k8s client calls."""

    def test_kubeconfig_none_uses_client_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Prove kubeconfig=None is passed correctly to the k8s client."""
        # Track what parameters were passed to the client
        clients_created: list[dict] = []

        def track_client_creation(**kwargs):
            clients_created.append(kwargs)
            return FakeKubernetesReadClient.with_deployment_env(
                namespace="k9b",
                deployment="k9b-scheduler",
                env_vars={"K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED": "true"},
            )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_loop_gate.get_cached_kubernetes_client",
            track_client_creation,
        )

        _get_deployment_env_value(
            kubeconfig=None,  # Explicitly None
            namespace="k9b",
            deployment="k9b-scheduler",
            env_var="K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED",
        )

        # Verify client was created with kubeconfig=None
        assert len(clients_created) == 1
        assert clients_created[0].get("kubeconfig") is None

    def test_kubeconfig_path_is_passed_to_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Prove kubeconfig path is passed to the k8s client."""
        # Track what parameters were passed to the client
        clients_created: list[dict] = []

        def track_client_creation(**kwargs):
            clients_created.append(kwargs)
            return FakeKubernetesReadClient.with_deployment_env(
                namespace="k9b",
                deployment="k9b-scheduler",
                env_vars={"K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED": "true"},
            )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_loop_gate.get_cached_kubernetes_client",
            track_client_creation,
        )

        _get_deployment_env_value(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            deployment="k9b-scheduler",
            env_var="K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED",
        )

        # Verify client was created with the kubeconfig path
        assert len(clients_created) == 1
        assert clients_created[0].get("kubeconfig") == "/path/to/kubeconfig"


class TestAllowEnvFallback:
    """Tests for allow_env_fallback parameter behavior."""

    def test_returns_false_when_cluster_unreachable_and_fallback_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Prove function returns False when cluster unreachable and allow_env_fallback=False."""
        # Set env var to true - but this should NOT be used
        monkeypatch.setenv("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED", "true")

        # Fake client that raises not found (simulating cluster access issue)
        fake_client = FakeKubernetesReadClient.with_not_found(
            namespace="k9b",
            deployment="k9b-scheduler",
        )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_loop_gate.get_cached_kubernetes_client",
            lambda **kwargs: fake_client,
        )

        result = is_automatic_diagnosis_loop_enabled(
            kubeconfig="/tmp/kubeconfig",
            namespace="k9b",
            allow_env_fallback=False,
        )

        # Should return False (fail-closed) instead of using env
        assert result is False

    def test_returns_true_from_env_when_cluster_unreachable_and_fallback_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Prove function falls back to env when cluster unreachable and allow_env_fallback=True."""
        # Set env var to true
        monkeypatch.setenv("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED", "true")

        # Fake client that raises not found (simulating cluster access issue)
        fake_client = FakeKubernetesReadClient.with_not_found(
            namespace="k9b",
            deployment="k9b-scheduler",
        )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_loop_gate.get_cached_kubernetes_client",
            lambda **kwargs: fake_client,
        )

        result = is_automatic_diagnosis_loop_enabled(
            kubeconfig="/tmp/kubeconfig",
            namespace="k9b",
            allow_env_fallback=True,
        )

        # Should return True (uses env fallback)
        assert result is True

    def test_uses_cluster_when_accessible_regardless_of_fallback_setting(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Prove cluster value is used when accessible, regardless of allow_env_fallback."""
        # Set env var to false (should be ignored)
        monkeypatch.setenv("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED", "false")

        # Fake client returns true from cluster
        fake_client = FakeKubernetesReadClient.with_deployment_env(
            namespace="k9b",
            deployment="k9b-scheduler",
            env_vars={"K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED": "true"},
        )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_loop_gate.get_cached_kubernetes_client",
            lambda **kwargs: fake_client,
        )

        # Even with allow_env_fallback=False, cluster value should be used
        result = is_automatic_diagnosis_loop_enabled(
            kubeconfig="/tmp/kubeconfig",
            namespace="k9b",
            allow_env_fallback=False,
        )

        # Should return True from cluster, not False from env
        assert result is True
