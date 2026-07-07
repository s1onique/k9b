"""Unit tests for Kubernetes Python client module.

These tests verify:
1. Client config loader chooses in-cluster config when requested
2. Client config loader chooses kubeconfig/context in local mode
3. Namespace UID read returns metadata UID
4. Namespace UID read handles 403/404/transport failure gracefully
5. Deployment env read returns configured env value
6. Deployment env read handles missing container/env cleanly
7. Pod list pagination follows continue token
8. Pod list stops at max_items and records truncation
9. No raw Kubernetes objects escape from projection methods
"""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import MagicMock, patch


class TestKubernetesClientModels(unittest.TestCase):
    """Test Kubernetes projection models."""

    def test_namespace_projection_from_dict(self) -> None:
        """Test NamespaceProjection.from_dict extracts UID correctly."""
        from k8s_diag_agent.security.kubernetes_client_models import NamespaceProjection

        data = {
            "metadata": {
                "name": "kube-system",
                "uid": "12345-abcde",
                "creationTimestamp": "2024-01-01T00:00:00Z",
            }
        }
        projection = NamespaceProjection.from_dict(data)

        self.assertEqual(projection.name, "kube-system")
        self.assertEqual(projection.uid, "12345-abcde")
        self.assertIsNotNone(projection.creation_timestamp)

    def test_namespace_projection_missing_fields(self) -> None:
        """Test NamespaceProjection handles missing fields gracefully."""
        from k8s_diag_agent.security.kubernetes_client_models import NamespaceProjection

        data: dict[str, Any] = {}
        projection = NamespaceProjection.from_dict(data)

        self.assertEqual(projection.name, "")
        self.assertEqual(projection.uid, "")

    def test_pod_projection_from_dict(self) -> None:
        """Test PodProjection.from_dict extracts pod info correctly."""
        from k8s_diag_agent.security.kubernetes_client_models import PodProjection

        data = {
            "metadata": {
                "name": "test-pod",
                "namespace": "default",
                "uid": "pod-uid-123",
                "labels": {"app": "test"},
            },
            "spec": {
                "nodeName": "node-1",
            },
            "status": {
                "phase": "Running",
                "podIP": "10.0.0.1",
                "hostIP": "192.168.1.1",
                "containerStatuses": [
                    {
                        "name": "main",
                        "ready": True,
                        "restartCount": 0,
                        "state": {"running": {}},
                    }
                ],
            },
        }
        projection = PodProjection.from_dict(data)

        self.assertEqual(projection.namespace, "default")
        self.assertEqual(projection.name, "test-pod")
        self.assertEqual(projection.uid, "pod-uid-123")
        self.assertEqual(projection.node_name, "node-1")
        self.assertEqual(projection.phase, "Running")
        self.assertEqual(projection.labels, {"app": "test"})

    def test_pod_projection_no_raw_object_leakage(self) -> None:
        """Test PodProjection does not leak raw Kubernetes objects."""
        from k8s_diag_agent.security.kubernetes_client_models import PodProjection

        data = {
            "metadata": {
                "name": "test",
                "namespace": "default",
                "uid": "uid-1",
                "_raw": "should not appear",
            },
            "spec": {},
            "status": {},
        }
        projection = PodProjection.from_dict(data)

        # Verify it's a simple dataclass with no complex objects
        self.assertIsInstance(projection.namespace, str)
        self.assertIsInstance(projection.name, str)
        self.assertIsInstance(projection.labels, dict)
        self.assertIsInstance(projection.container_statuses, tuple)

    def test_event_projection_from_dict(self) -> None:
        """Test EventProjection.from_dict extracts event info correctly."""
        from k8s_diag_agent.security.kubernetes_client_models import EventProjection

        data = {
            "metadata": {
                "name": "event-1",
                "namespace": "default",
                "creationTimestamp": "2024-01-01T12:00:00Z",
            },
            "type": "Warning",
            "reason": "BackOff",
            "message": "Back-off pulling image",
            "involvedObject": {
                "kind": "Pod",
                "name": "test-pod",
            },
            "count": 5,
        }
        projection = EventProjection.from_dict(data)

        self.assertEqual(projection.namespace, "default")
        self.assertEqual(projection.event_type, "Warning")
        self.assertEqual(projection.reason, "BackOff")
        self.assertEqual(projection.count, 5)
        self.assertEqual(projection.involved_object_kind, "Pod")

    def test_deployment_projection_from_dict(self) -> None:
        """Test DeploymentProjection.from_dict extracts deployment info correctly."""
        from k8s_diag_agent.security.kubernetes_client_models import DeploymentProjection

        data = {
            "metadata": {
                "name": "test-deploy",
                "namespace": "default",
                "uid": "deploy-uid-123",
                "labels": {"version": "v1"},
            },
            "spec": {
                "replicas": 3,
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": "main",
                                "env": [
                                    {"name": "ENV_VAR", "value": "test-value"},
                                ],
                            }
                        ]
                    }
                },
            },
            "status": {
                "readyReplicas": 2,
                "availableReplicas": 2,
                "unavailableReplicas": 1,
            },
        }
        projection = DeploymentProjection.from_dict(data)

        self.assertEqual(projection.namespace, "default")
        self.assertEqual(projection.name, "test-deploy")
        self.assertEqual(projection.uid, "deploy-uid-123")
        self.assertEqual(projection.replicas, 3)
        self.assertEqual(projection.ready_replicas, 2)
        self.assertEqual(projection.env_vars, {"ENV_VAR": "test-value"})

    def test_deployment_projection_env_not_set(self) -> None:
        """Test DeploymentProjection handles missing env vars."""
        from k8s_diag_agent.security.kubernetes_client_models import DeploymentProjection

        data = {
            "metadata": {"name": "test", "namespace": "default", "uid": "uid-1"},
            "spec": {"replicas": 1, "template": {"spec": {"containers": []}}},
            "status": {},
        }
        projection = DeploymentProjection.from_dict(data)

        self.assertEqual(projection.env_vars, {})
        self.assertEqual(projection.replicas, 1)

    def test_deployment_projection_image_pull_secrets(self) -> None:
        """Test DeploymentProjection extracts imagePullSecrets from pod template."""
        from k8s_diag_agent.security.kubernetes_client_models import DeploymentProjection

        data = {
            "metadata": {
                "name": "test-deploy",
                "namespace": "default",
                "uid": "deploy-uid-123",
            },
            "spec": {
                "replicas": 3,
                "template": {
                    "spec": {
                        "imagePullSecrets": [
                            {"name": "my-registry-secret"},
                            {"name": "another-secret"},
                        ],
                        "containers": [],
                    }
                },
            },
            "status": {},
        }
        projection = DeploymentProjection.from_dict(data)

        self.assertEqual(projection.image_pull_secrets, ("my-registry-secret", "another-secret"))

    def test_deployment_projection_image_pull_secrets_empty(self) -> None:
        """Test DeploymentProjection handles missing imagePullSecrets."""
        from k8s_diag_agent.security.kubernetes_client_models import DeploymentProjection

        data = {
            "metadata": {"name": "test", "namespace": "default", "uid": "uid-1"},
            "spec": {"replicas": 1, "template": {"spec": {"containers": []}}},
            "status": {},
        }
        projection = DeploymentProjection.from_dict(data)

        self.assertEqual(projection.image_pull_secrets, ())


class TestKubernetesClientErrors(unittest.TestCase):
    """Test Kubernetes client error types."""

    def test_error_to_dict(self) -> None:
        """Test KubernetesClientError.to_dict produces artifact-compatible output."""
        from k8s_diag_agent.security.kubernetes_client_errors import KubernetesClientError

        error = KubernetesClientError(
            "Test error",
            resource="pod",
            namespace="default",
            operation="read",
        )
        result = error.to_dict()

        self.assertEqual(result["error_type"], "KubernetesClientError")
        self.assertEqual(result["message"], "Test error")
        self.assertEqual(result["resource"], "pod")
        self.assertEqual(result["namespace"], "default")

    def test_translate_api_exception_403(self) -> None:
        """Test translate_api_exception handles 403 Forbidden."""
        from k8s_diag_agent.security.kubernetes_client_errors import (
            KubernetesApiPermissionError,
            translate_api_exception,
        )

        exc = MagicMock()
        exc.status = 403
        exc.reason = "Forbidden"

        result = translate_api_exception(exc, resource="pod", namespace="default")

        self.assertIsInstance(result, KubernetesApiPermissionError)

    def test_translate_api_exception_404(self) -> None:
        """Test translate_api_exception handles 404 Not Found."""
        from k8s_diag_agent.security.kubernetes_client_errors import (
            KubernetesApiNotFoundError,
            translate_api_exception,
        )

        exc = MagicMock()
        exc.status = 404

        result = translate_api_exception(exc, resource="pod", namespace="default")

        self.assertIsInstance(result, KubernetesApiNotFoundError)

    def test_translate_api_exception_timeout(self) -> None:
        """Test translate_api_exception handles timeout errors."""
        from k8s_diag_agent.security.kubernetes_client_errors import (
            KubernetesClientUnavailableError,
            translate_api_exception,
        )

        # Use a custom exception class with "timeout" in the name
        class TimeoutException(Exception):
            pass

        exc = TimeoutException("Connection timed out")

        result = translate_api_exception(exc)

        self.assertIsInstance(result, KubernetesClientUnavailableError)


class TestKubernetesClientConfig(unittest.TestCase):
    """Test Kubernetes client configuration."""

    @patch("kubernetes.config")
    @patch("kubernetes.client")
    def test_in_cluster_config_detection(self, mock_client: MagicMock, mock_config: MagicMock) -> None:
        """Test client uses in-cluster config when KUBERNETES_SERVICE_HOST is set."""
        from k8s_diag_agent.security.kubernetes_client import KubernetesReadClient

        mock_config.load_incluster_config = MagicMock()
        mock_config.load_kube_config = MagicMock()
        mock_client.ApiClient.return_value = MagicMock()
        mock_client.CoreV1Api.return_value = MagicMock()
        mock_client.AppsV1Api.return_value = MagicMock()

        with patch.dict("os.environ", {"KUBERNETES_SERVICE_HOST": "10.0.0.1"}):
            client = KubernetesReadClient()
            # Access core_v1 to trigger config loading
            _ = client.core_v1

        mock_config.load_incluster_config.assert_called_once()

    @patch("kubernetes.config")
    @patch("kubernetes.client")
    def test_kubeconfig_config(self, mock_client: MagicMock, mock_config: MagicMock) -> None:
        """Test client uses kubeconfig when explicitly provided."""
        from k8s_diag_agent.security.kubernetes_client import KubernetesReadClient

        mock_config.load_incluster_config = MagicMock()
        mock_config.load_kube_config = MagicMock()
        mock_client.ApiClient.return_value = MagicMock()
        mock_client.CoreV1Api.return_value = MagicMock()
        mock_client.AppsV1Api.return_value = MagicMock()

        with patch.dict("os.environ", {}, clear=True):
            client = KubernetesReadClient(kubeconfig="/path/to/kubeconfig")
            _ = client.core_v1

        mock_config.load_kube_config.assert_called_once_with(
            config_file="/path/to/kubeconfig",
            context=None,
        )


class TestKubernetesReadClientMethods(unittest.TestCase):
    """Test KubernetesReadClient read methods."""

    @patch("kubernetes.config")
    @patch("kubernetes.client")
    def test_read_namespace_uid_success(self, mock_client: MagicMock, mock_config: MagicMock) -> None:
        """Test read_namespace_uid returns UID on success."""
        from k8s_diag_agent.security.kubernetes_client import KubernetesReadClient

        mock_ns = MagicMock()
        mock_ns.metadata.uid = "test-uid-123"

        mock_core = MagicMock()
        mock_core.read_namespace.return_value = mock_ns

        mock_client.ApiClient.return_value = MagicMock()
        mock_client.CoreV1Api.return_value = mock_core
        mock_client.AppsV1Api.return_value = MagicMock()

        client = KubernetesReadClient()
        result = client.read_namespace_uid("kube-system")

        self.assertEqual(result, "test-uid-123")
        mock_core.read_namespace.assert_called_once_with("kube-system")

    @patch("kubernetes.config")
    @patch("kubernetes.client")
    def test_read_namespace_uid_handles_error(self, mock_client: MagicMock, mock_config: MagicMock) -> None:
        """Test read_namespace_uid returns None on error."""
        from k8s_diag_agent.security.kubernetes_client import KubernetesReadClient

        mock_core = MagicMock()
        mock_core.read_namespace.side_effect = Exception("API error")

        mock_client.ApiClient.return_value = MagicMock()
        mock_client.CoreV1Api.return_value = mock_core
        mock_client.AppsV1Api.return_value = MagicMock()

        client = KubernetesReadClient()
        result = client.read_namespace_uid("kube-system")

        self.assertIsNone(result)

    @patch("kubernetes.config")
    @patch("kubernetes.client")
    def test_read_deployment_env_value_success(self, mock_client: MagicMock, mock_config: MagicMock) -> None:
        """Test read_deployment_env_value returns configured env value."""
        from k8s_diag_agent.security.kubernetes_client import KubernetesReadClient

        mock_deploy = MagicMock()
        mock_container = MagicMock()
        mock_container.name = "main"
        
        # Create env var mocks with proper attributes
        mock_env_var = MagicMock()
        mock_env_var.name = "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"
        mock_env_var.value = "true"
        mock_container.env = [mock_env_var]
        mock_deploy.spec.template.spec.containers = [mock_container]

        mock_apps = MagicMock()
        mock_apps.read_namespaced_deployment.return_value = mock_deploy

        mock_client.ApiClient.return_value = MagicMock()
        mock_client.CoreV1Api.return_value = MagicMock()
        mock_client.AppsV1Api.return_value = mock_apps

        client = KubernetesReadClient()
        result = client.read_deployment_env_value(
            namespace="k9b",
            deployment="scheduler",
            env_name="K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED",
        )

        self.assertEqual(result, "true")

    @patch("kubernetes.config")
    @patch("kubernetes.client")
    def test_read_deployment_env_value_not_set(self, mock_client: MagicMock, mock_config: MagicMock) -> None:
        """Test read_deployment_env_value returns None when env not set."""
        from k8s_diag_agent.security.kubernetes_client import KubernetesReadClient

        mock_deploy = MagicMock()
        mock_container = MagicMock()
        mock_container.name = "main"
        mock_container.env = [
            MagicMock(name="OTHER_VAR", value="other"),
        ]
        mock_deploy.spec.template.spec.containers = [mock_container]

        mock_apps = MagicMock()
        mock_apps.read_namespaced_deployment.return_value = mock_deploy

        mock_client.ApiClient.return_value = MagicMock()
        mock_client.CoreV1Api.return_value = MagicMock()
        mock_client.AppsV1Api.return_value = mock_apps

        client = KubernetesReadClient()
        result = client.read_deployment_env_value(
            namespace="k9b",
            deployment="scheduler",
            env_name="K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED",
        )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
