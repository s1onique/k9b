"""Shared helpers for OTel Demo K8s injection cleanup tests."""

from __future__ import annotations

__test__ = False

from scripts.k9b_lab_common_helpers import KubectlResult


def make_kubectl_result(
    success: bool = True,
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
    data: dict[str, object] | None = None,
) -> KubectlResult:
    """Factory for KubectlResult with sensible defaults."""
    return KubectlResult(
        success=success,
        stdout=stdout,
        stderr=stderr,
        returncode=returncode,
        data=data,
    )


def make_deployment_not_found_result(deployment: str = "shipping") -> KubectlResult:
    """Factory for deployment-not-found error."""
    return make_kubectl_result(
        success=False,
        stderr=f'deployments.apps "{deployment}" not found',
        returncode=1,
    )


def make_path_absent_result() -> KubectlResult:
    """Factory for path-absent JSON Patch error (idempotent success)."""
    return make_kubectl_result(
        success=False,
        stderr='{"message":"doc is missing path: /spec/template/spec/nodeSelector"}',
        returncode=1,
    )


def make_nodeselector_absent_result() -> KubectlResult:
    """Factory for nodeSelector path-absent error (idempotent success)."""
    return make_kubectl_result(
        success=False,
        stderr="spec.template.spec.nodeselector: doesn't exist",
        returncode=1,
    )


def make_connection_error_result() -> KubectlResult:
    """Factory for connection error (fail-closed)."""
    return make_kubectl_result(
        success=False,
        stderr="connection refused",
        returncode=1,
    )


def make_generic_not_found_result() -> KubectlResult:
    """Factory for generic not-found error (fail-closed)."""
    return make_kubectl_result(
        success=False,
        stderr='{"message":"not found"}',
        returncode=1,
    )


def make_namespace_not_found_result(namespace: str = "otel-demo") -> KubectlResult:
    """Factory for namespace-not-found error (fail-closed)."""
    return make_kubectl_result(
        success=False,
        stderr=f'namespace "{namespace}" not found',
        returncode=1,
    )
