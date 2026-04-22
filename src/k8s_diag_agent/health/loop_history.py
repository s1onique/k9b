"""History and retained-state helpers for the health loop.

Extracts history loading, persistence, and retained-state helper functions from loop.py
into a focused module. Preserves behavior exactly - no schema or artifact contract changes.

This module provides the history management logic that:
1. Loads and persists health history entries
2. Serializes/deserializes health state
3. Provides pure helper functions for history-related formatting

These are pure helpers with no runner logic.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from ..collect.cluster_snapshot import ClusterSnapshot

# Module constants
_LABEL_RE = re.compile(r"[^a-zA-Z0-9_-]+")
_HISTORY_FILENAME = "history.json"
_TRUTHY_ENV_VALUES = {"1", "true", "yes", "y", "on"}


def _safe_label(value: str) -> str:
    """Convert a value to a safe filesystem/URL label."""
    cleaned = _LABEL_RE.sub("-", value or "")
    cleaned = re.sub(r"-+", "-", cleaned)
    cleaned = cleaned.strip("-")
    return cleaned.lower() or "entry"


def _env_is_truthy(value: str | None) -> bool:
    """Check if an environment variable value is considered truthy."""
    if not value:
        return False
    return value.strip().lower() in _TRUTHY_ENV_VALUES


def _serialize_value(value: Any) -> Any:
    """Recursively serialize values for JSON output."""
    if isinstance(value, dict):
        return {key: _serialize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    return value


def _write_json(data: Any, path: Path) -> None:
    """Write data to a JSON file, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _format_snapshot_filename(run_id: str, label: str, captured_at: datetime) -> str:
    """Format a snapshot filename with run_id, safe label, and timestamp."""
    timestamp = captured_at.strftime("%Y%m%dT%H%M%SZ")
    safe_label = _safe_label(label)
    return f"{run_id}-{safe_label}-{timestamp}.json"


def _build_runtime_run_id(label: str) -> str:
    """Build a runtime run ID from label and current timestamp."""
    component = _safe_label(label)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{component}-{timestamp}"


def _watched_release_versions(
    snapshot: ClusterSnapshot, watched: Iterable[str]
) -> dict[str, str | None]:
    """Extract version info for watched Helm releases."""
    versions: dict[str, str | None] = {}
    for release_key in watched:
        release = snapshot.helm_releases.get(release_key)
        versions[release_key] = release.chart_version if release else None
    return versions


def _watched_crd_versions(
    snapshot: ClusterSnapshot, watched: Iterable[str]
) -> dict[str, str | None]:
    """Extract storage version info for watched CRD families."""
    versions: dict[str, str | None] = {}
    for crd_name in watched:
        crd = snapshot.crds.get(crd_name)
        versions[crd_name] = crd.storage_version if crd else None
    return versions


def _safe_int(value: Any | None) -> int | None:
    """Safely parse a value as an integer, returning None for invalid inputs."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _str_or_none(value: Any) -> str | None:
    """Convert a value to a stripped string or None if empty."""
    if value is None:
        return None
    str_value = str(value).strip()
    return str_value if str_value else None


class HealthRating(StrEnum):
    """Health rating for a cluster or target."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"


@dataclass
class HealthHistoryEntry:
    """A retained health history entry for cross-run comparison."""
    cluster_id: str
    node_count: int
    pod_count: int | None
    control_plane_version: str
    health_rating: HealthRating
    missing_evidence: tuple[str, ...]
    watched_helm_releases: dict[str, str | None] = field(default_factory=dict)
    watched_crd_families: dict[str, str | None] = field(default_factory=dict)
    node_conditions: dict[str, int] = field(default_factory=dict)
    pod_counts: dict[str, int] = field(default_factory=dict)
    job_failures: int = 0
    warning_event_count: int = 0
    cluster_class: str | None = None
    cluster_role: str | None = None
    baseline_cohort: str | None = None
    baseline_policy_path: str | None = None

    @classmethod
    def from_dict(cls, cluster_id: str, data: dict[str, Any]) -> HealthHistoryEntry:
        """Parse a history entry from a dictionary (e.g., from JSON)."""
        raw_helm = data.get("watched_helm_releases")
        if isinstance(raw_helm, dict):
            watched_helm = {
                str(key): str(value) if value is not None else None
                for key, value in raw_helm.items()
                if key
            }
        else:
            watched_helm = {}
        raw_crd = data.get("watched_crd_families")
        if isinstance(raw_crd, dict):
            watched_crds = {
                str(key): str(value) if value is not None else None
                for key, value in raw_crd.items()
                if key
            }
        else:
            watched_crds = {}
        node_condition_raw = data.get("node_conditions")
        if isinstance(node_condition_raw, dict):
            node_conditions = {
                str(key): int(value) if isinstance(value, int) else int(value or 0)
                for key, value in node_condition_raw.items()
                if key
            }
        else:
            node_conditions = {}
        pod_count_raw = data.get("pod_counts")
        if isinstance(pod_count_raw, dict):
            pod_counts = {
                str(key): int(value) if isinstance(value, int) else int(value or 0)
                for key, value in pod_count_raw.items()
                if key
            }
        else:
            pod_counts = {}
        return cls(
            cluster_id=cluster_id,
            node_count=int(data.get("node_count", 0)),
            pod_count=data.get("pod_count"),
            control_plane_version=str(data.get("control_plane_version") or ""),
            health_rating=HealthRating(data.get("health_rating", "healthy")),
            missing_evidence=tuple(data.get("missing_evidence", [])),
            watched_helm_releases=watched_helm,
            watched_crd_families=watched_crds,
            node_conditions=node_conditions,
            pod_counts=pod_counts,
            job_failures=_safe_int(data.get("job_failures")) or 0,
            warning_event_count=_safe_int(data.get("warning_event_count")) or 0,
            cluster_class=_str_or_none(data.get("cluster_class")),
            cluster_role=_str_or_none(data.get("cluster_role")),
            baseline_cohort=_str_or_none(data.get("baseline_cohort") or data.get("platform_generation")),
            baseline_policy_path=_str_or_none(data.get("baseline_policy_path")),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize this entry to a dictionary for JSON storage."""
        return {
            "node_count": self.node_count,
            "pod_count": self.pod_count,
            "control_plane_version": self.control_plane_version,
            "health_rating": self.health_rating.value,
            "missing_evidence": list(self.missing_evidence),
            "watched_helm_releases": self.watched_helm_releases,
            "watched_crd_families": self.watched_crd_families,
            "node_conditions": self.node_conditions,
            "pod_counts": self.pod_counts,
            "job_failures": self.job_failures,
            "warning_event_count": self.warning_event_count,
            "cluster_class": self.cluster_class,
            "cluster_role": self.cluster_role,
            "baseline_cohort": self.baseline_cohort,
            "baseline_policy_path": self.baseline_policy_path,
        }


def load_history(history_path: Path) -> dict[str, HealthHistoryEntry]:
    """Load health history from a JSON file.

    Returns an empty dict if the file doesn't exist.
    """
    if not history_path.exists():
        return {}
    raw = json.loads(history_path.read_text(encoding="utf-8"))
    history: dict[str, HealthHistoryEntry] = {}
    for cluster_id, entry in raw.items():
        if isinstance(entry, dict):
            history[cluster_id] = HealthHistoryEntry.from_dict(cluster_id, entry)
    return history


def persist_history(history: dict[str, HealthHistoryEntry], history_path: Path) -> None:
    """Persist health history to a JSON file."""
    data = {cluster_id: entry.to_dict() for cluster_id, entry in history.items()}
    _write_json(data, history_path)