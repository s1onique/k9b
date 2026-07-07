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


@dataclass
class FakeKubernetesReadClient:
    """Fake KubernetesReadClient for unit testing.

    This provides a minimal interface matching KubernetesReadClient for tests
    that need to mock the Kubernetes client boundary.

    Default behavior: returns None for unconfigured reads. Use the factory
    methods or set specific behaviors before use.

    Use factory methods for common scenarios:
    - with_deployment_env(): return specific env var values
    - with_permission_error(): raise KubernetesApiPermissionError
    - with_not_found(): raise KubernetesApiNotFoundError
    - with_namespace_uid(): return specific namespace UIDs
    """

    # Pre-configured behaviors
    _deployment_env_values: dict[str, dict[str, str]] = field(default_factory=dict)
    _namespace_uids: dict[str, str | None] = field(default_factory=dict)
    _permission_error_on: list[tuple[str, str]] = field(default_factory=list)  # (namespace, deployment)
    _not_found_on: list[tuple[str, str]] = field(default_factory=list)  # (namespace, deployment)

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


__all__ = ["FakeKubernetesReadClient"]
