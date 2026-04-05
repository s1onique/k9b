"""Live cluster snapshot helpers using kubectl/helm."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from .cluster_snapshot import (
    ClusterSnapshot,
    ClusterSnapshotMetadata,
    CollectionStatus,
    CRDRecord,
    HelmReleaseRecord,
)


def list_kube_contexts() -> List[str]:
    output = _run_command(["kubectl", "config", "get-contexts", "-o", "name"])
    return [line.strip() for line in output.splitlines() if line.strip()]


def collect_cluster_snapshot(context: str) -> ClusterSnapshot:
    """Collect cluster data while recording Helm/CRD issues instead of crashing."""
    metadata = _collect_metadata(context)
    helm_releases: Dict[str, HelmReleaseRecord] = {}
    helm_error: Optional[str] = None
    try:
        helm_releases = _collect_helm_releases(context)
    except RuntimeError as exc:
        helm_error = str(exc)

    crds: Dict[str, CRDRecord] = {}
    missing_evidence: List[str] = []
    try:
        crds = _collect_crds(context)
    except RuntimeError:
        # Record CRD listing failure as missing evidence but keep the rest of the snapshot.
        missing_evidence.append("crd_list")

    status = CollectionStatus(
        helm_error=helm_error,
        missing_evidence=tuple(missing_evidence),
    )

    return ClusterSnapshot(
        metadata=metadata,
        workloads={},
        metrics={},
        helm_releases=helm_releases,
        crds=crds,
        collection_status=status,
    )


def _collect_metadata(context: str) -> ClusterSnapshotMetadata:
    version_output = _kubectl(context, "version", "--output", "json")
    control_plane_version = _parse_server_version(version_output)
    node_count = _count_lines(_kubectl(context, "get", "nodes", "--no-headers"))
    pod_count = _count_lines(_kubectl(context, "get", "pods", "--all-namespaces", "--no-headers"))
    return ClusterSnapshotMetadata(
        cluster_id=context,
        captured_at=datetime.now(timezone.utc),
        control_plane_version=control_plane_version,
        node_count=node_count,
        pod_count=pod_count,
    )


def _collect_helm_releases(context: str) -> Dict[str, HelmReleaseRecord]:
    output = _run_helm_command(context, "list", "--all-namespaces", "--output", "json")
    if not output.strip():
        return {}
    payload = json.loads(output)
    entries = payload if isinstance(payload, list) else []
    releases: Dict[str, HelmReleaseRecord] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            release = HelmReleaseRecord.from_dict(entry)
        except KeyError:
            continue
        releases[release.key] = release
    return releases


def _collect_crds(context: str) -> Dict[str, CRDRecord]:
    output = _kubectl(context, "get", "crds", "-o", "json")
    if not output.strip():
        return {}
    parsed = json.loads(output)
    items = parsed.get("items") if isinstance(parsed, dict) else []
    results: Dict[str, CRDRecord] = {}
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


def _kubectl(context: str, *args: str) -> str:
    return _run_command(["kubectl", *args, "--context", context])


def _run_helm_command(context: str, *args: str) -> str:
    return _run_command(["helm", *args, "--kube-context", context])


def _run_command(command: Sequence[str]) -> str:
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Command `{command[0]}` not found. Ensure it is on PATH.") from exc
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"`{command[0]}` failed: {message}") from exc
    return result.stdout


def _parse_server_version(output: str) -> str:
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "kubectl version output could not be parsed; ensure your kubectl supports `version --output json`."
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError("kubectl version output is not a JSON object.")
    server_info: Any = payload.get("serverVersion")
    if not isinstance(server_info, dict):
        raise RuntimeError("kubectl version output is missing the `serverVersion` section.")
    git_version = server_info.get("gitVersion")
    if not isinstance(git_version, str) or not git_version:
        raise RuntimeError(
            "kubectl version output is missing `serverVersion.gitVersion`; ensure the control plane is reachable."
        )
    return git_version


def _count_lines(output: str) -> int:
    return sum(1 for line in output.splitlines() if line.strip())
