"""Read-only check catalog contracts for automatic diagnosis loop.

This module contains:
- CheckCost: Check execution cost enum
- CheckExpectedValue: Expected discriminative value enum
- CheckDefinition: Definition of a read-only check

These are pure data contracts with no implementation logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

# =============================================================================
# Schema Version
# =============================================================================

SCHEMA_VERSION = "1.0"


# =============================================================================
# Check Cost and Value
# =============================================================================


class CheckCost(StrEnum):
    """Check execution cost."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CheckExpectedValue(StrEnum):
    """Expected discriminative value of check result."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# =============================================================================
# Check Definition
# =============================================================================


@dataclass(frozen=True)
class CheckDefinition:
    """Definition of a read-only check.

    Each check must declare:
    - id: Unique check identifier
    - kind: Always "read_only_kubernetes"
    - cost: LOW|MEDIUM|HIGH
    - expected_value: LOW|MEDIUM|HIGH
    - required_identity: What identity parameters are needed
    - handler: Handler function (for fake runner compatibility)
    - timeout: Maximum execution time in seconds
    - result_bound: Maximum result size
    """

    check_id: str
    kind: str  # Always "read_only_kubernetes"
    cost: str  # LOW|MEDIUM|HIGH
    expected_value: str  # LOW|MEDIUM|HIGH
    requires_namespace: bool
    requires_object_name: bool
    requires_pod_name: bool
    requires_node_name: bool
    description: str
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict."""
        return {
            "check_id": self.check_id,
            "kind": self.kind,
            "cost": self.cost,
            "expected_value": self.expected_value,
            "requires": {
                "namespace": self.requires_namespace,
                "object_name": self.requires_object_name,
                "pod_name": self.requires_pod_name,
                "node_name": self.requires_node_name,
            },
            "description": self.description,
            "rationale": self.rationale,
        }

    def can_execute_with(self, **identity: bool | str | None) -> bool:
        """Check if this check can execute with given identity."""
        if self.requires_namespace and not identity.get("namespace"):
            return False
        if self.requires_object_name and not identity.get("object_name"):
            return False
        if self.requires_pod_name and not identity.get("pod_name"):
            return False
        if self.requires_node_name and not identity.get("node_name"):
            return False
        return True


__all__ = [
    "SCHEMA_VERSION",
    "CheckCost",
    "CheckExpectedValue",
    "CheckDefinition",
]
