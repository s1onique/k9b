"""Cluster identity using kube-system namespace UID."""

from __future__ import annotations

import json
import logging
import subprocess
from typing import Any

_logger = logging.getLogger(__name__)


def derive_cluster_uid(
    kube_context: str | None = None,
    cluster_label: str | None = None,
) -> str | None:
    """Derive the canonical cluster UID from the kube-system namespace UID.

    This uses the Kubernetes API to get the kube-system namespace's metadata.uid,
    which serves as the durable cluster identity anchor. This UID persists
    across cluster upgrades/rebuilds and is independent of operator-chosen
    labels or context names.

    Args:
        kube_context: Kubernetes context name for kubectl --context flag.
        cluster_label: Fallback label if kubectl is unavailable.

    Returns:
        The cluster UID (kube-system namespace UID) or None if unavailable.

    Invariants:
        - Same cluster under different contexts → same cluster_uid
        - Rebuilt cluster with same label → different cluster_uid
        - Canonical identity is ONLY the real kube-system UID; no synthetic fallbacks
    """
    try:
        cmd = ["kubectl", "get", "namespace", "kube-system", "-o", "json"]
        if kube_context:
            cmd.extend(["--context", kube_context])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            data = json.loads(result.stdout)
            uid = data.get("metadata", {}).get("uid")
            if uid:
                return str(uid)

        _logger.debug(
            "Failed to get kube-system namespace UID: %s",
            result.stderr[:200] if result.stderr else "non-zero exit",
        )

    except FileNotFoundError:
        _logger.debug("kubectl not found in PATH")
    except subprocess.TimeoutExpired:
        _logger.debug("kubectl get namespace timed out")
    except json.JSONDecodeError as exc:
        _logger.debug("Failed to parse kubectl output: %s", exc)

    # Return None - do NOT fall back to cluster_label or "unknown"
    # Canonical identity is ONLY the real kube-system namespace UID
    # Display/legacy identity should use separate fields (cluster_label, cluster_context)
    _logger.debug(
        "Cluster UID unavailable; use cluster_label for display purposes"
    )
    return None


def get_cluster_uid_from_snapshot(
    snapshot_data: dict[str, Any],
    kube_context: str | None = None,
) -> str | None:
    """Extract or derive cluster UID from snapshot data.

    If the snapshot contains a cluster_uid field, use it directly.
    Otherwise, derive it using derive_cluster_uid().

    IMPORTANT: This returns the canonical cluster_uid ONLY.
    Display/legacy identity should use cluster_label or cluster_context.

    Args:
        snapshot_data: The ClusterSnapshot serialized data.
        kube_context: Kubernetes context for derivation.

    Returns:
        The cluster UID (kube-system namespace UID) or None if unavailable.
    """
    # Check for pre-populated cluster_uid
    if snapshot_data.get("cluster_uid"):
        return str(snapshot_data["cluster_uid"])

    # Also check nested metadata structure
    metadata = snapshot_data.get("metadata", {})
    if metadata and metadata.get("cluster_uid"):
        return str(metadata["cluster_uid"])

    # Do NOT fall back to cluster_id - it is a display field, not canonical identity
    # If cluster_uid is missing, return None to indicate unknown canonical identity
    return None
