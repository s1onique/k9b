"""Unit tests for kubernetes_auth module."""
from __future__ import annotations

import logging
import os
from unittest.mock import patch

import pytest

from k8s_diag_agent.kubernetes_auth import (
    AUTH_MODE_VALUES,
    AuthError,
    AuthMode,
    build_kubectl_env,
    get_context_for_auth_mode,
    has_service_account_credentials,
    is_in_cluster,
    log_auth_mode,
    resolve_auth_mode,
    validate_in_cluster_mode,
    validate_kubeconfig_mode,
)


class TestAuthMode:
    """Tests for AuthMode enum."""

    def test_auth_mode_values(self) -> None:
        """Verify all expected auth mode values are defined."""
        assert AUTH_MODE_VALUES == ("auto", "inCluster", "kubeconfig")

    def test_auth_mode_from_string_auto(self) -> None:
        """Test parsing 'auto' mode."""
        assert AuthMode.from_string("auto") == AuthMode.AUTO
        assert AuthMode.from_string("AUTO") == AuthMode.AUTO
        assert AuthMode.from_string("Auto") == AuthMode.AUTO

    def test_auth_mode_from_string_incluster(self) -> None:
        """Test parsing 'inCluster' mode."""
        assert AuthMode.from_string("inCluster") == AuthMode.IN_CLUSTER
        assert AuthMode.from_string("INCLUSTER") == AuthMode.IN_CLUSTER
        assert AuthMode.from_string("InCluster") == AuthMode.IN_CLUSTER

    def test_auth_mode_from_string_kubeconfig(self) -> None:
        """Test parsing 'kubeconfig' mode."""
        assert AuthMode.from_string("kubeconfig") == AuthMode.KUBECONFIG
        assert AuthMode.from_string("KUBECONFIG") == AuthMode.KUBECONFIG
        assert AuthMode.from_string("Kubeconfig") == AuthMode.KUBECONFIG

    def test_auth_mode_from_string_none(self) -> None:
        """Test parsing None defaults to AUTO."""
        assert AuthMode.from_string(None) == AuthMode.AUTO
        assert AuthMode.from_string("") == AuthMode.AUTO

    def test_auth_mode_from_string_invalid(self) -> None:
        """Test parsing invalid value defaults to AUTO."""
        assert AuthMode.from_string("invalid") == AuthMode.AUTO
        assert AuthMode.from_string("something") == AuthMode.AUTO


class TestHasServiceAccountCredentials:
    """Tests for has_service_account_credentials()."""

    def test_returns_true_when_files_exist(self) -> None:
        """Test when token and CA files exist."""
        with patch("pathlib.Path.exists", return_value=True):
            result = has_service_account_credentials()
            assert result is True

    def test_returns_false_when_token_missing(self) -> None:
        """Test when token file is missing."""
        with patch("pathlib.Path.exists", side_effect=[False, True]):
            result = has_service_account_credentials()
            assert result is False

    def test_returns_false_when_ca_missing(self) -> None:
        """Test when CA file is missing."""
        with patch("pathlib.Path.exists", side_effect=[True, False]):
            result = has_service_account_credentials()
            assert result is False


class TestIsInCluster:
    """Tests for in-cluster detection."""

    def test_is_in_cluster_when_credentials_exist_and_no_kubeconfig(self) -> None:
        """Test detection when service account credentials exist and no KUBECONFIG."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("k8s_diag_agent.kubernetes_auth.has_service_account_credentials", return_value=True):
                result = is_in_cluster()
                assert result is True

    def test_is_in_cluster_when_kubeconfig_set(self) -> None:
        """Test detection fails when KUBECONFIG is set."""
        with patch.dict(os.environ, {"KUBECONFIG": "/path/to/kubeconfig"}):
            result = is_in_cluster()
            assert result is False

    def test_is_in_cluster_false_when_credentials_missing(self) -> None:
        """Test detection fails when credentials are missing."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("k8s_diag_agent.kubernetes_auth.has_service_account_credentials", return_value=False):
                result = is_in_cluster()
                assert result is False


class TestValidateInClusterMode:
    """Tests for validate_in_cluster_mode()."""

    def test_does_not_raise_when_credentials_exist(self) -> None:
        """Test no error when credentials exist."""
        with patch("k8s_diag_agent.kubernetes_auth.has_service_account_credentials", return_value=True):
            validate_in_cluster_mode()  # Should not raise

    def test_raises_auth_error_when_credentials_missing(self) -> None:
        """Test AuthError when credentials are missing."""
        with patch("k8s_diag_agent.kubernetes_auth.has_service_account_credentials", return_value=False):
            with pytest.raises(AuthError) as exc_info:
                validate_in_cluster_mode()
            assert "inCluster" in str(exc_info.value)


class TestValidateKubeconfigMode:
    """Tests for validate_kubeconfig_mode()."""

    def test_does_not_raise_when_kubeconfig_enabled(self) -> None:
        """Test no error when kubeconfig is enabled."""
        validate_kubeconfig_mode(kubeconfig_enabled=True)  # Should not raise

    def test_does_not_raise_when_kubeconfig_env_set(self) -> None:
        """Test no error when KUBECONFIG env is set."""
        with patch.dict(os.environ, {"KUBECONFIG": "/path/to/kubeconfig"}):
            validate_kubeconfig_mode(kubeconfig_enabled=False)  # Should not raise

    def test_raises_auth_error_when_no_kubeconfig(self) -> None:
        """Test AuthError when no kubeconfig is available."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(AuthError) as exc_info:
                validate_kubeconfig_mode(kubeconfig_enabled=False)
            assert "kubeconfig" in str(exc_info.value)


class TestResolveAuthMode:
    """Tests for auth mode resolution."""

    def test_explicit_incluster_raises_when_no_credentials(self) -> None:
        """Test explicit inCluster raises AuthError when no credentials."""
        with patch("k8s_diag_agent.kubernetes_auth.has_service_account_credentials", return_value=False):
            with pytest.raises(AuthError):
                resolve_auth_mode("inCluster", kubeconfig_enabled=True)

    def test_explicit_incluster_succeeds_with_credentials(self) -> None:
        """Test explicit inCluster succeeds with credentials."""
        with patch("k8s_diag_agent.kubernetes_auth.has_service_account_credentials", return_value=True):
            result = resolve_auth_mode("inCluster", kubeconfig_enabled=True)
            assert result == AuthMode.IN_CLUSTER

    def test_explicit_incluster_works_even_with_kubeconfig_env(self) -> None:
        """Test inCluster mode selected even with KUBECONFIG env set."""
        with patch.dict(os.environ, {"KUBECONFIG": "/path/to/kubeconfig"}):
            with patch("k8s_diag_agent.kubernetes_auth.has_service_account_credentials", return_value=True):
                result = resolve_auth_mode("inCluster", kubeconfig_enabled=True)
                assert result == AuthMode.IN_CLUSTER

    def test_explicit_kubeconfig_raises_when_no_kubeconfig(self) -> None:
        """Test explicit kubeconfig raises AuthError when no kubeconfig."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(AuthError):
                resolve_auth_mode("kubeconfig", kubeconfig_enabled=False)

    def test_explicit_kubeconfig_succeeds_when_enabled(self) -> None:
        """Test kubeconfig mode succeeds when kubeconfig is enabled."""
        with patch.dict(os.environ, {}, clear=True):
            result = resolve_auth_mode("kubeconfig", kubeconfig_enabled=True)
            assert result == AuthMode.KUBECONFIG

    def test_explicit_kubeconfig_succeeds_when_env_set(self) -> None:
        """Test kubeconfig mode succeeds when KUBECONFIG env is set."""
        with patch.dict(os.environ, {"KUBECONFIG": "/path/to/kubeconfig"}):
            result = resolve_auth_mode("kubeconfig", kubeconfig_enabled=False)
            assert result == AuthMode.KUBECONFIG

    def test_auto_prefers_kubeconfig_env(self) -> None:
        """Test auto mode prefers kubeconfig when env and enabled."""
        with patch.dict(os.environ, {"KUBECONFIG": "/path/to/kubeconfig"}):
            result = resolve_auth_mode("auto", kubeconfig_enabled=True)
            assert result == AuthMode.KUBECONFIG

    def test_auto_uses_in_cluster_when_detected(self) -> None:
        """Test auto mode uses in-cluster when detected."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("k8s_diag_agent.kubernetes_auth.is_in_cluster", return_value=True):
                result = resolve_auth_mode("auto", kubeconfig_enabled=False)
                assert result == AuthMode.IN_CLUSTER

    def test_auto_fallback_to_kubeconfig(self) -> None:
        """Test auto mode falls back to kubeconfig when available."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("k8s_diag_agent.kubernetes_auth.is_in_cluster", return_value=False):
                result = resolve_auth_mode("auto", kubeconfig_enabled=True)
                assert result == AuthMode.KUBECONFIG

    def test_auto_best_effort_when_nothing_available(self) -> None:
        """Test auto mode falls back to in-cluster as best effort."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("k8s_diag_agent.kubernetes_auth.is_in_cluster", return_value=False):
                result = resolve_auth_mode("auto", kubeconfig_enabled=False)
                assert result == AuthMode.IN_CLUSTER


class TestGetContextForAuthMode:
    """Tests for get_context_for_auth_mode."""

    def test_in_cluster_returns_in_cluster(self) -> None:
        """Test in-cluster mode returns 'in-cluster' context."""
        result = get_context_for_auth_mode(AuthMode.IN_CLUSTER)
        assert result == "in-cluster"

    def test_kubeconfig_returns_none(self) -> None:
        """Test kubeconfig mode returns None (use default)."""
        result = get_context_for_auth_mode(AuthMode.KUBECONFIG)
        assert result is None

    def test_auto_returns_none(self) -> None:
        """Test auto mode returns None."""
        result = get_context_for_auth_mode(AuthMode.AUTO)
        assert result is None


class TestBuildKubectlEnv:
    """Tests for build_kubectl_env."""

    def test_in_cluster_unsets_kubeconfig(self) -> None:
        """Test in-cluster mode unsets KUBECONFIG."""
        result = build_kubectl_env(AuthMode.IN_CLUSTER)
        assert result.get("KUBECONFIG") is None

    def test_kubeconfig_returns_empty(self) -> None:
        """Test kubeconfig mode returns empty dict."""
        result = build_kubectl_env(AuthMode.KUBECONFIG)
        assert result == {}

    def test_auto_returns_empty(self) -> None:
        """Test auto mode returns empty dict."""
        result = build_kubectl_env(AuthMode.AUTO)
        assert result == {}


class TestLogAuthMode:
    """Tests for log_auth_mode."""

    def test_logs_in_cluster_mode(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test logging for in-cluster mode."""
        with caplog.at_level(logging.INFO):
            log_auth_mode(AuthMode.IN_CLUSTER)
        assert any("in-cluster service account" in record.message for record in caplog.records)

    def test_logs_kubeconfig_mode(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test logging for kubeconfig mode."""
        with caplog.at_level(logging.INFO):
            log_auth_mode(AuthMode.KUBECONFIG)
        assert any("kubeconfig file" in record.message for record in caplog.records)

    def test_logs_auto_mode(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test logging for auto mode."""
        with caplog.at_level(logging.INFO):
            log_auth_mode(AuthMode.AUTO)
        assert any("auto-detected" in record.message for record in caplog.records)

    def test_does_not_log_sensitive_paths(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test that auth mode logging doesn't expose sensitive paths."""
        with caplog.at_level(logging.INFO):
            log_auth_mode(AuthMode.KUBECONFIG)
        # Should not contain path-like patterns
        for record in caplog.records:
            assert "/home/" not in record.message
            assert "/.kube/" not in record.message


class TestAuthError:
    """Tests for AuthError exception."""

    def test_auth_error_is_exception(self) -> None:
        """Test AuthError inherits from Exception."""
        error = AuthError("test error")
        assert isinstance(error, Exception)

    def test_auth_error_message(self) -> None:
        """Test AuthError preserves message."""
        error = AuthError("test error message")
        assert str(error) == "test error message"
