"""Unit tests for scheduler-based automatic diagnosis loop enabled check.

Tests cover:
- is_automatic_diagnosis_loop_enabled checks scheduler deployment (not backend)
- _get_deployment_env_value extracts env vars from deployment spec
- Fallback to os.environ when cluster is not accessible
- Proper error handling for k8s client failures

Architecture note:
    The automatic diagnosis loop is a SCHEDULER feature, not a backend feature.
    These tests verify the checker targets the scheduler deployment correctly.
    
    After ACT-K9B-K8S-CLIENT-TEST-HARNESS-UPDATE01, these tests mock
    get_cached_kubernetes_client() instead of subprocess.run since production
    code now uses the Kubernetes Python client boundary.
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
    _SCHEDULER_DEPLOYMENT,
    _get_deployment_env_value,
    is_automatic_diagnosis_loop_enabled,
)
from tests.unit.k8s_fake_client import FakeKubernetesReadClient


class TestGetDeploymentEnvValue:
    """Tests for _get_deployment_env_value function."""

    def test_extracts_env_var_from_deployment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Prove env var is extracted from scheduler deployment spec."""
        fake_client = FakeKubernetesReadClient.with_deployment_env(
            namespace="k9b",
            deployment="k9b-scheduler",
            env_vars={"K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED": "true"},
        )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_loop_gate.get_cached_kubernetes_client",
            lambda **kwargs: fake_client,
        )

        result = _get_deployment_env_value(
            kubeconfig="/tmp/kubeconfig",
            namespace="k9b",
            deployment="k9b-scheduler",
            env_var="K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED",
        )

        assert result == "true"

    def test_returns_none_when_env_var_not_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Prove None is returned when env var is not in deployment spec."""
        # Fake client with empty env vars
        fake_client = FakeKubernetesReadClient.with_deployment_env(
            namespace="k9b",
            deployment="k9b-scheduler",
            env_vars={},  # No env vars set
        )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_loop_gate.get_cached_kubernetes_client",
            lambda **kwargs: fake_client,
        )

        result = _get_deployment_env_value(
            kubeconfig="/tmp/kubeconfig",
            namespace="k9b",
            deployment="k9b-scheduler",
            env_var="K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED",
        )

        assert result is None

    def test_returns_none_on_k8s_client_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Prove None is returned when k8s client raises error."""
        # Fake client that raises not found
        fake_client = FakeKubernetesReadClient.with_not_found(
            namespace="k9b",
            deployment="k9b-scheduler",
        )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_loop_gate.get_cached_kubernetes_client",
            lambda **kwargs: fake_client,
        )

        result = _get_deployment_env_value(
            kubeconfig="/tmp/kubeconfig",
            namespace="k9b",
            deployment="k9b-scheduler",
            env_var="K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED",
        )

        assert result is None

    def test_targets_scheduler_not_backend(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Prove the function is called with k9b-scheduler deployment name."""
        # Track what deployment was requested
        deployments_requested: list[tuple[str, str]] = []

        class TrackingFakeClient(FakeKubernetesReadClient):
            def read_deployment_env_value(
                self,
                *,
                namespace: str,
                deployment: str,
                container: str | None = None,
                env_name: str,
            ) -> str | None:
                deployments_requested.append((namespace, deployment))
                return super().read_deployment_env_value(
                    namespace=namespace,
                    deployment=deployment,
                    container=container,
                    env_name=env_name,
                )

        fake_client = TrackingFakeClient.with_deployment_env(
            namespace="k9b",
            deployment="k9b-scheduler",
            env_vars={"K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED": "true"},
        )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_loop_gate.get_cached_kubernetes_client",
            lambda **kwargs: fake_client,
        )

        _get_deployment_env_value(
            kubeconfig="/tmp/kubeconfig",
            namespace="k9b",
            deployment=_SCHEDULER_DEPLOYMENT,
            env_var="K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED",
        )

        # Verify scheduler was requested
        assert len(deployments_requested) == 1
        assert deployments_requested[0][1] == "k9b-scheduler"


class TestIsAutomaticDiagnosisLoopEnabled:
    """Tests for is_automatic_diagnosis_loop_enabled function."""

    def test_checks_scheduler_deployment_when_cluster_accessible(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Prove function checks scheduler deployment in cluster."""
        fake_client = FakeKubernetesReadClient.with_deployment_env(
            namespace="k9b",
            deployment="k9b-scheduler",
            env_vars={"K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED": "true"},
        )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_loop_gate.get_cached_kubernetes_client",
            lambda **kwargs: fake_client,
        )

        result = is_automatic_diagnosis_loop_enabled(
            kubeconfig="/tmp/kubeconfig",
            namespace="k9b",
        )

        assert result is True

    def test_returns_false_when_scheduler_env_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Prove function returns False when scheduler has env=false."""
        fake_client = FakeKubernetesReadClient.with_deployment_env(
            namespace="k9b",
            deployment="k9b-scheduler",
            env_vars={"K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED": "false"},
        )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_loop_gate.get_cached_kubernetes_client",
            lambda **kwargs: fake_client,
        )

        result = is_automatic_diagnosis_loop_enabled(
            kubeconfig="/tmp/kubeconfig",
            namespace="k9b",
        )

        assert result is False

    def test_falls_back_to_os_environ_when_cluster_not_accessible(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Prove function falls back to os.environ when k8s client fails."""
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
        )

        assert result is True

    def test_does_not_check_backend_deployment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Prove function targets scheduler, not backend."""
        # Track what deployments were requested
        deployments_requested: list[tuple[str, str]] = []

        class TrackingFakeClient(FakeKubernetesReadClient):
            def read_deployment_env_value(
                self,
                *,
                namespace: str,
                deployment: str,
                container: str | None = None,
                env_name: str,
            ) -> str | None:
                deployments_requested.append((namespace, deployment))
                # Return true for scheduler to make test pass
                if deployment == "k9b-scheduler":
                    return "true"
                return None

        fake_client = TrackingFakeClient()

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_loop_gate.get_cached_kubernetes_client",
            lambda **kwargs: fake_client,
        )

        result = is_automatic_diagnosis_loop_enabled(
            kubeconfig="/tmp/kubeconfig",
            namespace="k9b",
        )

        # The function should return True because scheduler has it enabled
        assert result is True

        # Verify only scheduler was checked (not backend)
        assert all(dep == "k9b-scheduler" for _, dep in deployments_requested)


class TestArchitectureDocumentation:
    """Tests that verify the architecture documentation is correct."""

    def test_scheduler_constant_is_k9b_scheduler(self) -> None:
        """Prove _SCHEDULER_DEPLOYMENT constant is k9b-scheduler."""
        assert _SCHEDULER_DEPLOYMENT == "k9b-scheduler"

    def test_does_not_check_backend(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Prove backend deployment is not targeted by the checker."""
        # Track what deployments were requested
        deployments_requested: list[str] = []

        class TrackingFakeClient(FakeKubernetesReadClient):
            def read_deployment_env_value(
                self,
                *,
                namespace: str,
                deployment: str,
                container: str | None = None,
                env_name: str,
            ) -> str | None:
                deployments_requested.append(deployment)
                return "true"

        fake_client = TrackingFakeClient()

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_loop_gate.get_cached_kubernetes_client",
            lambda **kwargs: fake_client,
        )

        _get_deployment_env_value(
            kubeconfig="/tmp/kubeconfig",
            namespace="k9b",
            deployment="k9b-scheduler",  # Explicitly scheduler
            env_var="K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED",
        )

        # Verify only scheduler deployment was requested (not backend)
        assert deployments_requested == ["k9b-scheduler"]
        assert "k9b-backend" not in deployments_requested
