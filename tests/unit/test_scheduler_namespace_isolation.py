"""Unit tests for scheduler namespace isolation.

Regression tests for namespace isolation in scheduler deployment lookup.

These tests verify that when reading the scheduler deployment, the correct
k9b control-plane namespace is used, NOT the incident namespace.

This is critical for provider smoke tests where:
- k9b backend runs in namespace "k9b"
- OTel demo incidents run in namespace "otel-demo"
- Scheduler deployment k9b-scheduler exists in "k9b" namespace

Bug scenario: If someone passes incident_namespace="otel-demo" to
is_automatic_diagnosis_loop_enabled(), the function should NOT try to
read deployment/k9b-scheduler from namespace "otel-demo".

Architecture note:
    After ACT-K9B-K8S-CLIENT-TEST-HARNESS-UPDATE01, these tests mock
    get_cached_kubernetes_client() instead of subprocess.run since production
    code now uses the Kubernetes Python client boundary.
"""

from __future__ import annotations

import os

import pytest

from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
    get_automatic_loop_enabled_with_reason,
    get_default_k9b_namespace,
    is_automatic_diagnosis_loop_enabled,
)
from tests.unit.k8s_fake_client import FakeKubernetesReadClient


class TestSchedulerNamespaceIsolation:
    """Regression tests for namespace isolation in scheduler deployment lookup."""

    def test_uses_explicit_namespace_parameter_for_scheduler_lookup(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Prove the namespace parameter is used for scheduler deployment lookup."""
        # Track what namespaces were requested
        namespaces_requested: list[str] = []

        class TrackingFakeClient(FakeKubernetesReadClient):
            def read_deployment_env_value(
                self,
                *,
                namespace: str,
                deployment: str,
                container: str | None = None,
                env_name: str,
            ) -> str | None:
                namespaces_requested.append(namespace)
                return "true"

        fake_client = TrackingFakeClient()

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_loop_gate.get_cached_kubernetes_client",
            lambda **kwargs: fake_client,
        )

        # Call with explicit namespace "k9b"
        result = is_automatic_diagnosis_loop_enabled(
            kubeconfig="/tmp/kubeconfig",
            namespace="k9b",
        )

        assert result is True
        # Verify the namespace was k9b, not otel-demo
        assert namespaces_requested == ["k9b"]

    def test_fails_gracefully_when_scheduler_not_in_wrong_namespace(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Prove lookup fails with useful error when scheduler not in target namespace.

        This is the exact failure mode from the live lab:
        'Failed to read deployment k9b-scheduler in namespace otel-demo'

        When someone passes incident_namespace="otel-demo" but scheduler is in "k9b",
        the function should fail gracefully (fall back to env or return False)
        rather than crash.
        """
        # Ensure env var is NOT set (so fallback would return False)
        monkeypatch.delenv("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED", raising=False)

        # Fake client that raises not found (scheduler doesn't exist in otel-demo)
        fake_client = FakeKubernetesReadClient.with_not_found(
            namespace="otel-demo",
            deployment="k9b-scheduler",
        )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_loop_gate.get_cached_kubernetes_client",
            lambda **kwargs: fake_client,
        )

        # Call with wrong namespace (otel-demo) - this is the bug scenario
        enabled, result = get_automatic_loop_enabled_with_reason(
            kubeconfig="/tmp/kubeconfig",
            namespace="otel-demo",  # Wrong namespace - scheduler is in k9b
            allow_env_fallback=False,  # Fail-closed
        )

        # Should fail gracefully
        assert enabled is False
        assert result.source == "error"
        # Should indicate the lookup failed
        assert result.reason in (
            "automatic_loop_env_read_failed",
            "automatic_loop_env_rbac_denied",
        )

    def test_k9b_namespace_can_be_overridden_via_parameter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Prove namespace parameter allows overriding the default 'k9b' namespace.

        This is useful for testing or unusual deployments where k9b runs in
        a different namespace.
        """
        # Track what namespaces were requested
        namespaces_requested: list[str] = []

        class TrackingFakeClient(FakeKubernetesReadClient):
            def read_deployment_env_value(
                self,
                *,
                namespace: str,
                deployment: str,
                container: str | None = None,
                env_name: str,
            ) -> str | None:
                namespaces_requested.append(namespace)
                return "true"

        fake_client = TrackingFakeClient()

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_loop_gate.get_cached_kubernetes_client",
            lambda **kwargs: fake_client,
        )

        # Call with custom namespace
        result = is_automatic_diagnosis_loop_enabled(
            kubeconfig="/tmp/kubeconfig",
            namespace="k9b-custom",  # Custom namespace
        )

        assert result is True
        # Verify the namespace was k9b-custom
        assert "k9b-custom" in namespaces_requested


class TestDefaultNamespaceResolution:
    """Tests for K9B_NAMESPACE environment variable resolution."""

    def test_get_default_k9b_namespace_returns_default_when_env_not_set(self) -> None:
        """Prove default namespace is 'k9b' when K9B_NAMESPACE is not set."""
        env_backup = os.environ.get("K9B_NAMESPACE")
        try:
            # Ensure env var is not set
            if "K9B_NAMESPACE" in os.environ:
                del os.environ["K9B_NAMESPACE"]

            result = get_default_k9b_namespace()
            assert result == "k9b"
        finally:
            if env_backup is not None:
                os.environ["K9B_NAMESPACE"] = env_backup

    def test_get_default_k9b_namespace_respects_env_var(self) -> None:
        """Prove K9B_NAMESPACE env var overrides the default."""
        env_backup = os.environ.get("K9B_NAMESPACE")
        try:
            os.environ["K9B_NAMESPACE"] = "k9b-custom-ns"

            result = get_default_k9b_namespace()
            assert result == "k9b-custom-ns"
        finally:
            if env_backup is not None:
                os.environ["K9B_NAMESPACE"] = env_backup
            elif "K9B_NAMESPACE" in os.environ:
                del os.environ["K9B_NAMESPACE"]

    def test_get_default_k9b_namespace_guards_against_blank_values(self) -> None:
        """Prove blank K9B_NAMESPACE falls back to default 'k9b'."""
        env_backup = os.environ.get("K9B_NAMESPACE")
        try:
            os.environ["K9B_NAMESPACE"] = "   "  # blank with whitespace

            result = get_default_k9b_namespace()
            assert result == "k9b"
        finally:
            if env_backup is not None:
                os.environ["K9B_NAMESPACE"] = env_backup
            elif "K9B_NAMESPACE" in os.environ:
                del os.environ["K9B_NAMESPACE"]


class TestP4cCallerPattern:
    """Regression tests for P4c caller-level namespace handling.

    These tests prove that when P4c-style callers invoke the gate,
    they use get_default_k9b_namespace() for scheduler lookup, NOT the incident namespace.

    This is the exact pattern that should be used by any code that:
    - Has access to incidents in various namespaces (e.g., otel-demo)
    - Needs to check if automatic diagnosis is enabled
    - Should look up the scheduler in the k9b control-plane namespace
    """

    def test_p4c_caller_uses_k9b_namespace_for_scheduler_gate_not_incident_namespace(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Prove P4c-style caller uses k9b namespace for scheduler, not incident namespace.

        This test reproduces the exact failure mode from the live lab:
        - Incident is in namespace "otel-demo"
        - k9b scheduler runs in namespace "k9b"
        - Caller should use get_default_k9b_namespace() to resolve "k9b"
        - NOT pass the incident namespace "otel-demo" to the gate
        """
        # Track what namespaces were requested
        namespaces_requested: list[str] = []

        class TrackingFakeClient(FakeKubernetesReadClient):
            def read_deployment_env_value(
                self,
                *,
                namespace: str,
                deployment: str,
                container: str | None = None,
                env_name: str,
            ) -> str | None:
                namespaces_requested.append(namespace)
                return "true"

        fake_client = TrackingFakeClient()

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_loop_gate.get_cached_kubernetes_client",
            lambda **kwargs: fake_client,
        )

        # Simulate P4c-style caller:
        # - incident_namespace = "otel-demo" (for context)
        # - k9b_namespace = get_default_k9b_namespace() -> "k9b"
        # - Pass k9b_namespace to gate, NOT incident_namespace
        _incident_namespace = "otel-demo"  # noqa: F841 - documented for context
        k9b_namespace = get_default_k9b_namespace()

        # This is the correct pattern:
        # Use k9b_namespace for scheduler lookup, not incident_namespace
        result = get_automatic_loop_enabled_with_reason(
            kubeconfig="/tmp/kubeconfig",
            namespace=k9b_namespace,  # Correct: use k9b namespace
        )

        assert result[0] is True
        # Verify the namespace was k9b, not otel-demo
        assert namespaces_requested == ["k9b"]
        assert "otel-demo" not in namespaces_requested

    def test_incorrect_p4c_caller_pattern_fails_gracefully(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Prove incorrect pattern (passing incident namespace) fails gracefully.

        This documents the bug that should NOT be used:
        - Passing incident_namespace="otel-demo" to the gate
        - When scheduler is actually in "k9b" namespace
        - Should fail-closed (return False) rather than crash
        """
        # Ensure env var is NOT set
        monkeypatch.delenv("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED", raising=False)

        # Fake client that raises not found for the wrong namespace
        fake_client = FakeKubernetesReadClient.with_not_found(
            namespace="otel-demo",
            deployment="k9b-scheduler",
        )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_loop_gate.get_cached_kubernetes_client",
            lambda **kwargs: fake_client,
        )

        # INCORRECT pattern: passing incident namespace
        enabled, check_result = get_automatic_loop_enabled_with_reason(
            kubeconfig="/tmp/kubeconfig",
            namespace="otel-demo",  # Wrong: incident namespace
            allow_env_fallback=False,  # Fail-closed
        )

        # Should fail gracefully
        assert enabled is False
        assert check_result.source == "error"
        assert check_result.reason in (
            "automatic_loop_env_read_failed",
            "automatic_loop_env_rbac_denied",
        )
