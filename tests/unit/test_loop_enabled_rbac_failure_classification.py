"""Tests proving RBAC/read failures don't collapse into env-missing.

These tests verify that:
1. RBAC denied errors return reason: "automatic_loop_env_rbac_denied" (NOT env-missing)
2. Network/timeout errors return reason: "automatic_loop_env_read_failed" (NOT env-missing)
3. Deployment read errors are properly classified

Architecture note:
    The loop check runs from the GitHub runner, not the scheduler pod.
    The runner uses k9b-live-lab-admin kubeconfig which should have RBAC to read deployments.
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
    DeploymentReadError,
    LoopEnabledCheckResult,
    get_automatic_loop_enabled_with_reason,
)


class TestDeploymentReadErrorClassification:
    """Tests for DeploymentReadError classification."""

    def test_rbac_denial_detected_forbidden(self) -> None:
        """RBAC Forbidden errors should be detected."""
        error = DeploymentReadError(
            message='deployments.apps "k9b-scheduler" is forbidden',
            returncode=1,
            stderr='Error from server (Forbidden): deployments.apps "k9b-scheduler" is forbidden: User "system:serviceaccount:github:runner" cannot get resource "deployments"',
        )
        assert error.is_rbac_denied() is True
        assert error.is_not_found() is False

    def test_rbac_denial_detected_unauthorized(self) -> None:
        """RBAC Unauthorized errors should be detected."""
        error = DeploymentReadError(
            message="Unauthorized access",
            returncode=1,
            stderr="Unauthorized: the server does not have the resource",
        )
        assert error.is_rbac_denied() is True

    def test_rbac_denial_detected_denied(self) -> None:
        """RBAC 'denied' keyword should be detected."""
        error = DeploymentReadError(
            message="Access denied",
            returncode=1,
            stderr="Error: access denied to read deployment",
        )
        assert error.is_rbac_denied() is True

    def test_rbac_denial_detected_cannot_get(self) -> None:
        """RBAC 'cannot get' phrase should be detected."""
        error = DeploymentReadError(
            message="Cannot get deployment",
            returncode=1,
            stderr="error: the server could not find the requested resource, User cannot get deployment",
        )
        assert error.is_rbac_denied() is True

    def test_not_found_detected(self) -> None:
        """Not found errors should be detected."""
        error = DeploymentReadError(
            message="Deployment not found",
            returncode=1,
            stderr='error: deployments.apps "k9b-scheduler" not found',
        )
        assert error.is_rbac_denied() is False
        assert error.is_not_found() is True

    def test_not_found_no_resources(self) -> None:
        """'No resources found' should be detected as not found."""
        error = DeploymentReadError(
            message="No resources found",
            returncode=0,
            stderr="No resources found in k9b namespace.",
        )
        # returncode 0 but still detected as not found
        assert error.is_not_found() is True

    def test_network_timeout_not_rbac(self) -> None:
        """Network/timeout errors should NOT be classified as RBAC."""
        error = DeploymentReadError(
            message="Timeout reading deployment",
            returncode=None,
            stderr="Command timed out after 30 seconds",
        )
        assert error.is_rbac_denied() is False
        assert error.is_not_found() is False


class TestLoopEnabledCheckResultReasonCodes:
    """Tests verifying correct reason codes are returned for different scenarios.

    These tests use monkeypatch to inject deterministic test cases for each branch.
    """

    def test_loop_enabled_classifies_env_var_from_deployment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Env var found and enabled in deployment returns correct reason."""

        def fake_read_deployment(
            kubeconfig: str | None,
            namespace: str,
            deployment: str,
            env_var: str,
        ) -> tuple[str | None, DeploymentReadError | None]:
            # Simulate deployment with K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED=true
            return "true", None

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_loop_gate._read_deployment_env_value",
            fake_read_deployment,
        )

        enabled, result = get_automatic_loop_enabled_with_reason(
            kubeconfig="/tmp/kubeconfig",
            namespace="k9b",
            allow_env_fallback=False,
        )

        assert enabled is True
        assert result.reason == "env_var_from_deployment"
        assert result.source == "deployment"

    def test_loop_enabled_classifies_env_var_not_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Env var found but set to false returns correct reason."""

        def fake_read_deployment(
            kubeconfig: str | None,
            namespace: str,
            deployment: str,
            env_var: str,
        ) -> tuple[str | None, DeploymentReadError | None]:
            # Simulate deployment with K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED=false
            return "false", None

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_loop_gate._read_deployment_env_value",
            fake_read_deployment,
        )

        enabled, result = get_automatic_loop_enabled_with_reason(
            kubeconfig="/tmp/kubeconfig",
            namespace="k9b",
            allow_env_fallback=False,
        )

        assert enabled is False
        assert result.reason == "env_var_not_enabled"
        assert result.source == "deployment"

    def test_loop_enabled_classifies_env_var_not_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Env var not in deployment returns correct reason."""

        def fake_read_deployment(
            kubeconfig: str | None,
            namespace: str,
            deployment: str,
            env_var: str,
        ) -> tuple[str | None, DeploymentReadError | None]:
            # Simulate deployment exists but env var is not set
            return None, None

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_loop_gate._read_deployment_env_value",
            fake_read_deployment,
        )

        enabled, result = get_automatic_loop_enabled_with_reason(
            kubeconfig="/tmp/kubeconfig",
            namespace="k9b",
            allow_env_fallback=False,
        )

        assert enabled is False
        assert result.reason == "env_var_not_set"
        assert result.source == "deployment"

    def test_loop_enabled_classifies_rbac_denied(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """RBAC denied returns 'automatic_loop_env_rbac_denied' reason."""

        def fake_read_deployment(
            kubeconfig: str | None,
            namespace: str,
            deployment: str,
            env_var: str,
        ) -> tuple[str | None, DeploymentReadError | None]:
            # Simulate RBAC denial
            return None, DeploymentReadError(
                message="forbidden",
                returncode=1,
                stderr='Error from server (Forbidden): deployments.apps "k9b-scheduler" is forbidden: User "system:serviceaccount:github:runner" cannot get resource "deployments"',
            )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_loop_gate._read_deployment_env_value",
            fake_read_deployment,
        )

        enabled, result = get_automatic_loop_enabled_with_reason(
            kubeconfig="/tmp/kubeconfig",
            namespace="k9b",
            allow_env_fallback=False,
        )

        assert enabled is False
        assert result.reason == "automatic_loop_env_rbac_denied"
        assert result.source == "error"
        assert result.error_message is not None
        assert "forbidden" in result.error_message.lower()

    def test_loop_enabled_classifies_read_failed_network(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Network/timeout error returns 'automatic_loop_env_read_failed' reason."""

        def fake_read_deployment(
            kubeconfig: str | None,
            namespace: str,
            deployment: str,
            env_var: str,
        ) -> tuple[str | None, DeploymentReadError | None]:
            # Simulate network timeout
            return None, DeploymentReadError(
                message="Timeout reading deployment",
                returncode=None,
                stderr="Command timed out after 30 seconds",
            )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_loop_gate._read_deployment_env_value",
            fake_read_deployment,
        )

        enabled, result = get_automatic_loop_enabled_with_reason(
            kubeconfig="/tmp/kubeconfig",
            namespace="k9b",
            allow_env_fallback=False,
        )

        assert enabled is False
        assert result.reason == "automatic_loop_env_read_failed"
        assert result.source == "error"
        assert result.error_message is not None

    def test_loop_enabled_classifies_read_failed_not_found(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Not found error returns 'automatic_loop_env_read_failed' reason."""

        def fake_read_deployment(
            kubeconfig: str | None,
            namespace: str,
            deployment: str,
            env_var: str,
        ) -> tuple[str | None, DeploymentReadError | None]:
            # Simulate not found (not RBAC denial)
            return None, DeploymentReadError(
                message="Deployment not found",
                returncode=1,
                stderr='error: deployments.apps "k9b-scheduler" not found',
            )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_loop_gate._read_deployment_env_value",
            fake_read_deployment,
        )

        enabled, result = get_automatic_loop_enabled_with_reason(
            kubeconfig="/tmp/kubeconfig",
            namespace="k9b",
            allow_env_fallback=False,
        )

        # Not found is NOT RBAC denial, so it goes to read_failed
        assert enabled is False
        assert result.reason == "automatic_loop_env_read_failed"
        assert result.source == "error"

    def test_loop_enabled_uses_env_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Env var not set with allow_env_fallback=True uses os.environ."""

        def fake_read_deployment(
            kubeconfig: str | None,
            namespace: str,
            deployment: str,
            env_var: str,
        ) -> tuple[str | None, DeploymentReadError | None]:
            # Simulate deployment exists but env var is not set
            return None, None

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_loop_gate._read_deployment_env_value",
            fake_read_deployment,
        )
        monkeypatch.setenv("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED", "true")

        enabled, result = get_automatic_loop_enabled_with_reason(
            kubeconfig="/tmp/kubeconfig",
            namespace="k9b",
            allow_env_fallback=True,
        )

        assert enabled is True
        assert result.reason == "env_var_from_fallback"
        assert result.source == "environment"


class TestLoopEnabledCheckResultDataclass:
    """Tests for LoopEnabledCheckResult structure."""

    def test_result_has_required_fields(self) -> None:
        """Result should have enabled, source, and reason fields."""
        result = LoopEnabledCheckResult(
            enabled=False,
            source="error",
            reason="automatic_loop_env_rbac_denied",
            error_message="Forbidden access",
        )

        assert result.enabled is False
        assert result.source == "error"
        assert result.reason == "automatic_loop_env_rbac_denied"
        assert result.error_message == "Forbidden access"

    def test_result_to_dict(self) -> None:
        """Result should serialize to dict correctly."""
        result = LoopEnabledCheckResult(
            enabled=True,
            source="deployment",
            reason="env_var_from_deployment",
        )

        d = result.to_dict()
        assert d["enabled"] is True
        assert d["source"] == "deployment"
        assert d["reason"] == "env_var_from_deployment"
        assert "error_message" not in d

    def test_result_to_dict_with_error(self) -> None:
        """Result with error should include error_message in dict."""
        result = LoopEnabledCheckResult(
            enabled=False,
            source="error",
            reason="automatic_loop_env_rbac_denied",
            error_message="RBAC denied",
        )

        d = result.to_dict()
        assert d["enabled"] is False
        assert d["source"] == "error"
        assert d["reason"] == "automatic_loop_env_rbac_denied"
        assert d["error_message"] == "RBAC denied"


class TestReasonCodeSemantics:
    """Tests verifying reason code semantics are correct."""

    def test_rbac_denied_semantics(self) -> None:
        """automatic_loop_env_rbac_denied means: cannot read deployment due to permissions."""
        result = LoopEnabledCheckResult(
            enabled=False,
            source="error",
            reason="automatic_loop_env_rbac_denied",
            error_message="Forbidden: cannot get deployment",
        )

        # This is NOT the same as env_var_not_set
        # It means we TRIED to read but WERE DENIED
        assert result.reason == "automatic_loop_env_rbac_denied"
        assert result.enabled is False

    def test_read_failed_semantics(self) -> None:
        """automatic_loop_env_read_failed means: cannot read deployment (network/timeout)."""
        result = LoopEnabledCheckResult(
            enabled=False,
            source="error",
            reason="automatic_loop_env_read_failed",
            error_message="Connection timeout",
        )

        # This is NOT the same as env_var_not_set
        # It means we TRIED to read but FAILED due to network/timeout
        assert result.reason == "automatic_loop_env_read_failed"
        assert result.enabled is False

    def test_env_var_not_set_semantics(self) -> None:
        """env_var_not_set means: deployment was readable but env var is not configured."""
        result = LoopEnabledCheckResult(
            enabled=False,
            source="deployment",
            reason="env_var_not_set",
        )

        # This means: we could read the deployment, but the env var was not set
        # This is DIFFERENT from RBAC or network failure
        assert result.reason == "env_var_not_set"
        assert result.enabled is False
