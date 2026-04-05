"""Helpers for representing real cluster snapshots."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


@dataclass(frozen=True)
class ClusterSnapshotMetadata:
    cluster_id: str
    captured_at: datetime
    control_plane_version: str
    node_count: int
    pod_count: Optional[int] = None
    region: Optional[str] = None
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class HelmReleaseRecord:
    name: str
    namespace: str
    chart: str
    chart_version: str
    app_version: Optional[str] = None

    @property
    def key(self) -> str:
        return f"{self.namespace}/{self.name}"

    def to_dict(self) -> Dict[str, Optional[str]]:
        return {
            "name": self.name,
            "namespace": self.namespace,
            "chart": self.chart,
            "chart_version": self.chart_version,
            "app_version": self.app_version,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "HelmReleaseRecord":
        chart = str(data.get("chart") or "")
        return cls(
            name=str(data["name"]),
            namespace=str(data.get("namespace", "default")),
            chart=chart,
            chart_version=str(data.get("chart_version") or _extract_chart_version(chart)),
            app_version=_optional_str(data.get("app_version")),
        )


@dataclass(frozen=True)
class CRDRecord:
    name: str
    served_versions: Tuple[str, ...]
    storage_version: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "served_versions": list(self.served_versions),
            "storage_version": self.storage_version,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CRDRecord":
        served_versions = _extract_served_versions(data)
        storage_version = _extract_storage_version(data)
        return cls(
            name=str(data["name"]),
            served_versions=served_versions,
            storage_version=storage_version,
        )


@dataclass(frozen=True)
class ClusterSnapshot:
    metadata: ClusterSnapshotMetadata
    workloads: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)
    helm_releases: Dict[str, HelmReleaseRecord] = field(default_factory=dict)
    crds: Dict[str, CRDRecord] = field(default_factory=dict)
    collection_status: "CollectionStatus" = field(default_factory=lambda: CollectionStatus())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ClusterSnapshot":
        metadata_source = data.get("metadata") if isinstance(data, Mapping) else {}
        if not metadata_source:
            metadata_source = data
        metadata = ClusterSnapshotMetadata(
            cluster_id=str(metadata_source["cluster_id"]),
            captured_at=_parse_timestamp(metadata_source.get("captured_at")),
            control_plane_version=str(metadata_source.get("control_plane_version", "unknown")),
            node_count=int(metadata_source.get("node_count", 0)),
            pod_count=_safe_int(metadata_source.get("pod_count")),
            region=_truthy(metadata_source.get("region")),
            labels={
                str(key): str(value)
                for key, value in (metadata_source.get("labels") or {}).items()
            },
        )
        workloads = {
            str(key): value
            for key, value in (data.get("workloads") or {}).items()
        }
        metrics = {
            str(key): float(value)
            for key, value in (data.get("metrics") or {}).items()
            if _is_number_like(value)
        }
        helm_releases = _build_helm_releases(data.get("helm_releases"))
        crds = _build_crds(data.get("crds"))
        status = _build_collection_status(data.get("status"))
        return cls(
            metadata=metadata,
            workloads=workloads,
            metrics=metrics,
            helm_releases=helm_releases,
            crds=crds,
            collection_status=status,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metadata": {
                "cluster_id": self.metadata.cluster_id,
                "captured_at": self.metadata.captured_at.isoformat(),
                "control_plane_version": self.metadata.control_plane_version,
                "node_count": self.metadata.node_count,
                "pod_count": self.metadata.pod_count,
                "region": self.metadata.region,
                "labels": self.metadata.labels,
            },
            "workloads": self.workloads,
            "metrics": self.metrics,
            "helm_releases": [release.to_dict() for release in self.helm_releases.values()],
            "crds": [crd.to_dict() for crd in self.crds.values()],
            "status": self.collection_status.to_dict(),
        }


def extract_cluster_snapshots(fixture: Mapping[str, Any]) -> List[ClusterSnapshot]:
    raw = fixture.get("cluster_snapshots")
    if not raw:
        return []
    snapshots: List[ClusterSnapshot] = []
    items: Iterable[Mapping[str, Any]]
    if isinstance(raw, Mapping):
        items = cast_iterable(raw.values())
    elif isinstance(raw, list):
        items = cast_iterable(raw)
    else:
        return []
    for entry in items:
        if isinstance(entry, Mapping):
            snapshots.append(ClusterSnapshot.from_dict(entry))
    return snapshots


def cast_iterable(iterable: Iterable[Any]) -> Iterable[Mapping[str, Any]]:
    for item in iterable:
        if isinstance(item, Mapping):
            yield item


def _build_helm_releases(source: Any) -> Dict[str, HelmReleaseRecord]:
    releases: Dict[str, HelmReleaseRecord] = {}
    for entry in _iter_dicts(source):
        try:
            release = HelmReleaseRecord.from_dict(entry)
        except KeyError:
            continue
        releases[release.key] = release
    return releases


def _build_crds(source: Any) -> Dict[str, CRDRecord]:
    crds: Dict[str, CRDRecord] = {}
    for entry in _iter_dicts(source):
        try:
            crd = CRDRecord.from_dict(entry)
        except KeyError:
            continue
        crds[crd.name] = crd
    return crds


def _iter_dicts(items: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(items, Mapping):
        items_iter: Iterable[Any] = items.values()
    else:
        items_iter = items or []
    for item in items_iter:
        if isinstance(item, Mapping):
            yield item


def _parse_timestamp(value: Optional[str]) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    if value.endswith("Z"):
        value = f"{value[:-1]}+00:00"
    return datetime.fromisoformat(value)


def _safe_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _truthy(value: Any) -> Optional[str]:
    if value in {None, ""}:
        return None
    return str(value)


def _is_number_like(value: Any) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _extract_chart_version(chart: str) -> str:
    if not chart:
        return "unknown"
    if "-" not in chart:
        return chart
    return chart.rsplit("-", 1)[-1]


def _optional_str(value: Any) -> Optional[str]:
    if value in {None, ""}:
        return None
    return str(value)


def _extract_served_versions(source: Mapping[str, Any]) -> Tuple[str, ...]:
    served = source.get("served_versions")
    if isinstance(served, Iterable):
        items = tuple(str(item) for item in served if str(item))
        if items:
            return items
    spec = source.get("spec") or {}
    versions = spec.get("versions")
    if isinstance(versions, Iterable):
        return tuple(
            str(version.get("name"))
            for version in versions
            if isinstance(version, Mapping) and version.get("served")
        )
    return ()


def _extract_storage_version(source: Mapping[str, Any]) -> Optional[str]:
    storage = source.get("storage_version")
    if _truthy(storage):
        return str(storage)
    spec = source.get("spec") or {}
    versions = spec.get("versions")
    if isinstance(versions, Iterable):
        for version in versions:
            if isinstance(version, Mapping) and version.get("storage"):
                return _optional_str(version.get("name"))
    return None


def _build_collection_status(source: Any) -> CollectionStatus:
    if not isinstance(source, Mapping):
        return CollectionStatus()
    helm_error = _optional_str(source.get("helm_error"))
    missing = source.get("missing_evidence")
    if isinstance(missing, Iterable):
        missing_list = tuple(str(item) for item in missing if str(item))
    else:
        missing_list = ()
    return CollectionStatus(helm_error=helm_error, missing_evidence=missing_list)


@dataclass(frozen=True)
class CollectionStatus:
    """Records collection issues so later reasoning can treat missing evidence explicitly."""

    helm_error: Optional[str] = None
    missing_evidence: Tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "helm_error": self.helm_error,
            "missing_evidence": list(self.missing_evidence),
        }
