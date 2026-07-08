"""Import contract tests for kubernetes_client modules.

These tests ensure backward compatibility by verifying that the public API
remains stable when implementation is split into focused modules.
"""

from __future__ import annotations


def test_kubernetes_client_public_imports_remain_stable() -> None:
    """Verify that kubernetes_client module still exports all public symbols."""
    from k8s_diag_agent.security.kubernetes_client import (
        KubernetesApiNotFoundError,
        KubernetesApiPermissionError,
        KubernetesApiResponseTooLargeError,
        KubernetesApiTimeoutError,
        KubernetesClientError,
        KubernetesClientUnavailableError,
        KubernetesReadClient,
        clear_client_cache,
        create_kubernetes_read_client,
        get_cached_kubernetes_client,
    )

    # Verify classes exist
    assert KubernetesReadClient is not None
    assert KubernetesClientError is not None
    assert KubernetesClientUnavailableError is not None
    assert KubernetesApiPermissionError is not None
    assert KubernetesApiNotFoundError is not None
    assert KubernetesApiTimeoutError is not None
    assert KubernetesApiResponseTooLargeError is not None

    # Verify functions exist
    assert create_kubernetes_read_client is not None
    assert get_cached_kubernetes_client is not None
    assert clear_client_cache is not None


def test_kubernetes_client_model_imports_remain_stable() -> None:
    """Verify that kubernetes_client_models module still exports all models."""
    from k8s_diag_agent.security.kubernetes_client_models import (
        BoundedPodLogResult,
        ContainerStatusProjection,
        CrdSummary,
        DeploymentProjection,
        EventProjection,
        NamespaceProjection,
        NodeSummary,
        PaginationMetadata,
        PodProjection,
        PodSummary,
        SecretProjection,
        ServiceAccountProjection,
        StatefulSetSummary,
    )

    # Verify all models exist
    assert ContainerStatusProjection is not None
    assert DeploymentProjection is not None
    assert EventProjection is not None
    assert NamespaceProjection is not None
    assert NodeSummary is not None
    assert PaginationMetadata is not None
    assert PodProjection is not None
    assert PodSummary is not None
    assert SecretProjection is not None
    assert ServiceAccountProjection is not None
    assert StatefulSetSummary is not None
    assert CrdSummary is not None
    assert BoundedPodLogResult is not None


def test_kubernetes_client_errors_imports_remain_stable() -> None:
    """Verify that kubernetes_client_errors module still exports all errors."""
    from k8s_diag_agent.security.kubernetes_client_errors import (
        KubernetesApiNotFoundError,
        KubernetesApiPermissionError,
        KubernetesApiResponseTooLargeError,
        KubernetesApiTimeoutError,
        KubernetesApiTooManyRequestsError,
        KubernetesClientError,
        KubernetesClientUnavailableError,
    )

    # Verify all errors exist
    assert KubernetesClientError is not None
    assert KubernetesClientUnavailableError is not None
    assert KubernetesApiPermissionError is not None
    assert KubernetesApiNotFoundError is not None
    assert KubernetesApiTimeoutError is not None
    assert KubernetesApiResponseTooLargeError is not None
    assert KubernetesApiTooManyRequestsError is not None


def test_kubernetes_client_pagination_imports_remain_stable() -> None:
    """Verify that kubernetes_client_pagination module still exports all helpers."""
    from k8s_diag_agent.security.kubernetes_client_pagination import (
        list_all_namespaces_pods_summaries,
        list_namespaced_deployments_projected,
        list_namespaced_events_projected,
        list_namespaced_pods_projected,
        sample_failed_pods_bounded,
    )

    # Verify all pagination helpers exist
    assert list_all_namespaces_pods_summaries is not None
    assert list_namespaced_deployments_projected is not None
    assert list_namespaced_events_projected is not None
    assert list_namespaced_pods_projected is not None
    assert sample_failed_pods_bounded is not None


def test_kubernetes_client_config_imports_remain_stable() -> None:
    """Verify that kubernetes_client_config module exports config functions."""
    from k8s_diag_agent.security.kubernetes_client_config import (
        _load_kubernetes_config,
    )

    assert _load_kubernetes_config is not None


def test_cached_client_returns_read_client_contract() -> None:
    """Verify that get_cached_kubernetes_client returns KubernetesReadClient."""
    from k8s_diag_agent.security.kubernetes_client import (
        KubernetesReadClient,
        clear_client_cache,
        get_cached_kubernetes_client,
    )

    # Clear any existing cache
    clear_client_cache()

    # Create client - this should not call the cluster because it lazily loads config
    client = get_cached_kubernetes_client(
        kubeconfig="/tmp/nonexistent",
        context="test_context",
    )

    # Verify it returns the right type
    assert isinstance(client, KubernetesReadClient)

    # Verify key methods exist (they delegate, not call cluster)
    assert hasattr(client, "list_crds")
    assert hasattr(client, "list_warning_events_for_all_namespaces")
    assert hasattr(client, "read_deployment_env_value")
    assert hasattr(client, "list_namespaced_pods_projected")
    assert hasattr(client, "list_nodes")


def test_kubernetes_client_translation_imports_remain_stable() -> None:
    """Verify that kubernetes_client_translation module exports translate_api_exception."""
    from k8s_diag_agent.security.kubernetes_client_translation import (
        translate_api_exception,
    )

    assert translate_api_exception is not None
