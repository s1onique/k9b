#!/usr/bin/env python3
"""Provider preflight gate for k9b labs.

DEPRECATED: This module is a thin wrapper around scripts.lab_common.provider_preflight.
New code should import from scripts.lab_common.provider_preflight directly.

This module is kept for backward compatibility with existing workflows.
"""

from __future__ import annotations

from pathlib import Path

# Re-export everything from lab_common for backward compatibility
# Re-export internal functions for backward compatibility with existing tests
from scripts.lab_common.provider_preflight import (
    FAILURE_PROVIDER_CONFIG_ERROR,
    FAILURE_PROVIDER_CONNECTION_FAILED,
    FAILURE_PROVIDER_DISABLED_REQUIRED,
    FAILURE_PROVIDER_NOT_INITIALIZED,
    FAILURE_PROVIDER_UNAVAILABLE,
    ProviderPreflightResult,
    _evaluate_provider_state,
)
from scripts.lab_common.provider_preflight import (
    run_provider_preflight as _run_provider_preflight,
)


def run_provider_preflight(
    kubeconfig: str,
    namespace: str,
    service: str,
    port: int,
    artifact_dir: Path,
    require_provider_configured: bool = True,
    require_provider_invocation_possible: bool = True,
    timeout_seconds: int = 30,
    backend_deployment: str = "k9b-backend",
    backend_container: str = "k9b-backend",
) -> ProviderPreflightResult:
    """Backward-compatible provider preflight wrapper.

    Kept as an explicit function because existing workflow contract tests assert
    that this compatibility module still defines `run_provider_preflight`.
    """
    return _run_provider_preflight(
        kubeconfig=kubeconfig,
        namespace=namespace,
        service=service,
        port=port,
        artifact_dir=artifact_dir,
        require_provider_configured=require_provider_configured,
        require_provider_invocation_possible=require_provider_invocation_possible,
        timeout_seconds=timeout_seconds,
        backend_deployment=backend_deployment,
        backend_container=backend_container,
    )
from scripts.lab_common.provider_status import (
    ProviderStatus,
    _find_dependency_by_name,
    parse_provider_status_from_health_details,
)

# Re-export for backward compatibility
__all__ = [
    "ProviderPreflightResult",
    "ProviderStatus",
    "run_provider_preflight",
    "parse_provider_status_from_health_details",
    "_find_dependency_by_name",
    "_evaluate_provider_state",
    "FAILURE_PROVIDER_DISABLED_REQUIRED",
    "FAILURE_PROVIDER_UNAVAILABLE",
    "FAILURE_PROVIDER_NOT_INITIALIZED",
    "FAILURE_PROVIDER_CONNECTION_FAILED",
    "FAILURE_PROVIDER_CONFIG_ERROR",
]


# Default service name for CLI
_DEFAULT_SERVICE = "k9b-backend"


def main() -> int:
    """CLI entry point for provider preflight."""
    import argparse

    from scripts.lab_common.constants import (
        DEFAULT_K9B_BACKEND_PORT,
        DEFAULT_K9B_NAMESPACE,
    )
    
    parser = argparse.ArgumentParser(description="Run k9b provider preflight check")
    parser.add_argument("--kubeconfig", required=True, help="Path to kubeconfig")
    parser.add_argument("--namespace", default=DEFAULT_K9B_NAMESPACE, help="k9b namespace")
    parser.add_argument("--service", default=_DEFAULT_SERVICE, help="k9b backend service")
    parser.add_argument("--port", type=int, default=DEFAULT_K9B_BACKEND_PORT, help="k9b backend port")
    parser.add_argument("--artifact-dir", required=True, help="Artifact directory")
    parser.add_argument(
        "--require-provider-configured",
        action="store_true",
        default=True,
        help="Require provider to be configured",
    )
    parser.add_argument(
        "--require-provider-invocation-possible",
        action="store_true",
        default=True,
        help="Require provider invocation to be possible",
    )
    
    args = parser.parse_args()
    
    result = run_provider_preflight(
        kubeconfig=args.kubeconfig,
        namespace=args.namespace,
        service=args.service,
        port=args.port,
        artifact_dir=Path(args.artifact_dir),
        require_provider_configured=args.require_provider_configured,
        require_provider_invocation_possible=args.require_provider_invocation_possible,
    )
    
    print(f"Provider Preflight: {'PASSED' if result.passed else 'FAILED'}")
    print(f"Check method: {result.check_method}")
    print(f"Failure class: {result.failure_class}")
    print(f"Message: {result.message}")
    
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
