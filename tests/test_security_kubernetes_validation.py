"""Tests for Kubernetes validation helpers.

These tests verify the security hardening for:
- kube context name validation
- kubernetes namespace validation
- kubernetes resource name validation
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.security.path_validation import (
    SecurityError,
    validate_kube_context_name,
    validate_kubernetes_namespace,
    validate_kubernetes_resource_name,
)


class TestValidateKubeContextName:
    """Tests for validate_kube_context_name function."""

    def test_valid_simple_context(self) -> None:
        """Valid simple context name is accepted."""
        assert validate_kube_context_name("kind-cluster") == "kind-cluster"

    def test_valid_context_with_underscores(self) -> None:
        """Context with underscores is accepted."""
        assert validate_kube_context_name("my_cluster_name") == "my_cluster_name"

    def test_valid_context_with_numbers(self) -> None:
        """Context with numbers is accepted."""
        assert validate_kube_context_name("cluster-123-prod") == "cluster-123-prod"

    def test_valid_context_dots(self) -> None:
        """Context with dots is accepted (DNS-like)."""
        assert validate_kube_context_name("gke.project.zone.cluster") == "gke.project.zone.cluster"

    def test_rejects_empty_string(self) -> None:
        """Empty string is rejected."""
        with pytest.raises(SecurityError, match="cannot be empty"):
            validate_kube_context_name("")

    def test_rejects_whitespace_only(self) -> None:
        """Whitespace-only string is rejected."""
        with pytest.raises(SecurityError, match="whitespace"):
            validate_kube_context_name("   ")

    def test_rejects_leading_trailing_whitespace(self) -> None:
        """Leading/trailing whitespace is rejected."""
        with pytest.raises(SecurityError, match="whitespace"):
            validate_kube_context_name(" context ")

    def test_rejects_null_byte(self) -> None:
        """Null byte is rejected."""
        with pytest.raises(SecurityError, match="null byte"):
            validate_kube_context_name("context\x00evil")

    def test_rejects_path_traversal(self) -> None:
        """Path traversal patterns are rejected."""
        with pytest.raises(SecurityError, match="path traversal"):
            validate_kube_context_name("../etc")

    def test_rejects_forward_slash(self) -> None:
        """Forward slash is rejected."""
        with pytest.raises(SecurityError, match="path traversal"):
            validate_kube_context_name("foo/bar")

    def test_rejects_backslash(self) -> None:
        """Backslash is rejected."""
        with pytest.raises(SecurityError, match="path traversal"):
            validate_kube_context_name("foo\\bar")

    def test_rejects_shell_metachar_semicolon(self) -> None:
        """Semicolon shell metachar is rejected."""
        with pytest.raises(SecurityError, match="shell metacharacter"):
            validate_kube_context_name("context;evil")

    def test_rejects_shell_metachar_ampersand(self) -> None:
        """Ampersand shell metachar is rejected."""
        with pytest.raises(SecurityError, match="shell metacharacter"):
            validate_kube_context_name("context&evil")

    def test_rejects_shell_metachar_pipe(self) -> None:
        """Pipe shell metachar is rejected."""
        with pytest.raises(SecurityError, match="shell metacharacter"):
            validate_kube_context_name("context|evil")

    def test_rejects_shell_metachar_dollar(self) -> None:
        """Dollar sign shell metachar is rejected."""
        with pytest.raises(SecurityError, match="shell metacharacter"):
            validate_kube_context_name("$context")

    def test_rejects_shell_metachar_backtick(self) -> None:
        """Backtick shell metachar is rejected."""
        with pytest.raises(SecurityError, match="shell metacharacter"):
            validate_kube_context_name("`evil`")

    def test_rejects_shell_metachar_newline(self) -> None:
        """Newline shell metachar is rejected."""
        # Note: newline is in the shell metachar set but may match path traversal first
        with pytest.raises(SecurityError):
            validate_kube_context_name("context\n")

    def test_rejects_too_long_context(self) -> None:
        """Context exceeding 500 chars is rejected."""
        long_context = "a" * 501
        with pytest.raises(SecurityError, match="exceeds maximum length"):
            validate_kube_context_name(long_context)

    def test_valid_max_length_context(self) -> None:
        """Context at max length (500 chars) is accepted."""
        context = "a" * 500
        assert validate_kube_context_name(context) == context


class TestValidateKubernetesNamespace:
    """Tests for validate_kubernetes_namespace function."""

    def test_valid_default_namespace(self) -> None:
        """Valid default namespace is accepted."""
        assert validate_kubernetes_namespace("default") == "default"

    def test_valid_kube_system_namespace(self) -> None:
        """Valid kube-system namespace is accepted."""
        assert validate_kubernetes_namespace("kube-system") == "kube-system"

    def test_valid_app_namespace(self) -> None:
        """Valid app namespace with hyphens is accepted."""
        assert validate_kubernetes_namespace("my-app-v1") == "my-app-v1"

    def test_valid_namespace_with_numbers(self) -> None:
        """Namespace with numbers is accepted."""
        assert validate_kubernetes_namespace("app123-namespace456") == "app123-namespace456"

    def test_rejects_empty_string(self) -> None:
        """Empty string is rejected."""
        with pytest.raises(SecurityError, match="cannot be empty"):
            validate_kubernetes_namespace("")

    def test_rejects_uppercase(self) -> None:
        """Uppercase characters are rejected (must be lowercase)."""
        with pytest.raises(SecurityError, match="DNS label pattern"):
            validate_kubernetes_namespace("UPPER")

    def test_rejects_uppercase_mixed(self) -> None:
        """Mixed case is rejected."""
        with pytest.raises(SecurityError, match="DNS label pattern"):
            validate_kubernetes_namespace("MyNamespace")

    def test_rejects_starts_with_hyphen(self) -> None:
        """Namespace starting with hyphen is rejected."""
        with pytest.raises(SecurityError, match="DNS label pattern"):
            validate_kubernetes_namespace("-invalid")

    def test_rejects_ends_with_hyphen(self) -> None:
        """Namespace ending with hyphen is rejected."""
        with pytest.raises(SecurityError, match="DNS label pattern"):
            validate_kubernetes_namespace("invalid-")

    def test_rejects_whitespace(self) -> None:
        """Whitespace in namespace is rejected."""
        # Note: whitespace is caught by shell metachar check before DNS pattern
        with pytest.raises(SecurityError):
            validate_kubernetes_namespace("my namespace")

    def test_rejects_null_byte(self) -> None:
        """Null byte is rejected."""
        with pytest.raises(SecurityError, match="null byte"):
            validate_kubernetes_namespace("ns\x00evil")

    def test_rejects_path_traversal(self) -> None:
        """Path traversal is rejected."""
        with pytest.raises(SecurityError, match="path traversal"):
            validate_kubernetes_namespace("../etc")

    def test_rejects_shell_metachar(self) -> None:
        """Shell metacharacters are rejected."""
        with pytest.raises(SecurityError, match="shell metacharacter"):
            validate_kubernetes_namespace("ns;rm")

    def test_rejects_too_long_namespace(self) -> None:
        """Namespace exceeding 63 chars is rejected."""
        long_ns = "a" * 64
        with pytest.raises(SecurityError, match="exceeds maximum length"):
            validate_kubernetes_namespace(long_ns)

    def test_valid_max_length_namespace(self) -> None:
        """Namespace at max length (63 chars) is accepted."""
        ns = "a" * 63
        assert validate_kubernetes_namespace(ns) == ns

    def test_rejects_special_characters(self) -> None:
        """Special characters are rejected."""
        with pytest.raises(SecurityError, match="DNS label pattern"):
            validate_kubernetes_namespace("ns@production")

    def test_rejects_underscore(self) -> None:
        """Underscores are rejected (not valid in DNS label)."""
        with pytest.raises(SecurityError, match="DNS label pattern"):
            validate_kubernetes_namespace("my_namespace")


class TestValidateKubernetesResourceName:
    """Tests for validate_kubernetes_resource_name function."""

    def test_valid_pod_name(self) -> None:
        """Valid pod name is accepted."""
        assert validate_kubernetes_resource_name("nginx-pod") == "nginx-pod"

    def test_valid_deployment_name(self) -> None:
        """Valid deployment name is accepted."""
        assert validate_kubernetes_resource_name("my-deployment-v1") == "my-deployment-v1"

    def test_valid_service_name(self) -> None:
        """Valid service name is accepted."""
        assert validate_kubernetes_resource_name("my-service") == "my-service"

    def test_valid_service_with_dots(self) -> None:
        """Valid service name with dots (FQDN) is accepted."""
        assert validate_kubernetes_resource_name("my-service.default.svc") == "my-service.default.svc"

    def test_valid_name_with_numbers(self) -> None:
        """Resource name with numbers is accepted."""
        assert validate_kubernetes_resource_name("app123-deployment456") == "app123-deployment456"

    def test_valid_short_name(self) -> None:
        """Valid short resource name is accepted."""
        assert validate_kubernetes_resource_name("a") == "a"

    def test_rejects_empty_string(self) -> None:
        """Empty string is rejected."""
        with pytest.raises(SecurityError, match="cannot be empty"):
            validate_kubernetes_resource_name("")

    def test_rejects_uppercase(self) -> None:
        """Uppercase characters are rejected (DNS name must be lowercase)."""
        with pytest.raises(SecurityError, match="DNS name pattern"):
            validate_kubernetes_resource_name("Pod_Name")

    def test_rejects_uppercase_only(self) -> None:
        """Uppercase-only resource names are rejected (must be lowercase)."""
        with pytest.raises(SecurityError, match="DNS name pattern"):
            validate_kubernetes_resource_name("MyDeployment")

    def test_rejects_starts_with_hyphen(self) -> None:
        """Resource starting with hyphen is rejected."""
        with pytest.raises(SecurityError, match="DNS name pattern"):
            validate_kubernetes_resource_name("-invalid")

    def test_rejects_ends_with_hyphen(self) -> None:
        """Resource ending with hyphen is rejected."""
        with pytest.raises(SecurityError, match="DNS name pattern"):
            validate_kubernetes_resource_name("invalid-")

    def test_rejects_whitespace(self) -> None:
        """Whitespace in resource name is rejected."""
        # Note: whitespace is caught by shell metachar check
        with pytest.raises(SecurityError):
            validate_kubernetes_resource_name("my resource")

    def test_rejects_null_byte(self) -> None:
        """Null byte is rejected."""
        with pytest.raises(SecurityError, match="null byte"):
            validate_kubernetes_resource_name("name\x00evil")

    def test_rejects_path_traversal(self) -> None:
        """Path traversal is rejected."""
        with pytest.raises(SecurityError, match="path traversal"):
            validate_kubernetes_resource_name("../etc")

    def test_rejects_shell_metachar(self) -> None:
        """Shell metacharacters are rejected."""
        with pytest.raises(SecurityError, match="shell metacharacter"):
            validate_kubernetes_resource_name("name;rm")

    def test_rejects_too_long_resource(self) -> None:
        """Resource exceeding 253 chars is rejected."""
        long_name = "a" * 254
        with pytest.raises(SecurityError, match="exceeds maximum length"):
            validate_kubernetes_resource_name(long_name)

    def test_valid_max_length_resource(self) -> None:
        """Resource at max length (253 chars) is accepted."""
        name = "a" * 253
        assert validate_kubernetes_resource_name(name) == name

    def test_rejects_underscore(self) -> None:
        """Underscores are rejected (not valid in DNS name)."""
        with pytest.raises(SecurityError, match="DNS name pattern"):
            validate_kubernetes_resource_name("my_resource")

    def test_rejects_special_characters(self) -> None:
        """Special characters are rejected."""
        with pytest.raises(SecurityError, match="DNS name pattern"):
            validate_kubernetes_resource_name("name@prod")

    def test_rejects_consecutive_dots(self) -> None:
        """Consecutive dots are rejected."""
        # Consecutive dots may be caught by shell metachar check or DNS pattern
        with pytest.raises(SecurityError):
            validate_kubernetes_resource_name("name..other")


class TestInjectionAttemptScenarios:
    """Tests for specific injection attempt scenarios."""

    def test_injection_attempt_shell_command_in_context(self) -> None:
        """Shell command injection in context name is blocked."""
        with pytest.raises(SecurityError):
            validate_kube_context_name("context; rm -rf /")

    def test_injection_attempt_command_substitution_in_namespace(self) -> None:
        """Command substitution in namespace is blocked."""
        with pytest.raises(SecurityError):
            validate_kubernetes_namespace("ns`cat /etc/passwd`")

    def test_injection_attempt_variable_expansion_in_resource(self) -> None:
        """Variable expansion in resource name is blocked."""
        with pytest.raises(SecurityError):
            validate_kubernetes_resource_name("$HOME/.kube/config")

    def test_injection_attempt_path_escape_in_namespace(self) -> None:
        """Path escape attempt in namespace is blocked."""
        with pytest.raises(SecurityError, match="path traversal"):
            validate_kubernetes_namespace("../../../etc")

    def test_injection_attempt_newline_in_context(self) -> None:
        """Newline injection in context is blocked."""
        with pytest.raises(SecurityError):
            validate_kube_context_name("context\nwhoami")

    def test_injection_attempt_null_terminated_in_resource(self) -> None:
        """Null-terminated string injection is blocked."""
        with pytest.raises(SecurityError, match="null byte"):
            validate_kubernetes_resource_name("name\x00 && rm -rf /")