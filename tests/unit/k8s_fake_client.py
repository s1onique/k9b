"""Shared fake Kubernetes client for unit tests.

This module provides FakeKubernetesReadClient that can be used to mock the
KubernetesReadClient interface in unit tests.

Usage:
    from tests.unit.k8s_fake_client import FakeKubernetesReadClient

    # Create a fake that returns a specific deployment env value
    fake = FakeKubernetesReadClient.with_deployment_env(
        namespace="k9b",
        deployment="k9b-scheduler",
        env_vars={"K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED": "true"},
    )

    # Patch the client factory at the correct seam
    monkeypatch.setattr(
        "k8s_diag_agent.collect.incident_diagnosis_loop_gate.get_cached_kubernetes_client",
        lambda **kwargs: fake,
    )
    result = is_automatic_diagnosis_loop_enabled(...)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from k8s_diag_agent.security.kubernetes_client_errors import (
    KubernetesApiNotFoundError,
    KubernetesApiPermissionError,
)
from k8s_diag_agent.security.kubernetes_client_models import (
    CrdSummary,
    DeploymentProjection,
    EventProjection,
    NodeSummary,
    PodSummary,
    StatefulSetSummary,
)


@dataclass
class FakeKubernetesReadClient:
    """Fake KubernetesReadClient for unit testing.

    This provides a minimal interface matching KubernetesReadClient for tests
    that need to mock the Kubernetes client boundary.

    Default behavior: returns None/empty for unconfigured reads. Use the factory
    methods or set specific behaviors before use.

    Use factory methods for common scenarios:
    - with_deployment_env(): return specific env var values
    - with_permission_error(): raise KubernetesApiPermissionError
    - with_not_found(): raise KubernetesApiNotFoundError
    - with_namespace_uid(): return specific namespace UIDs
    - with_warning_events(): return specific warning events
    - with_crds(): return specific CRDs
    """

    # Pre-configured behaviors
    _deployment_env_values: dict[str, dict[str, str]] = field(default_factory=dict)
    _namespace_uids: dict[str, str | None] = field(default_factory=dict)
    _permission_error_on: list[tuple[str, str]] = field(default_factory=list)  # (namespace, deployment)
    _not_found_on: list[tuple[str, str]] = field(default_factory=list)  # (namespace, deployment)
    _warning_events: list[EventProjection] = field(default_factory=list)
    _deployments: dict[str, list[DeploymentProjection]] = field(default_factory=dict)  # namespace -> list
    _statefulsets: dict[str, list[StatefulSetSummary]] = field(default_factory=dict)  # namespace -> list
    _pods: dict[str, list[PodSummary]] = field(default_factory=dict)  # namespace -> list
    _nodes: list[NodeSummary] = field(default_factory=list)
    _crds: list[CrdSummary] = field(default_factory=list)
    _permission_error_on_crd: bool = False

    def read_deployment_env_value(
        self,
        *,
        namespace: str,
        deployment: str,
        container: str | None = None,
        env_name: str,
    ) -> str | None:
        """Read an env var value from a deployment spec.
        
        Args:
            namespace: Namespace name
            deployment: Deployment name
            container: Optional container name
            env_name: Environment variable name to find
            
        Returns:
            The env var value, or None if not found
            
        Raises:
            KubernetesApiPermissionError: If read is denied (RBAC)
            KubernetesApiNotFoundError: If deployment/namespace not found
        """
        # Check for permission error
        if (namespace, deployment) in self._permission_error_on:
            raise KubernetesApiPermissionError(
                f'deployments.apps "{deployment}" is forbidden',
                resource="deployment",
                namespace=namespace,
                operation="read_deployment_env_value",
            )
        
        # Check for not found error
        if (namespace, deployment) in self._not_found_on:
            raise KubernetesApiNotFoundError(
                f'deployments.apps "{deployment}" not found',
                resource="deployment",
                namespace=namespace,
                operation="read_deployment_env_value",
            )
        
        # Look up configured env values
        key = f"{namespace}/{deployment}"
        if key in self._deployment_env_values:
            env_vars = self._deployment_env_values[key]
            return env_vars.get(env_name)
        
        return None

    def read_namespace_uid(self, name: str) -> str | None:
        """Read the UID of a namespace.
        
        Args:
            name: Namespace name
            
        Returns:
            The namespace UID, or None if not found
        """
        return self._namespace_uids.get(name)

    # === New methods for kubectl migration ===

    def list_warning_events_for_all_namespaces(
        self,
        *,
        limit: int,
        timeout_seconds: int | None = None,
    ) -> list[EventProjection]:
        """List warning events across all namespaces.
        
        Args:
            limit: Maximum number of events to return
            timeout_seconds: Optional timeout (ignored in fake)
            
        Returns:
            List of EventProjection for warning events
        """
        return self._warning_events[:limit]

    def list_namespaced_deployments(
        self,
        namespace: str,
        *,
        timeout_seconds: int | None = None,
    ) -> list[DeploymentProjection]:
        """List deployments in a namespace.
        
        Args:
            namespace: Namespace name
            timeout_seconds: Optional timeout (ignored in fake)
            
        Returns:
            List of DeploymentProjection
        """
        return self._deployments.get(namespace, [])

    def list_namespaced_statefulsets(
        self,
        namespace: str,
        *,
        timeout_seconds: int | None = None,
    ) -> list[StatefulSetSummary]:
        """List statefulsets in a namespace.
        
        Args:
            namespace: Namespace name
            timeout_seconds: Optional timeout (ignored in fake)
            
        Returns:
            List of StatefulSetSummary
        """
        return self._statefulsets.get(namespace, [])

    def list_namespaced_pods(
        self,
        namespace: str,
        *,
        label_selector: str | None = None,
        field_selector: str | None = None,
        timeout_seconds: int | None = None,
    ) -> list[PodSummary]:
        """List pods in a namespace.
        
        Args:
            namespace: Namespace name
            label_selector: Optional label selector (ignored in fake)
            field_selector: Optional field selector (ignored in fake)
            timeout_seconds: Optional timeout (ignored in fake)
            
        Returns:
            List of PodSummary
        """
        return self._pods.get(namespace, [])

    def list_nodes(
        self,
        *,
        timeout_seconds: int | None = None,
    ) -> list[NodeSummary]:
        """List all nodes.
        
        Args:
            timeout_seconds: Optional timeout (ignored in fake)
            
        Returns:
            List of NodeSummary
        """
        return self._nodes

    def list_crds(
        self,
        *,
        timeout_seconds: int | None = None,
    ) -> list[CrdSummary]:
        """List all CRDs.
        
        Args:
            timeout_seconds: Optional timeout (ignored in fake)
            
        Returns:
            List of CrdSummary
            
        Raises:
            KubernetesApiPermissionError: If _permission_error_on_crd is True
        """
        if self._permission_error_on_crd:
            raise KubernetesApiPermissionError(
                "CustomResourceDefinition is forbidden",
                resource="CustomResourceDefinition",
                operation="list_crds",
            )
        return self._crds

    @classmethod
    def with_deployment_env(
        cls,
        *,
        namespace: str,
        deployment: str,
        env_vars: dict[str, str],
    ) -> FakeKubernetesReadClient:
        """Create a fake client that returns specific env vars from a deployment.
        
        Args:
            namespace: Namespace name
            deployment: Deployment name
            env_vars: Dict of env var names to values
            
        Returns:
            FakeKubernetesReadClient configured to return these env vars
        """
        fake = cls()
        key = f"{namespace}/{deployment}"
        fake._deployment_env_values[key] = env_vars
        return fake

    @classmethod
    def with_permission_error(
        cls,
        *,
        namespace: str,
        deployment: str,
    ) -> FakeKubernetesReadClient:
        """Create a fake client that raises permission error for a deployment.
        
        Args:
            namespace: Namespace name
            deployment: Deployment name
            
        Returns:
            FakeKubernetesReadClient configured to raise KubernetesApiPermissionError
        """
        fake = cls()
        fake._permission_error_on = [(namespace, deployment)]
        return fake

    @classmethod
    def with_not_found(
        cls,
        *,
        namespace: str,
        deployment: str,
    ) -> FakeKubernetesReadClient:
        """Create a fake client that raises not found for a deployment.
        
        Args:
            namespace: Namespace name
            deployment: Deployment name
            
        Returns:
            FakeKubernetesReadClient configured to raise KubernetesApiNotFoundError
        """
        fake = cls()
        fake._not_found_on = [(namespace, deployment)]
        return fake

    @classmethod
    def with_namespace_uid(
        cls,
        *,
        namespace: str,
        uid: str,
    ) -> FakeKubernetesReadClient:
        """Create a fake client that returns a specific namespace UID.
        
        Args:
            namespace: Namespace name
            uid: The UID to return
            
        Returns:
            FakeKubernetesReadClient configured to return this UID
        """
        fake = cls()
        fake._namespace_uids[namespace] = uid
        return fake

    @classmethod
    def with_warning_events(
        cls,
        events: list[EventProjection],
    ) -> FakeKubernetesReadClient:
        """Create a fake client that returns specific warning events.
        
        Args:
            events: List of warning events to return
            
        Returns:
            FakeKubernetesReadClient configured with these events
        """
        fake = cls()
        fake._warning_events = events
        return fake

    @classmethod
    def with_empty_cluster(cls) -> FakeKubernetesReadClient:
        """Create a fake client with empty cluster data.
        
        Returns:
            FakeKubernetesReadClient with empty pods, nodes, events
        """
        fake = cls()
        fake._warning_events = []
        fake._deployments = {}
        fake._statefulsets = {}
        fake._pods = {}
        fake._nodes = []
        fake._crds = []
        return fake

    @classmethod
    def with_crd_permission_error(cls) -> FakeKubernetesReadClient:
        """Create a fake client that raises permission error on CRD listing.
        
        Returns:
            FakeKubernetesReadClient configured to raise KubernetesApiPermissionError for CRDs
        """
        fake = cls()
        fake._permission_error_on_crd = True
        return fake

    @classmethod
    def with_crds(
        cls,
        crds: list[CrdSummary],
    ) -> FakeKubernetesReadClient:
        """Create a fake client that returns specific CRDs.
        
        Args:
            crds: List of CRDs to return
            
        Returns:
            FakeKubernetesReadClient configured with these CRDs
        """
        fake = cls()
        fake._crds = crds
        return fake


# Recording fake for testing selector semantics
class RecordingFakeKubernetesReadClient(FakeKubernetesReadClient):
    """Fake client that records method calls for verification."""

    def __init__(self) -> None:
        super().__init__()
        self.warning_events_field_selector: str | None = None
        self.deployments_field_selector: str | None = None
        self.pods_field_selector: str | None = None

    def list_warning_events_for_all_namespaces(
        self,
        *,
        limit: int,
        timeout_seconds: int | None = None,
    ) -> list[EventProjection]:
        # Record that we were called with field_selector="type=Warning"
        self.warning_events_field_selector = "type=Warning"
        return super().list_warning_events_for_all_namespaces(
            limit=limit, timeout_seconds=timeout_seconds
        )

    def list_namespaced_deployments(
        self,
        namespace: str,
        *,
        timeout_seconds: int | None = None,
    ) -> list[DeploymentProjection]:
        return super().list_namespaced_deployments(namespace, timeout_seconds=timeout_seconds)

    def list_namespaced_statefulsets(
        self,
        namespace: str,
        *,
        timeout_seconds: int | None = None,
    ) -> list[StatefulSetSummary]:
        return super().list_namespaced_statefulsets(namespace, timeout_seconds=timeout_seconds)

    def list_namespaced_pods(
        self,
        namespace: str,
        *,
        label_selector: str | None = None,
        field_selector: str | None = None,
        timeout_seconds: int | None = None,
    ) -> list[PodSummary]:
        self.pods_field_selector = field_selector
        return super().list_namespaced_pods(
            namespace, label_selector=label_selector, field_selector=field_selector,
            timeout_seconds=timeout_seconds
        )


__all__ = ["FakeKubernetesReadClient", "RecordingFakeKubernetesReadClient"]
