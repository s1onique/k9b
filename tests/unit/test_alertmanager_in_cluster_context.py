"""Tests for Alertmanager discovery in-cluster context handling.

These tests verify that discovery strategies correctly handle the "in-cluster" context:
- In-cluster mode (context == "in-cluster") must NOT pass --context to kubectl
- Kubeconfig mode (context is a non-in-cluster name) should use --context

This ensures Alertmanager discovery works in both:
1. Pod ServiceAccount auth (in-cluster mode) - kubectl uses mounted token automatically
2. kubeconfig contexts - kubectl uses explicit context from kubeconfig
"""

from __future__ import annotations

import json

import pytest

from k8s_diag_agent.external_analysis.alertmanager_discovery import (
    _IN_CLUSTER_CONTEXT,
    CRDDiscoveryStrategy,
    PrometheusCRDConfigDiscoveryStrategy,
    ServiceHeuristicDiscoveryStrategy,
    _kubectl_context_args,
    _should_add_context_flag,
)


class TestShouldAddContextFlag:
    """Tests for the _should_add_context_flag helper function."""

    def test_returns_false_for_none_context(self) -> None:
        """When context is None, should not add --context flag."""
        assert _should_add_context_flag(None) is False

    def test_returns_false_for_in_cluster_context(self) -> None:
        """When context is 'in-cluster', should NOT add --context flag."""
        assert _should_add_context_flag(_IN_CLUSTER_CONTEXT) is False
        assert _should_add_context_flag("in-cluster") is False

    def test_returns_true_for_named_context(self) -> None:
        """When context is a named kubeconfig context, should add --context flag."""
        assert _should_add_context_flag("my-cluster") is True
        assert _should_add_context_flag("prod") is True
        assert _should_add_context_flag("minikube") is True

    def test_returns_true_for_context_with_hyphen(self) -> None:
        """Named contexts with hyphens should still get --context flag."""
        assert _should_add_context_flag("gke-project-123") is True

    def test_constant_matches_expected_value(self) -> None:
        """Verify the in-cluster context constant matches expected value."""
        assert _IN_CLUSTER_CONTEXT == "in-cluster"


class TestCRDDiscoveryInClusterContext:
    """Tests for CRD discovery with in-cluster context."""

    def test_crd_discovery_skips_context_flag_for_in_cluster(self) -> None:
        """CRD discovery must NOT pass --context when context is 'in-cluster'."""
        strategy = CRDDiscoveryStrategy()

        kubectl_output = {
            "apiVersion": "monitoring.coreos.com/v1",
            "kind": "AlertmanagerList",
            "items": [],
        }

        captured_commands: list[list[str]] = []

        def mock_run(cmd: list[str], **kwargs: object) -> object:
            captured_commands.append(cmd)
            return type(
                "MockResult",
                (),
                {
                    "returncode": 0,
                    "stdout": json.dumps(kubectl_output),
                },
            )()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("subprocess.run", mock_run)
            strategy.discover(context=_IN_CLUSTER_CONTEXT)

        assert len(captured_commands) == 1
        cmd = captured_commands[0]
        # Verify no --context in the command
        assert "--context" not in cmd, f"Expected no --context in command, got: {cmd}"
        # Verify it's still a valid kubectl command
        assert "kubectl" in cmd
        assert "get" in cmd
        assert "alertmanagers" in cmd

    def test_crd_discovery_uses_context_flag_for_named_context(self) -> None:
        """CRD discovery must use --context when context is a named kubeconfig context."""
        strategy = CRDDiscoveryStrategy()

        kubectl_output = {
            "apiVersion": "monitoring.coreos.com/v1",
            "kind": "AlertmanagerList",
            "items": [],
        }

        captured_commands: list[list[str]] = []

        def mock_run(cmd: list[str], **kwargs: object) -> object:
            captured_commands.append(cmd)
            return type(
                "MockResult",
                (),
                {
                    "returncode": 0,
                    "stdout": json.dumps(kubectl_output),
                },
            )()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("subprocess.run", mock_run)
            strategy.discover(context="my-cluster")

        assert len(captured_commands) == 1
        cmd = captured_commands[0]
        # Verify --context is present with the correct context name
        assert "--context" in cmd, f"Expected --context in command, got: {cmd}"
        context_idx = cmd.index("--context")
        assert cmd[context_idx + 1] == "my-cluster"


class TestPrometheusCRDConfigDiscoveryInClusterContext:
    """Tests for Prometheus CRD config discovery with in-cluster context."""

    def test_prometheus_discovery_skips_context_flag_for_in_cluster(self) -> None:
        """Prometheus CRD discovery must NOT pass --context when context is 'in-cluster'."""
        strategy = PrometheusCRDConfigDiscoveryStrategy()

        kubectl_output = {
            "apiVersion": "monitoring.coreos.com/v1",
            "kind": "PrometheusList",
            "items": [],
        }

        captured_commands: list[list[str]] = []

        def mock_run(cmd: list[str], **kwargs: object) -> object:
            captured_commands.append(cmd)
            return type(
                "MockResult",
                (),
                {
                    "returncode": 0,
                    "stdout": json.dumps(kubectl_output),
                },
            )()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("subprocess.run", mock_run)
            strategy.discover(context=_IN_CLUSTER_CONTEXT)

        assert len(captured_commands) == 1
        cmd = captured_commands[0]
        assert "--context" not in cmd, f"Expected no --context in command, got: {cmd}"

    def test_prometheus_discovery_uses_context_flag_for_named_context(self) -> None:
        """Prometheus CRD discovery must use --context when context is a named context."""
        strategy = PrometheusCRDConfigDiscoveryStrategy()

        kubectl_output = {
            "apiVersion": "monitoring.coreos.com/v1",
            "kind": "PrometheusList",
            "items": [],
        }

        captured_commands: list[list[str]] = []

        def mock_run(cmd: list[str], **kwargs: object) -> object:
            captured_commands.append(cmd)
            return type(
                "MockResult",
                (),
                {
                    "returncode": 0,
                    "stdout": json.dumps(kubectl_output),
                },
            )()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("subprocess.run", mock_run)
            strategy.discover(context="prod-cluster")

        assert len(captured_commands) == 1
        cmd = captured_commands[0]
        assert "--context" in cmd, f"Expected --context in command, got: {cmd}"
        context_idx = cmd.index("--context")
        assert cmd[context_idx + 1] == "prod-cluster"


class TestServiceHeuristicDiscoveryInClusterContext:
    """Tests for Service heuristic discovery with in-cluster context."""

    def test_service_discovery_skips_context_flag_for_in_cluster(self) -> None:
        """Service heuristic discovery must NOT pass --context when context is 'in-cluster'."""
        strategy = ServiceHeuristicDiscoveryStrategy()

        service_output = {"apiVersion": "v1", "kind": "ServiceList", "items": []}
        pod_output = {"apiVersion": "v1", "kind": "PodList", "items": []}

        captured_commands: list[list[str]] = []

        def mock_run(cmd: list[str], **kwargs: object) -> object:
            captured_commands.append(cmd)
            if len(captured_commands) == 1:
                return type(
                    "MockResult",
                    (),
                    {
                        "returncode": 0,
                        "stdout": json.dumps(service_output),
                    },
                )()
            else:
                return type(
                    "MockResult",
                    (),
                    {
                        "returncode": 0,
                        "stdout": json.dumps(pod_output),
                    },
                )()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("subprocess.run", mock_run)
            strategy.discover(context=_IN_CLUSTER_CONTEXT)

        # Should make 2 calls: get svc and get pods
        assert len(captured_commands) == 2
        for cmd in captured_commands:
            assert "--context" not in cmd, f"Expected no --context in service command, got: {cmd}"

    def test_service_discovery_uses_context_flag_for_named_context(self) -> None:
        """Service heuristic discovery must use --context when context is a named context."""
        strategy = ServiceHeuristicDiscoveryStrategy()

        service_output = {"apiVersion": "v1", "kind": "ServiceList", "items": []}
        pod_output = {"apiVersion": "v1", "kind": "PodList", "items": []}

        captured_commands: list[list[str]] = []

        def mock_run(cmd: list[str], **kwargs: object) -> object:
            captured_commands.append(cmd)
            if len(captured_commands) == 1:
                return type(
                    "MockResult",
                    (),
                    {
                        "returncode": 0,
                        "stdout": json.dumps(service_output),
                    },
                )()
            else:
                return type(
                    "MockResult",
                    (),
                    {
                        "returncode": 0,
                        "stdout": json.dumps(pod_output),
                    },
                )()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("subprocess.run", mock_run)
            strategy.discover(context="staging")

        # Should make 2 calls: get svc and get pods
        assert len(captured_commands) == 2
        for cmd in captured_commands:
            assert "--context" in cmd, f"Expected --context in service command, got: {cmd}"
            context_idx = cmd.index("--context")
            assert cmd[context_idx + 1] == "staging"


class TestDiscoveryWithNoneContext:
    """Tests for all discovery strategies with None context."""

    def test_crd_discovery_handles_none_context(self) -> None:
        """CRD discovery must handle None context (no --context flag)."""
        strategy = CRDDiscoveryStrategy()

        kubectl_output = {
            "apiVersion": "monitoring.coreos.com/v1",
            "kind": "AlertmanagerList",
            "items": [],
        }

        captured_commands: list[list[str]] = []

        def mock_run(cmd: list[str], **kwargs: object) -> object:
            captured_commands.append(cmd)
            return type(
                "MockResult",
                (),
                {
                    "returncode": 0,
                    "stdout": json.dumps(kubectl_output),
                },
            )()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("subprocess.run", mock_run)
            strategy.discover(context=None)

        assert len(captured_commands) == 1
        cmd = captured_commands[0]
        assert "--context" not in cmd, f"Expected no --context for None context, got: {cmd}"

    def test_service_discovery_handles_none_context(self) -> None:
        """Service heuristic discovery must handle None context (no --context flag)."""
        strategy = ServiceHeuristicDiscoveryStrategy()

        service_output = {"apiVersion": "v1", "kind": "ServiceList", "items": []}
        pod_output = {"apiVersion": "v1", "kind": "PodList", "items": []}

        captured_commands: list[list[str]] = []

        def mock_run(cmd: list[str], **kwargs: object) -> object:
            captured_commands.append(cmd)
            if len(captured_commands) == 1:
                return type(
                    "MockResult",
                    (),
                    {
                        "returncode": 0,
                        "stdout": json.dumps(service_output),
                    },
                )()
            else:
                return type(
                    "MockResult",
                    (),
                    {
                        "returncode": 0,
                        "stdout": json.dumps(pod_output),
                    },
                )()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("subprocess.run", mock_run)
            strategy.discover(context=None)

        for cmd in captured_commands:
            assert "--context" not in cmd, f"Expected no --context for None context, got: {cmd}"


class TestKubectlContextArgs:
    """Tests for the _kubectl_context_args helper function."""

    def test_returns_empty_for_none_context(self) -> None:
        """When context is None, should return empty list."""
        assert _kubectl_context_args(None) == []

    def test_returns_empty_for_in_cluster_context(self) -> None:
        """When context is 'in-cluster', should return empty list."""
        assert _kubectl_context_args(_IN_CLUSTER_CONTEXT) == []
        assert _kubectl_context_args("in-cluster") == []

    def test_returns_context_args_for_named_context(self) -> None:
        """When context is a named kubeconfig context, should return --context args."""
        assert _kubectl_context_args("my-cluster") == ["--context", "my-cluster"]
        assert _kubectl_context_args("prod") == ["--context", "prod"]
        assert _kubectl_context_args("minikube") == ["--context", "minikube"]

    def test_returns_context_args_for_context_with_hyphen(self) -> None:
        """Named contexts with hyphens should return correct --context args."""
        assert _kubectl_context_args("gke-project-123") == ["--context", "gke-project-123"]

    def test_return_type_is_list(self) -> None:
        """Verify the return type is list[str] for mypy compatibility."""
        result = _kubectl_context_args("test-context")
        # This test ensures the helper returns a list, not a tuple or other iterable
        assert isinstance(result, list)
        assert result == ["--context", "test-context"]
