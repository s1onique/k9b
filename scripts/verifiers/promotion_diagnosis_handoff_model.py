"""Model types for SEAM01 promotion-diagnosis handoff verifier.

This module contains core data types:
- Provenance: tracks variable provenance
- ProvenanceSafety: safety level enum
- ClassInfo, FunctionInfo, ImportInfo: metadata types
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


# The canonical field name that terminates a safe attribute chain
CANONICAL_PROMOTION_RESULT_FIELD = "promotion_result"


class ProvenanceSafety(Enum):
    """Represents the safety level of provenance at a given point."""
    UNKNOWN = auto()
    SAFE = auto()
    UNSAFE = auto()


@dataclass
class ClassInfo:
    """Information about a class definition."""
    name: str
    line_start: int
    line_end: int
    # P1 FIX: Store module path to prevent name-only shadowing attacks
    module_path: str | None = None


@dataclass
class FunctionInfo:
    """Information about a function definition with type annotations."""
    name: str
    line_start: int
    line_end: int
    params: dict[str, str | None]  # param name -> annotation string or None
    return_annotation: str | None
    local_vars: dict[str, Provenance] = field(default_factory=dict)
    is_classmethod: bool = False  # True if @classmethod decorator present
    first_param: str | None = None  # 'cls' for classmethods, 'self' for methods


@dataclass
class ImportInfo:
    """Information about an import statement."""
    module: str | None  # None for "from X import Y"
    name: str  # The imported name
    alias: str | None  # "as X" or None
    line_start: int
    line_end: int


@dataclass
class Provenance:
    """Tracks where a variable's value comes from.

    P0: attr_chain must terminate at ("promotion_result",) for safety.
    Any other chain is not sufficient proof.
    """
    attr_chain: tuple[str, ...] | None = None
    annotated_type: str | None = None
    return_type: str | None = None

    def is_safe_promotion_result_access(self) -> bool:
        """P0: Check if this provenance represents safe promotion_result access.

        The ONLY safe chain is exactly ("promotion_result",).
        Any chain with more elements (e.g., ("promotion_result", "error_messages"))
        is NOT safe - only the result object itself owns the projection.
        """
        if self.attr_chain is None:
            return False
        return self.attr_chain == (CANONICAL_PROMOTION_RESULT_FIELD,)

    def merge(self, other: Provenance) -> Provenance:
        """P0: Merge two provenances at control-flow joins.

        For soundness, the merged result is SAFE only if BOTH paths are SAFE.
        If there's any conflict or uncertainty, we conservatively return UNKNOWN.
        """
        # If either is None/unknown, result is unknown
        if self.attr_chain is None and other.attr_chain is None:
            return Provenance()
        if self.attr_chain is None:
            return Provenance()
        if other.attr_chain is None:
            return Provenance()

        # If they're identical, that's fine
        if self.attr_chain == other.attr_chain:
            result = Provenance()
            result.attr_chain = self.attr_chain
            result.annotated_type = self.annotated_type if self.annotated_type == other.annotated_type else None
            return result

        # Conflict: different chains -> unknown
        return Provenance()
