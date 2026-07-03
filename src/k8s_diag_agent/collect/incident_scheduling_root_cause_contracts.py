"""Contracts for Kubernetes scheduling root-cause diagnosis.

Keep this module side-effect-free. It is imported by the planner/orchestrator
and by incident_scheduling_root_cause.py.

Design constraints:
- Pure data definitions only
- No store mutation
- No LLM calls
- No Kubernetes calls
- No execution
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

# =============================================================================
# Constants
# =============================================================================

# Markers that indicate scheduling failure
_SCHEDULING_FAILURE_MARKERS = (
    "FailedScheduling",
    "Unschedulable",
    "no matching node",
    "cannot schedule",
    "unschedulable",
)

# Markers for nodeSelector mismatch
_NODE_SELECTOR_MARKERS = (
    "nodeSelector",
    "node selector",
    "nodeselector",
)

# =============================================================================
# Dataclasses
# =============================================================================


def _string_field(obj: Any, key: str, default: str = "") -> str:
    """Get string field from dict or object with enum-safe extraction.

    This handles the boundary between dict-shaped incidents, Incident objects,
    and enum-like values at the module level.

    Args:
        obj: Dict, Mapping, or object to extract field from
        key: Field name to extract
        default: Default value if field not found or None

    Returns:
        String value or default
    """
    if isinstance(obj, (dict, Mapping)):
        value = obj.get(key, default)
    else:
        value = getattr(obj, key, default)

    if value is None:
        return default

    # Handle enum-like values that have a .value attribute
    enum_value = getattr(value, "value", None)
    if enum_value is not None:
        return str(enum_value)

    return str(value)


@dataclass(frozen=True)
class SchedulingRootCauseEvidence:
    """Structured scheduling root-cause evidence for P4c diagnosis.

    This dataclass captures the deterministic evidence needed to prove
    a scheduling root cause for unschedulable-shipping scenarios.

    Attributes:
        namespace: Namespace of the affected workload
        workload_kind: Kind of workload (e.g., Deployment, StatefulSet)
        workload_name: Name of the affected workload
        selector_key: The nodeSelector key that cannot be matched
        selector_value: The nodeSelector value that cannot be matched
        selector_literal: The full selector as a string (e.g., "k9b.dev/otel-lab-node=missing")
        failed_scheduling: Whether FailedScheduling events were observed
        unschedulable: Whether pods are in Unschedulable state
        scheduler_message: Raw scheduler message from events
        matching_nodes: Tuple of node names that match the selector (empty = no match)
        root_cause_summary: Human-readable root-cause summary
    """

    namespace: str = ""
    workload_kind: str = ""
    workload_name: str = ""
    selector_key: str | None = None
    selector_value: str | None = None
    selector_literal: str | None = None
    failed_scheduling: bool = False
    unschedulable: bool = False
    scheduler_message: str | None = None
    matching_nodes: tuple[str, ...] = field(default_factory=tuple)
    root_cause_summary: str = ""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SchedulingRootCauseEvidence:
        """Create SchedulingRootCauseEvidence from a dict/Mapping.

        Accepts missing keys safely. Converts matching_nodes list/tuple to tuple.
        Preserves booleans and optional fields.

        Args:
            data: Dict or Mapping containing scheduling evidence fields

        Returns:
            SchedulingRootCauseEvidence instance
        """
        # Convert matching_nodes to tuple if present
        matching_nodes_raw = data.get("matching_nodes", ())
        if isinstance(matching_nodes_raw, (list, tuple)):
            matching_nodes = tuple(str(n) for n in matching_nodes_raw)
        else:
            matching_nodes = ()

        return cls(
            namespace=str(data.get("namespace", "")),
            workload_kind=str(data.get("workload_kind", "")),
            workload_name=str(data.get("workload_name", "")),
            selector_key=data.get("selector_key"),
            selector_value=data.get("selector_value"),
            selector_literal=data.get("selector_literal"),
            failed_scheduling=bool(data.get("failed_scheduling", False)),
            unschedulable=bool(data.get("unschedulable", False)),
            scheduler_message=data.get("scheduler_message"),
            matching_nodes=matching_nodes,
            root_cause_summary=str(data.get("root_cause_summary", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "namespace": self.namespace,
            "workload_kind": self.workload_kind,
            "workload_name": self.workload_name,
            "selector_key": self.selector_key,
            "selector_value": self.selector_value,
            "selector_literal": self.selector_literal,
            "failed_scheduling": self.failed_scheduling,
            "unschedulable": self.unschedulable,
            "scheduler_message": self.scheduler_message,
            "matching_nodes": list(self.matching_nodes),
            "root_cause_summary": self.root_cause_summary,
        }


# =============================================================================
# Normalization helpers
# =============================================================================


def _normalize_workload_kind(kind: str) -> str:
    """Normalize workload kind to title case."""
    kind_map = {
        "deployment": "Deployment",
        "statefulset": "StatefulSet",
        "daemonset": "DaemonSet",
        "job": "Job",
        "cronjob": "CronJob",
    }
    return kind_map.get(kind.lower(), kind.title() if kind else "Deployment")


__all__ = [
    "SchedulingRootCauseEvidence",
    "_SCHEDULING_FAILURE_MARKERS",
    "_NODE_SELECTOR_MARKERS",
    "_normalize_workload_kind",
    "_string_field",
]
