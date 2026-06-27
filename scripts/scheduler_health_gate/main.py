"""Main module for scheduler health gate.

This module provides backward-compatible re-exports from the refactored
scheduler health gate components. For new code, import directly from:
    - scripts.scheduler_health_gate.cli: CLI entry point and orchestration
    - scripts.scheduler_health_gate.contracts: Constants and data types
    - scripts.scheduler_health_gate.collect: Kubernetes collection helpers
    - scripts.scheduler_health_gate.evaluate: Health evaluation logic
    - scripts.scheduler_health_gate.render: Output formatting

This module exists to preserve import compatibility for existing callers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

# Import collect as private module for wrapper functions
from . import collect as _collect

# Re-export cli main function
from .cli import main as cli_main

# Re-export from contracts for backward compatibility
from .contracts import (  # noqa: F401
    FAILURE_SCHEDULER_CRASH_LOOP,
    FAILURE_SCHEDULER_MISSING,
    FAILURE_SCHEDULER_NOT_READY,
    SCHEDULER_DEPLOYMENT_NAME,
    SCHEDULER_POD_SELECTOR,
    SchedulerHealthResult,
)

# Re-export from evaluate for backward compatibility
from .evaluate import (  # noqa: F401
    check_crash_loop,
    check_terminated_pods,
    check_waiting_pods,
)

# Backward-compatible underscore aliases for old private helper names
# For kubectl-backed helpers, we use wrappers to preserve monkeypatch compatibility
_run_kubectl = _collect.run_kubectl


def _with_main_kubectl(func: Any, *args: Any, **kwargs: Any) -> Any:
    """Execute func with main module's _run_kubectl in collect module.
    
    This preserves backward compatibility for tests that monkeypatch main._run_kubectl.
    """
    original = _collect.run_kubectl
    _collect.run_kubectl = _run_kubectl
    try:
        return func(*args, **kwargs)
    finally:
        _collect.run_kubectl = original


def _get_scheduler_deployment_status(kubeconfig: str, namespace: str) -> dict[str, Any]:
    """Get scheduler deployment status (wrapper for monkeypatch compat)."""
    return cast(
        dict[str, Any],
        _with_main_kubectl(
            _collect.get_scheduler_deployment_status,
            kubeconfig,
            namespace,
        ),
    )


def _get_scheduler_pod_selector(
    kubeconfig: str,
    namespace: str,
    deployment_name: str,
) -> str:
    """Get scheduler pod selector (wrapper for monkeypatch compat)."""
    return cast(
        str,
        _with_main_kubectl(
            _collect.get_scheduler_pod_selector,
            kubeconfig,
            namespace,
            deployment_name,
        ),
    )


def _get_scheduler_pods(
    kubeconfig: str,
    namespace: str,
    selector: str,
) -> dict[str, Any]:
    """Get scheduler pods (wrapper for monkeypatch compat)."""
    return cast(
        dict[str, Any],
        _with_main_kubectl(
            _collect.get_scheduler_pods,
            kubeconfig,
            namespace,
            selector,
        ),
    )


def _get_namespace_events(
    kubeconfig: str,
    namespace: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Get namespace events (wrapper for monkeypatch compat)."""
    return cast(
        list[dict[str, Any]],
        _with_main_kubectl(
            _collect.get_namespace_events,
            kubeconfig,
            namespace,
            limit,
        ),
    )


# Non-kubectl-backed helpers are direct aliases
_check_crash_loop = check_crash_loop
_check_waiting_pods = check_waiting_pods
_check_terminated_pods = check_terminated_pods
_collect_scheduler_logs = _collect.collect_scheduler_logs

# Store original wrapper references for patch detection
_ORIGINAL_GET_DEPLOYMENT = _get_scheduler_deployment_status
_ORIGINAL_GET_SELECTOR = _get_scheduler_pod_selector
_ORIGINAL_GET_PODS = _get_scheduler_pods
_ORIGINAL_GET_EVENTS = _get_namespace_events


# Also expose the non-underscore versions for direct use
def get_scheduler_deployment_status(kubeconfig: str, namespace: str) -> dict[str, Any]:
    """Get scheduler deployment status."""
    return _collect.get_scheduler_deployment_status(kubeconfig, namespace)


def get_scheduler_pod_selector(
    kubeconfig: str,
    namespace: str,
    deployment_name: str,
) -> str:
    """Get scheduler pod selector."""
    return _collect.get_scheduler_pod_selector(kubeconfig, namespace, deployment_name)


def get_scheduler_pods(
    kubeconfig: str,
    namespace: str,
    selector: str,
) -> dict[str, Any]:
    """Get scheduler pods."""
    return _collect.get_scheduler_pods(kubeconfig, namespace, selector)


def get_namespace_events(
    kubeconfig: str,
    namespace: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Get namespace events."""
    return _collect.get_namespace_events(kubeconfig, namespace, limit)


def run_kubectl(
    kubeconfig: str,
    namespace: str,
    args: list[str],
    timeout: int = 30,
) -> tuple[int, str, str]:
    """Run kubectl command."""
    return _collect.run_kubectl(kubeconfig, namespace, args, timeout)


__all__ = [
    # Contracts
    "FAILURE_SCHEDULER_CRASH_LOOP",
    "FAILURE_SCHEDULER_MISSING",
    "FAILURE_SCHEDULER_NOT_READY",
    "SCHEDULER_DEPLOYMENT_NAME",
    "SCHEDULER_POD_SELECTOR",
    "SchedulerHealthResult",
    # Collect functions
    "get_namespace_events",
    "get_scheduler_deployment_status",
    "get_scheduler_pod_selector",
    "get_scheduler_pods",
    "run_kubectl",
    # Evaluate functions
    "check_crash_loop",
    "check_terminated_pods",
    "check_waiting_pods",
    # Backward-compatible underscore aliases
    "_check_crash_loop",
    "_check_waiting_pods",
    "_check_terminated_pods",
    "_collect_scheduler_logs",
    "_get_scheduler_deployment_status",
    "_get_scheduler_pod_selector",
    "_get_scheduler_pods",
    "_get_namespace_events",
    "_run_kubectl",
    # Entry points
    "run_scheduler_health_gate",
    "main",
]


def _is_patched(func_ref: Any, original_func: Any) -> bool:
    """Check if a function has been patched from its original value."""
    return func_ref is not original_func


def run_scheduler_health_gate(
    kubeconfig: str,
    namespace: str,
    artifact_dir: Path,
) -> SchedulerHealthResult:
    """Check scheduler health and classify failures.
    
    Args:
        kubeconfig: Path to kubeconfig file
        namespace: Kubernetes namespace
        artifact_dir: Directory for artifacts
        
    Returns:
        SchedulerHealthResult with classification and diagnostics
    """
    from . import cli as _cli

    # Check if cli helpers have been patched (existing test pattern)
    cli_patched = (
        _is_patched(_cli.get_scheduler_deployment_status, _collect.get_scheduler_deployment_status)
        or _is_patched(_cli.get_scheduler_pod_selector, _collect.get_scheduler_pod_selector)
        or _is_patched(_cli.get_scheduler_pods, _collect.get_scheduler_pods)
        or _is_patched(_cli.get_namespace_events, _collect.get_namespace_events)
    )

    # Check if main helpers have been patched (backward compat pattern)
    # Compare against stored originals to detect when caller has replaced them
    main_patched = (
        _is_patched(_get_scheduler_deployment_status, _ORIGINAL_GET_DEPLOYMENT)
        or _is_patched(_get_scheduler_pod_selector, _ORIGINAL_GET_SELECTOR)
        or _is_patched(_get_scheduler_pods, _ORIGINAL_GET_PODS)
        or _is_patched(_get_namespace_events, _ORIGINAL_GET_EVENTS)
    )

    if not cli_patched and not main_patched:
        # No patching detected, use standard path
        from .cli import run_scheduler_health_gate as _run
        return _run(kubeconfig, namespace, artifact_dir)

    if cli_patched:
        # Tests patch cli helpers directly - preserve that path
        from .cli import run_scheduler_health_gate as _run
        return _run(kubeconfig, namespace, artifact_dir)

    # Caller patched main helpers - wire them to cli
    orig_get_deployment = _cli.get_scheduler_deployment_status
    orig_get_selector = _cli.get_scheduler_pod_selector
    orig_get_pods = _cli.get_scheduler_pods
    orig_get_events = _cli.get_namespace_events

    try:
        # Wire the underscore-prefixed versions if they were patched
        _cli.get_scheduler_deployment_status = _get_scheduler_deployment_status
        _cli.get_scheduler_pod_selector = _get_scheduler_pod_selector
        _cli.get_scheduler_pods = _get_scheduler_pods
        _cli.get_namespace_events = _get_namespace_events

        from .cli import run_scheduler_health_gate as _run
        return _run(kubeconfig, namespace, artifact_dir)
    finally:
        _cli.get_scheduler_deployment_status = orig_get_deployment
        _cli.get_scheduler_pod_selector = orig_get_selector
        _cli.get_scheduler_pods = orig_get_pods
        _cli.get_namespace_events = orig_get_events


def main(argv: list[str] | None = None) -> int:
    """Main entry point for scheduler health gate CLI.
    
    Args:
        argv: Command line arguments (defaults to sys.argv)
        
    Returns:
        Exit code: 0 for pass, 1 for fail
    """
    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
