"""Regression tests for Alertmanager cross-namespace discovery.

These tests verify that discovery works correctly when:
- kube context namespace is 'default'
- Alertmanager resources are in 'monitoring' namespace

The bug was that discovery was querying namespaced resources without `-A`,
causing Alertmanager resources in non-default namespaces to be missed.

Tests cover:
- CRD discovery finds resources in non-default namespaces
- Prometheus CRD config discovery finds resources in non-default namespaces
- Service heuristic discovery finds resources in non-default namespaces
- Pod heuristic discovery finds resources in non-default namespaces
- Debug logging makes namespace scope explicit
"""

from __future__ import annotations

import json
import logging

import pytest

from k8s_diag_agent.external_analysis.alertmanager_discovery import (
    CRDDiscoveryStrategy,
    PrometheusCRDConfigDiscoveryStrategy,
    ServiceHeuristicDiscoveryStrategy,
    discover_alertmanagers,
)


class TestCRDDiscoveryCrossNamespace:
    """Regression tests for CRD discovery with resources in non-default namespace."""

    def test_crd_discovery_finds_resources_in_monitoring_namespace(self) -> None:
        """Regression: CRD discovery must find Alertmanager CRDs in 'monitoring' namespace.

        When kube context defaults to namespace 'default' but Alertmanager CRDs
        exist in 'monitoring' namespace, discovery must still find them using -A flag.
        """
        strategy = CRDDiscoveryStrategy()

        # Simulate kubectl output with Alertmanager in 'monitoring' namespace
        kubectl_output = {
            "apiVersion": "monitoring.coreos.com/v1",
            "kind": "AlertmanagerList",
            "items": [
                {
                    "metadata": {
                        "name": "main",
                        "namespace": "monitoring",  # NOT 'default'
                    },
                    "spec": {},
                },
            ],
        }

        # Patch subprocess.run to return the mock output
        with pytest.MonkeyPatch.context() as mp:
            result_mock = type(
                "MockResult",
                (),
                {
                    "returncode": 0,
                    "stdout": json.dumps(kubectl_output),
                },
            )()
            mp.setattr("subprocess.run", lambda *args, **kwargs: result_mock)

            result = strategy.discover()

        # Verify discovery found the resource
        assert len(result.sources) == 1
        assert result.sources[0].source_id == "crd:monitoring/main"
        assert result.sources[0].namespace == "monitoring"

    def test_crd_discovery_uses_all_namespaces_flag(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Regression: Verify kubectl command includes -A for all-namespace search."""
        strategy = CRDDiscoveryStrategy()

        kubectl_output = {
            "apiVersion": "monitoring.coreos.com/v1",
            "kind": "AlertmanagerList",
            "items": [],
        }

        captured_calls: list[list[str]] = []

        def mock_run(cmd: list[str], **kwargs: object) -> object:
            captured_calls.append(cmd)
            return type(
                "MockResult",
                (),
                {
                    "returncode": 0,
                    "stdout": json.dumps(kubectl_output),
                },
            )()

        with caplog.at_level(logging.DEBUG):
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr("subprocess.run", mock_run)
                strategy.discover()

        # Verify -A flag was used in the kubectl command
        assert len(captured_calls) == 1
        call_args = captured_calls[0]
        assert "-A" in call_args, f"Expected -A flag in kubectl command, got: {call_args}"

        # Verify command structure
        command_str = " ".join(call_args)
        assert "kubectl" in command_str
        assert "get" in command_str
        assert "alertmanagers" in command_str
        assert "-o" in command_str and "json" in command_str


class TestPrometheusCRDConfigDiscoveryCrossNamespace:
    """Regression tests for Prometheus CRD config discovery with resources in non-default namespace."""

    def test_prometheus_crd_discovery_finds_resources_in_monitoring_namespace(self) -> None:
        """Regression: Prometheus CRD discovery must find resources in 'monitoring' namespace.

        When kube context defaults to namespace 'default' but Prometheus instances
        with Alertmanager configs exist in 'monitoring' namespace, discovery must
        still find them using -A flag.
        """
        strategy = PrometheusCRDConfigDiscoveryStrategy()

        kubectl_output = {
            "apiVersion": "monitoring.coreos.com/v1",
            "kind": "PrometheusList",
            "items": [
                {
                    "metadata": {
                        "name": "k8s",
                        "namespace": "monitoring",  # NOT 'default'
                    },
                    "spec": {
                        "alerting": {
                            "alertmanagers": [
                                {
                                    "name": "main",
                                    "namespace": "monitoring",
                                }
                            ]
                        }
                    },
                }
            ],
        }

        with pytest.MonkeyPatch.context() as mp:
            result_mock = type(
                "MockResult",
                (),
                {
                    "returncode": 0,
                    "stdout": json.dumps(kubectl_output),
                },
            )()
            mp.setattr("subprocess.run", lambda *args, **kwargs: result_mock)

            result = strategy.discover()

        # Verify discovery found the resource
        assert len(result.sources) == 1
        assert result.sources[0].namespace == "monitoring"
        assert result.sources[0].origin.value == "prometheus-crd-config"

    def test_prometheus_crd_discovery_uses_all_namespaces_flag(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Regression: Verify kubectl command includes -A for all-namespace search."""
        strategy = PrometheusCRDConfigDiscoveryStrategy()

        kubectl_output = {
            "apiVersion": "monitoring.coreos.com/v1",
            "kind": "PrometheusList",
            "items": [],
        }

        captured_calls: list[list[str]] = []

        def mock_run(cmd: list[str], **kwargs: object) -> object:
            captured_calls.append(cmd)
            return type(
                "MockResult",
                (),
                {
                    "returncode": 0,
                    "stdout": json.dumps(kubectl_output),
                },
            )()

        with caplog.at_level(logging.DEBUG):
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr("subprocess.run", mock_run)
                strategy.discover()

        assert len(captured_calls) == 1
        call_args = captured_calls[0]
        assert "-A" in call_args, f"Missing -A flag in command: {call_args}"

        command_str = " ".join(call_args)
        assert "kubectl" in command_str
        assert "get" in command_str
        assert "prometheuses" in command_str


class TestServiceHeuristicDiscoveryCrossNamespace:
    """Regression tests for service/pod heuristic discovery with resources in non-default namespace."""

    def test_service_discovery_finds_resources_in_monitoring_namespace(self) -> None:
        """Regression: Service discovery must find services in 'monitoring' namespace.

        When kube context defaults to namespace 'default' but Alertmanager services
        exist in 'monitoring' namespace, discovery must still find them using -A flag.
        """
        strategy = ServiceHeuristicDiscoveryStrategy()

        service_output = {
            "apiVersion": "v1",
            "kind": "ServiceList",
            "items": [
                {
                    "metadata": {
                        "name": "alertmanager-main",
                        "namespace": "monitoring",  # NOT 'default'
                    },
                    "spec": {"ports": [{"port": 9093, "targetPort": 9093}]},
                }
            ],
        }

        pod_output = {"apiVersion": "v1", "kind": "PodList", "items": []}

        call_count = [0]

        def mock_run(cmd: list[str], **kwargs: object) -> object:
            call_count[0] += 1
            if call_count[0] == 1:
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
            result = strategy.discover()

        # Verify discovery found the service
        assert len(result.sources) == 1
        assert result.sources[0].source_id == "service:monitoring/alertmanager-main"
        assert result.sources[0].namespace == "monitoring"

    def test_pod_discovery_finds_resources_in_monitoring_namespace(self) -> None:
        """Regression: Pod discovery must find pods with app=alertmanager label in all namespaces.

        When kube context defaults to namespace 'default' but Alertmanager pods
        exist in 'monitoring' namespace, discovery must still find them using -A flag.
        """
        strategy = ServiceHeuristicDiscoveryStrategy()

        service_output = {"apiVersion": "v1", "kind": "ServiceList", "items": []}

        pod_output = {
            "apiVersion": "v1",
            "kind": "PodList",
            "items": [
                {
                    "metadata": {
                        "name": "alertmanager-main-0",
                        "namespace": "monitoring",  # NOT 'default'
                    },
                    "status": {"podIP": "10.244.0.100"},
                }
            ],
        }

        call_count = [0]

        def mock_run(cmd: list[str], **kwargs: object) -> object:
            call_count[0] += 1
            if call_count[0] == 1:
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
            result = strategy.discover()

        # Verify discovery found the pod
        assert len(result.sources) == 1
        assert result.sources[0].source_id == "pod:monitoring/alertmanager-main-0"
        assert result.sources[0].namespace == "monitoring"
        assert result.sources[0].endpoint == "http://10.244.0.100:9093"

    def test_service_and_pod_discovery_use_all_namespaces_flag(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Regression: Verify both service and pod kubectl commands include -A flag."""
        strategy = ServiceHeuristicDiscoveryStrategy()

        service_output = {"apiVersion": "v1", "kind": "ServiceList", "items": []}
        pod_output = {"apiVersion": "v1", "kind": "PodList", "items": []}

        captured_calls: list[list[str]] = []

        def mock_run(cmd: list[str], **kwargs: object) -> object:
            captured_calls.append(cmd)
            if len(captured_calls) == 1:
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

        with caplog.at_level(logging.DEBUG):
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr("subprocess.run", mock_run)
                strategy.discover()

        assert len(captured_calls) == 2

        # Check service command
        svc_cmd = captured_calls[0]
        svc_cmd_str = " ".join(svc_cmd)
        assert "kubectl" in svc_cmd_str
        assert "get" in svc_cmd_str
        assert "svc" in svc_cmd_str
        assert "-A" in svc_cmd, f"Missing -A in service command: {svc_cmd_str}"

        # Check pod command
        pod_cmd = captured_calls[1]
        pod_cmd_str = " ".join(pod_cmd)
        assert "kubectl" in pod_cmd_str
        assert "get" in pod_cmd_str
        assert "pods" in pod_cmd_str
        assert "-A" in pod_cmd, f"Missing -A in pod command: {pod_cmd_str}"


class TestDebugLoggingCrossNamespace:
    """Regression tests for debug logging that makes namespace scope explicit."""

    def test_crd_discovery_logs_namespace_scope(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Regression: CRD discovery must log that it's searching all namespaces."""
        strategy = CRDDiscoveryStrategy()

        kubectl_output = {
            "apiVersion": "monitoring.coreos.com/v1",
            "kind": "AlertmanagerList",
            "items": [],
        }

        with caplog.at_level(logging.DEBUG):
            with pytest.MonkeyPatch.context() as mp:
                result_mock = type(
                    "MockResult",
                    (),
                    {
                        "returncode": 0,
                        "stdout": json.dumps(kubectl_output),
                    },
                )()
                mp.setattr("subprocess.run", lambda *args, **kwargs: result_mock)
                strategy.discover()

        # Verify debug log mentions all namespaces search
        debug_messages = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
        all_ns_message = any("-A" in msg or "all namespaces" in msg.lower() for msg in debug_messages)
        assert all_ns_message, f"Expected debug log about all-namespaces search, got: {debug_messages}"

    def test_prometheus_crd_discovery_logs_namespace_scope(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Regression: Prometheus CRD discovery must log that it's searching all namespaces."""
        strategy = PrometheusCRDConfigDiscoveryStrategy()

        kubectl_output = {
            "apiVersion": "monitoring.coreos.com/v1",
            "kind": "PrometheusList",
            "items": [],
        }

        with caplog.at_level(logging.DEBUG):
            with pytest.MonkeyPatch.context() as mp:
                result_mock = type(
                    "MockResult",
                    (),
                    {
                        "returncode": 0,
                        "stdout": json.dumps(kubectl_output),
                    },
                )()
                mp.setattr("subprocess.run", lambda *args, **kwargs: result_mock)
                strategy.discover()

        debug_messages = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
        all_ns_message = any("-A" in msg or "all namespaces" in msg.lower() for msg in debug_messages)
        assert all_ns_message, f"Expected debug log about all-namespaces search, got: {debug_messages}"

    def test_service_heuristic_logs_namespace_scope(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Regression: Service heuristic discovery must log that it's searching all namespaces."""
        strategy = ServiceHeuristicDiscoveryStrategy()

        service_output = {"apiVersion": "v1", "kind": "ServiceList", "items": []}
        pod_output = {"apiVersion": "v1", "kind": "PodList", "items": []}

        with caplog.at_level(logging.DEBUG):
            call_count = [0]

            def mock_run(cmd: list[str], **kwargs: object) -> object:
                call_count[0] += 1
                if call_count[0] == 1:
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
                strategy.discover()

        debug_messages = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
        all_ns_message = any("-A" in msg or "all namespaces" in msg.lower() for msg in debug_messages)
        assert all_ns_message, f"Expected debug log about all-namespaces search, got: {debug_messages}"

    def test_discover_alertmanagers_logs_namespace_scope(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Regression: discover_alertmanagers must log namespace scope."""
        kubectl_output = {
            "apiVersion": "monitoring.coreos.com/v1",
            "kind": "AlertmanagerList",
            "items": [],
        }

        call_count = [0]

        def mock_run(cmd: list[str], **kwargs: object) -> object:
            call_count[0] += 1
            return type(
                "MockResult",
                (),
                {
                    "returncode": 0,
                    "stdout": json.dumps(kubectl_output),
                },
            )()

        with caplog.at_level(logging.DEBUG):
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr("subprocess.run", mock_run)
                discover_alertmanagers(context="test-context")

        debug_messages = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
        context_msg = any("test-context" in msg for msg in debug_messages)
        assert context_msg, f"Expected debug log mentioning context, got: {debug_messages}"


class TestOrchestratedDiscoveryCrossNamespace:
    """Integration tests for orchestrated discovery with resources in non-default namespace."""

    def test_discover_alertmanagers_finds_monitoring_namespace_resources(self) -> None:
        """Regression: discover_alertmanagers must find Alertmanager in 'monitoring' namespace.

        End-to-end test: when context defaults to 'default' namespace but
        Alertmanager CRD exists in 'monitoring', orchestrated discovery must find it.
        """
        crd_output = {
            "apiVersion": "monitoring.coreos.com/v1",
            "kind": "AlertmanagerList",
            "items": [
                {
                    "metadata": {
                        "name": "main",
                        "namespace": "monitoring",
                    },
                    "spec": {},
                },
            ],
        }

        prometheus_output = {"apiVersion": "monitoring.coreos.com/v1", "kind": "PrometheusList", "items": []}
        service_output = {"apiVersion": "v1", "kind": "ServiceList", "items": []}
        pod_output = {"apiVersion": "v1", "kind": "PodList", "items": []}

        call_count = [0]

        def mock_run(cmd: list[str], **kwargs: object) -> object:
            call_count[0] += 1
            if call_count[0] == 1:
                return type(
                    "MockResult",
                    (),
                    {
                        "returncode": 0,
                        "stdout": json.dumps(crd_output),
                    },
                )()
            elif call_count[0] == 2:
                return type(
                    "MockResult",
                    (),
                    {
                        "returncode": 0,
                        "stdout": json.dumps(prometheus_output),
                    },
                )()
            elif call_count[0] == 3:
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
            result = discover_alertmanagers(context="prod-cluster")

        # Verify the CRD source was found
        assert len(result.sources) >= 1
        monitoring_sources = [s for s in result.sources.values() if s.namespace == "monitoring"]
        assert len(monitoring_sources) >= 1
        assert monitoring_sources[0].source_id == "crd:monitoring/main"

        # Verify context was recorded
        assert result.cluster_context == "prod-cluster"
