"""Model types for SEAM01 promotion-diagnosis handoff verifier.

This module contains core data types:
- Provenance: tracks variable provenance
- ProvenanceSafety: safety level enum
- ClassInfo, FunctionInfo, ImportInfo: metadata types
- FlowResult: path separation for control flow analysis
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


# The canonical field name that terminates a safe attribute chain
CANONICAL_PROMOTION_RESULT_FIELD = "promotion_result"


class ProvenanceKind(Enum):
    """R21: Distinct provenance kinds for typed binding identity.

    These replace substring matching with exact annotation-AST binding resolution.
    """
    # Origin unknown or not verified
    UNKNOWN = auto()
    # Variable typed as PromotionBatch (or compatible) via verified import identity
    PROMOTION_BATCH = auto()
    # Variable typed as IncidentPromotionResult (or compatible) via verified import identity
    INCIDENT_PROMOTION_RESULT = auto()
    # Variable typed as RunPromotionAccumulator (or compatible) via verified import identity
    RUN_PROMOTION_ACCUMULATOR = auto()


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
class FlowResult:
    """R3: Explicit path separation for control flow analysis.

    Replaces boolean has_break + single environment with explicit path tracking.
    Each field contains a list of environments representing all paths of that type.

    For sequence: feed only normal paths into next statement
    For if: union body.normal + orelse.normal for normal paths
    For loop: exhaustion paths = zero-iteration + normal body completion
    """
    # Normal execution paths (continue to next statement)
    normal: list[dict[str, Provenance]] = field(default_factory=list)
    # Break paths (exits the enclosing loop)
    breaks: list[dict[str, Provenance]] = field(default_factory=list)
    # Continue paths (restarts the enclosing loop)
    continues: list[dict[str, Provenance]] = field(default_factory=list)
    # Return paths (exits the function)
    returns: list[dict[str, Provenance]] = field(default_factory=list)
    # Raise paths (exits with exception)
    raises: list[dict[str, Provenance]] = field(default_factory=list)

    def merge_all(self) -> dict[str, Provenance]:
        """Merge all paths (normal + break + continue + return + raise).

        Used at control-flow joins where all paths converge.
        """
        return merge_paths(self.normal + self.breaks + self.continues + self.returns + self.raises)


@dataclass
class Provenance:
    """Tracks where a variable's value comes from.

    R21: Now includes provenance_kind for exact binding identity.
    The attr_chain must terminate at ("promotion_result",) for safety,
    but ONLY when the variable has verified PROMOTION_BATCH provenance kind.
    """
    attr_chain: tuple[str, ...] | None = None
    annotated_type: str | None = None
    return_type: str | None = None
    # R21: Provenance kind from verified import identity
    provenance_kind: ProvenanceKind = ProvenanceKind.UNKNOWN

    def is_safe_promotion_result_access(self) -> bool:
        """P0: Check if this provenance represents safe promotion_result access.

        The ONLY safe chain is exactly ("promotion_result",) AND
        the variable must have INCIDENT_PROMOTION_RESULT provenance.

        A PROMOTION_BATCH is the envelope, not the owner of actionable_incident_ids.
        Accepting both kinds obscures incorrect transitions and creates a laundering bypass.

        This prevents:
        - untrusted.promotion_result.actionable_incident_ids (UNKNOWN provenance)
        - batch: PromotionBatch -> batch.promotion_result (PROMOTION_BATCH without transition)

        This allows:
        - batch: PromotionBatch -> batch.promotion_result -> actionable_incident_ids
          where batch.promotion_result transition produces INCIDENT_PROMOTION_RESULT
        """
        if self.attr_chain is None:
            return False
        if self.attr_chain != (CANONICAL_PROMOTION_RESULT_FIELD,):
            return False
        # P0 Fix: Only INCIDENT_PROMOTION_RESULT can safely access actionable_incident_ids.
        # PROMOTION_BATCH is the envelope, not the capability owner.
        return self.provenance_kind == ProvenanceKind.INCIDENT_PROMOTION_RESULT

    def merge(self, other: Provenance) -> Provenance:
        """P0: Merge two provenances at control-flow joins.

        For soundness, the merged result is SAFE only if BOTH paths are SAFE.
        If there's any conflict or uncertainty, we conservatively return UNKNOWN.

        Key rules:
        - If either path has UNKNOWN provenance kind, result is UNKNOWN
        - If provenance kinds differ (both non-UNKNOWN), result is UNKNOWN
        - If both have same typed provenance (same kind, same attr_chain), preserve it
        - Only if BOTH are safe with same attr_chain, result is safe
        """
        # P0: If either has UNKNOWN provenance kind, result is UNKNOWN
        # This prevents unknown + safe = safe bypasses
        if self.provenance_kind == ProvenanceKind.UNKNOWN or other.provenance_kind == ProvenanceKind.UNKNOWN:
            return Provenance()

        # P0 FIX: If provenance kinds differ (both non-UNKNOWN), result is UNKNOWN
        # This preserves typed identity - PromotionBatch + PromotionBatch stays typed
        # But PromotionBatch + INCIDENT_PROMOTION_RESULT becomes unknown
        if self.provenance_kind != other.provenance_kind:
            return Provenance()

        # If both have no provenance info AND same kind, return same kind with no attr_chain
        # This preserves typed parameters that haven't been accessed yet
        if self.attr_chain is None and other.attr_chain is None:
            result = Provenance()
            result.annotated_type = self.annotated_type if self.annotated_type == other.annotated_type else None
            result.provenance_kind = self.provenance_kind
            return result

        # If one has no provenance info, result is UNKNOWN
        # (can't prove safety when one path is unknown)
        if self.attr_chain is None or other.attr_chain is None:
            return Provenance()

        # If they're identical, preserve the provenance
        if self.attr_chain == other.attr_chain:
            result = Provenance()
            result.attr_chain = self.attr_chain
            result.annotated_type = self.annotated_type if self.annotated_type == other.annotated_type else None
            result.provenance_kind = self.provenance_kind
            return result

        # Conflict: different chains -> unknown
        return Provenance()


def merge_paths(paths: list[dict[str, Provenance]]) -> dict[str, Provenance]:
    """Merge multiple execution paths into a single environment.

    For soundness, a variable absent from one reachable path is not safely proven.
    Missing bindings must be represented explicitly as unknown.

    The merged result is SAFE only if ALL paths produce safe provenance for
    every variable that exists in any path.
    """
    if not paths:
        return {}

    result: dict[str, Provenance] = {}
    # Collect ALL variable names across all paths
    all_names: set[str] = set()
    for path in paths:
        all_names.update(path.keys())

    # For each variable, merge across all paths
    for name in all_names:
        # Collect all values for this variable
        values: list[Provenance] = []
        for path in paths:
            if name in path:
                values.append(path[name])

        # If any path doesn't have this variable, result is unknown
        # (may not be assigned on that path)
        if len(values) < len(paths):
            result[name] = Provenance()  # unknown
            continue

        # All paths have the variable - merge them
        merged = values[0]
        for v in values[1:]:
            merged = merged.merge(v)
        result[name] = merged

    return result
