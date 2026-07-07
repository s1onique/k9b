"""Live cluster snapshot helpers using kubectl/helm."""
from __future__ import annotations

import json
import logging
import os
import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime

from ..identity.artifact import new_artifact_id
from ..identity.cluster import derive_cluster_uid
from ..kubernetes_auth import (
    AuthMode,
    build_kubectl_env,
    is_in_cluster,
    log_auth_mode,
    resolve_process_auth_mode,
)
from ..security.kubectl_errors import (
    KubectlExecutionError,
    KubectlOutputTooLargeError,
)
from ..security.kubectl_subprocess import (
    run_kubectl,
)
from ..security.path_validation import (
    validate_kube_context_name,
)
from .cluster_snapshot import (
    ClusterHealthSignals,
    ClusterSnapshot,
    ClusterSnapshotMetadata,
    CollectionStatus,
    CRDRecord,
    HelmReleaseRecord,
    NodeConditionCounts,
    PodHealthCounts,
    WarningEventSummary,
)
from .live_snapshot_helpers import (  # noqa: F401 - re-exported for backward compatibility
    _extract_items,
    _int_or_zero,
    _parse_server_version,
    _pod_owned_by_job,
    _summarize_node_conditions,
    _summarize_pod_health,
)

# Re-export is_in_cluster as _is_in_cluster for backward compatibility with test mocks
# that mock k8s_diag_agent.collect.live_snapshot._is_in_cluster
_is_in_cluster = is_in_cluster

# Subprocess timeout for kubectl/helm commands (60s)
KUBECTL_COMMAND_TIMEOUT_SECONDS = 60


def _run_command(
    command: Sequence[str],
    *,
    auth_mode: AuthMode | None = None,
    chunk_size: int | None = 500,
) -> str:
    """Compatibility seam for tests; production delegates to bounded kubectl.

    This function exists to preserve test compatibility with mocks that patch
    k8s_diag_agent.collect.live_snapshot._run_command. Production code should
    use run_kubectl directly when not testing.

    Args:
        command: Command sequence to execute
        auth_mode: Auth mode override (defaults to process-resolved mode)
        chunk_size: Chunk size for kubectl get commands (None disables chunking)

    Returns:
        Command stdout as string

    Raises:
        RuntimeError: If command fails, times out, or binary is not found
    """
    if auth_mode is None:
        auth_mode = _get_auth_mode()
    try:
        return run_kubectl(
            command,
            timeout_seconds=KUBECTL_COMMAND_TIMEOUT_SECONDS,
            auth_mode=auth_mode,
            chunk_size=chunk_size,
        )
    except (KubectlExecutionError, KubectlOutputTooLargeError) as exc:
        raise RuntimeError(str(exc)) from exc

_logger = logging.getLogger(__name__)

# Module-level resolved auth mode (set once per process)
_resolved_auth_mode: AuthMode | None = None


def _get_auth_mode() -> AuthMode:
    """Get or resolve the Kubernetes auth mode for this process.

    Resolves once on first call and caches the result for subsequent calls.
    The resolved mode is used to construct subprocess environment variables.

    Returns:
        Resolved AuthMode (never AUTO - it resolves to IN_CLUSTER or KUBECONFIG).

    """
    global _resolved_auth_mode
    if _resolved_auth_mode is not None:
        return _resolved_auth_mode

    # Use shared helper for auth mode resolution
    _resolved_auth_mode = resolve_process_auth_mode()

    # Log selected auth mode (once, without exposing paths)
    log_auth_mode(_resolved_auth_mode, logger=_logger)

    return _resolved_auth_mode


def list_kube_contexts() -> list[str]:
    """List available Kubernetes contexts.
    
    Returns:
        - ["in-cluster"] when running inside a pod with service account
        - kubeconfig contexts when KUBECONFIG is set or in-cluster auth not detected
    """
    if is_in_cluster():
        return ["in-cluster"]
    # Use _run_command seam for test compatibility
    output = _run_command(
        ["kubectl", "config", "get-contexts", "-o", "name"],
        chunk_size=None,  # No chunking needed for context listing
    )
    return [line.strip() for line in output.splitlines() if line.strip()]


def collect_cluster_snapshot(context: str) -> ClusterSnapshot:
    """Collect cluster data while recording Helm/CRD issues instead of crashing."""
    metadata, node_conditions, pod_counts = _collect_metadata(context)
    helm_releases: dict[str, HelmReleaseRecord] = {}
    helm_error: str | None = None
    try:
        helm_releases = _collect_helm_releases(context)
    except RuntimeError as exc:
        helm_error = str(exc)

    crds: dict[str, CRDRecord] = {}
    missing_evidence: list[str] = []
    try:
        crds = _collect_crds(context)
    except RuntimeError:
        # Record CRD listing failure as missing evidence but keep the rest of the snapshot.
        missing_evidence.append("crd_list")

    job_failures, job_missing = _collect_job_failures(context)
    warning_events, warning_missing = _collect_warning_events(context)
    missing_evidence.extend(job_missing)
    missing_evidence.extend(warning_missing)

    status = CollectionStatus(
        helm_error=helm_error,
        missing_evidence=tuple(missing_evidence),
    )

    health_signals = ClusterHealthSignals(
        node_conditions=node_conditions,
        pod_counts=pod_counts,
        job_failures=job_failures,
        warning_events=warning_events,
    )

    return ClusterSnapshot(
        metadata=metadata,
        workloads={},
        metrics={},
        helm_releases=helm_releases,
        crds=crds,
        collection_status=status,
        health_signals=health_signals,
        artifact_id=new_artifact_id(),
    )


def _collect_metadata(
    context: str,
) -> tuple[ClusterSnapshotMetadata, NodeConditionCounts, PodHealthCounts]:
    version_output = _kubectl(context, "version", "--output", "json")
    control_plane_version = _parse_server_version(version_output)
    node_payload = json.loads(_kubectl(context, "get", "nodes", "-o", "json"))
    node_items = _extract_items(node_payload)
    pod_payload = json.loads(
        _kubectl(context, "get", "pods", "--all-namespaces", "-o", "json")
    )
    pod_items = _extract_items(pod_payload)

    # Use shared helper for cluster_uid derivation (canonical identity)
    cluster_uid = derive_cluster_uid(context)

    metadata = ClusterSnapshotMetadata(
        cluster_id=context,  # Legacy display field (operator-facing)
        captured_at=datetime.now(UTC),
        control_plane_version=control_plane_version,
        node_count=len(node_items),
        cluster_uid=cluster_uid,  # Canonical identity (kube-system namespace UID)
        pod_count=len(pod_items),
    )
    return metadata, _summarize_node_conditions(node_items), _summarize_pod_health(pod_items)


def _collect_helm_releases(context: str) -> dict[str, HelmReleaseRecord]:
    output = _run_helm_command(context, "list", "--all-namespaces", "--output", "json")
    if not output.strip():
        return {}
    payload = json.loads(output)
    entries = payload if isinstance(payload, list) else []
    releases: dict[str, HelmReleaseRecord] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            release = HelmReleaseRecord.from_dict(entry)
        except KeyError:
            continue
        releases[release.key] = release
    return releases


def _collect_crds(context: str) -> dict[str, CRDRecord]:
    output = _kubectl(context, "get", "crds", "-o", "json")
    if not output.strip():
        return {}
    parsed = json.loads(output)
    items = parsed.get("items") if isinstance(parsed, dict) else []
    results: dict[str, CRDRecord] = {}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata") or {}
        name = metadata.get("name")
        if not name:
            continue
        try:
            record = CRDRecord.from_dict({"name": name, "spec": item.get("spec", {})})
        except KeyError:
            continue
        results[record.name] = record
    return results


def _collect_job_failures(context: str) -> tuple[int, tuple[str, ...]]:
    try:
        output = _kubectl(context, "get", "jobs", "--all-namespaces", "-o", "json")
    except RuntimeError:
        return 0, ("jobs",)
    payload = json.loads(output)
    failures = 0
    for entry in _extract_items(payload):
        status = entry.get("status") or {}
        failures += _int_or_zero(status.get("failed"))
    return failures, ()


def _collect_warning_events(
    context: str, limit: int = 6
) -> tuple[tuple[WarningEventSummary, ...], tuple[str, ...]]:
    try:
        output = _kubectl(
            context,
            "get",
            "events",
            "--all-namespaces",
            "--field-selector",
            "type=Warning",
            "--sort-by=.metadata.creationTimestamp",
            "-o",
            "json",
        )
    except RuntimeError:
        return (), ("events",)
    payload = json.loads(output)
    items = _extract_items(payload)
    sorted_items = sorted(
        items,
        key=lambda event: str(
            (event.get("metadata") or {}).get("creationTimestamp") or ""
        ),
        reverse=True,
    )
    events: list[WarningEventSummary] = []
    for entry in sorted_items:
        if len(events) >= limit:
            break
        metadata = entry.get("metadata") or {}
        namespace = str(metadata.get("namespace") or "")
        reason = str(entry.get("reason") or "")
        message = str(entry.get("message") or "")
        last_seen = str(
            metadata.get("lastTimestamp") or
            metadata.get("eventTime") or
            metadata.get("creationTimestamp")
            or ""
        )
        events.append(
            WarningEventSummary(
                namespace=namespace,
                reason=reason,
                message=message,
                count=_int_or_zero(entry.get("count")),
                last_seen=last_seen,
            )
        )
    return tuple(events), ()


def _kubectl(context: str, *args: str) -> str:
    """Build and execute a kubectl command with validated context.

    Uses bounded execution to prevent memory growth from large collections.
    Routes through _run_command seam for test compatibility.

    Args:
        context: Kubernetes context name (validated), or "in-cluster" for service account auth
        *args: kubectl arguments

    Returns:
        Command output

    Raises:
        SecurityError: If context name is invalid
        KubectlOutputTooLargeError: If output exceeds configured limits
        KubectlExecutionError: If command fails
    """
    # Build the command
    if context == "in-cluster":
        cmd = ["kubectl", *args]
    else:
        # Validate context before constructing command
        validated_context = validate_kube_context_name(context)
        cmd = ["kubectl", *args, "--context", validated_context]

    # Use _run_command seam for test compatibility
    return _run_command(cmd)


def _run_helm_command(context: str, *args: str) -> str:
    """Build and execute a helm command with validated context.

    Note: Helm commands don't use bounded execution since they're typically
    small outputs. This function preserves the existing subprocess behavior.

    Args:
        context: Kubernetes context name (validated)
        *args: helm arguments

    Returns:
        Command output

    Raises:
        SecurityError: If context name is invalid
    """
    # Validate context before constructing command
    validated_context = validate_kube_context_name(context)
    return _run_helm_subprocess(["helm", *args, "--kube-context", validated_context])


def _run_helm_subprocess(command: Sequence[str]) -> str:
    """Execute a helm command with auth-mode-aware environment.

    This is used for helm commands which don't need bounded execution
    (helm list typically returns small outputs).
    """
    # Get resolved auth mode (resolves once per process)
    auth_mode = _get_auth_mode()

    # Build subprocess environment based on auth mode
    env = os.environ.copy()
    env_updates = build_kubectl_env(auth_mode)
    for key, value in env_updates.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value

    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=KUBECTL_COMMAND_TIMEOUT_SECONDS,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"`{command[0]}` timed out after {KUBECTL_COMMAND_TIMEOUT_SECONDS}s. "
            "Cluster may be unresponsive or under load."
        ) from exc
    except FileNotFoundError as exc:
        # More specific than OSError; raised when binary is missing from PATH
        raise RuntimeError(f"Command `{command[0]}` not found. Ensure it is on PATH.") from exc
    except OSError as exc:
        # Catches exec format errors (wrong CPU architecture) and other OS-level failures
        raise RuntimeError(
            f"Failed to execute command {command[0]!r}: {exc}. "
            "Check that the binary exists and matches the container CPU architecture."
        ) from exc
    except subprocess.CalledProcessError as exc:
        # Sanitize stderr to prevent credential leakage in error messages
        stderr_output = exc.stderr if exc.stderr else exc.stdout
        from ..security.subprocess_helpers import sanitize_subprocess_error

        message = sanitize_subprocess_error(
            f"`{command[0]}` failed",
            stderr_output,
            max_length=1000,
        )
        raise RuntimeError(message) from exc
    return result.stdout


# Removed: _derive_cluster_uid moved to identity/cluster.py
