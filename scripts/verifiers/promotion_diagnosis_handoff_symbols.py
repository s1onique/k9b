"""Symbol identity and import resolution for SEAM01 verifier.

This module handles:
- Canonical module identity verification (exact match, not substring)
- Canonical class/alias ownership verification
- Import identity resolution
"""

from __future__ import annotations

import sys
from pathlib import Path

# Handle imports for both script and module execution
_verifiers_dir = Path(__file__).parent
if str(_verifiers_dir) not in sys.path:
    sys.path.insert(0, str(_verifiers_dir))

from promotion_diagnosis_handoff_model import ImportInfo

# Known type aliases for IncidentPromotionResult - MUST be verified by import identity
# P1: Must verify origin module, not just name match
INCIDENT_PROMOTION_RESULT_ALIASES = frozenset({
    "_TypedPromotionResult",  # incident_promotion_backend.py alias
})

# Canonical class names that own actionable_incident_ids
CANONICAL_ACTIONABLE_OWNERS = frozenset({
    "IncidentPromotionResult",
    "PromotionPropagationResult",
    "IncidentPromotionResultDispatch",
})

# R21: Canonical class that owns canonical_incident_ids
CANONICAL_CANONICAL_OWNER = "RunPromotionAccumulator"

# R21: Canonical class name for typed binding identity
CANONICAL_PROMOTION_BATCH = "PromotionBatch"

# Canonical module paths - MUST use exact match for security
# P1: Exact module identity, not substring containment
CANONICAL_INCIDENT_PROMOTION_RESULT_MODULES = frozenset({
    "k8s_diag_agent.collect.incident_promotion_dispatch",
    "k8s_diag_agent.collect.incident_promotion",
    "k8s_diag_agent.collect.promotion_diagnosis_handoff",  # PromotionPropagationResult lives here
    "incident_promotion_dispatch",  # sometimes imported directly
    "promotion_diagnosis_handoff",  # sometimes imported directly
})

CANONICAL_RUN_PROMOTION_ACCUMULATOR_MODULES = frozenset({
    "k8s_diag_agent.collect.incident_promotion_accumulator",
    "incident_promotion_accumulator",  # sometimes imported directly
})

# Canonical module for _TypedPromotionResult alias
CANONICAL_ALIAS_MODULES = frozenset({
    "k8s_diag_agent.collect.incident_promotion_backend",
    "incident_promotion_backend",
})

# R21: Canonical modules for PromotionBatch
CANONICAL_PROMOTION_BATCH_MODULES = frozenset({
    "k8s_diag_agent.collect.incident_promotion_batch",
    "incident_promotion_batch",
})


def normalize_module_path(module: str | None) -> str | None:
    """Normalize a module path for comparison.

    Handles:
    - Leading/trailing whitespace
    - Module alias prefixes
    """
    if not module:
        return None
    module = module.strip()
    # Remove any 'as' alias prefix if present
    if " as " in module:
        module = module.split(" as ")[0].strip()
    return module


def module_paths_equal(path1: str | None, path2: str) -> bool:
    """Check if two module paths are exactly equal.

    P1 FIX: Uses exact comparison, not substring containment.
    Rejects: "fake.k8s_diag_agent.collect.incident_promotion_dispatch_shadow"
    Accepts: "k8s_diag_agent.collect.incident_promotion_dispatch"
    """
    if not path1:
        return False
    return normalize_module_path(path1) == normalize_module_path(path2)


def resolve_annotation_to_import(
    annotation_name: str,
    imports: list[ImportInfo],
) -> ImportInfo | None:
    """Find the LAST import that provides the given annotation name.

    R14 FIX: Python imports bind names in the local namespace. The LAST visible
    import before an annotation is the effective binding. Earlier canonical imports
    can be shadowed by later fake imports.

    Example that MUST be rejected:
        from canonical import RunPromotionAccumulator  # earlier
        from fake import RunPromotionAccumulator       # later - effective binding

    Returns the last matching import, or None if no import found.
    """
    last_match: ImportInfo | None = None
    for imp in imports:
        if imp.name == annotation_name:
            last_match = imp
        elif imp.alias == annotation_name:
            last_match = imp
    return last_match


def is_from_canonical_module(
    import_info: ImportInfo | None,
    canonical_modules: frozenset[str],
) -> bool:
    """Check if an import originates from a canonical module.

    P1 FIX: Uses exact module path comparison, not substring containment.
    Rejects shadow modules that merely contain the canonical path.
    """
    if import_info is None:
        return False
    if import_info.module is None:
        return False
    # Check exact module match
    for canonical in canonical_modules:
        if module_paths_equal(import_info.module, canonical):
            return True
    return False


def is_incident_promotion_result_type(
    type_str: str | None,
    imports: list[ImportInfo] | None = None,
) -> bool:
    """Check if a type string represents IncidentPromotionResult or compatible.

    P1 FIX: Now verifies import identity. The type is only trusted if:
    1. It's imported from a canonical module, OR
    2. The import list is None (backward compatibility for simple checks)

    P1 FIX: _TypedPromotionResult alias is also verified against canonical module.
    """
    if not type_str:
        return False
    if "|" in type_str:
        return any(is_incident_promotion_result_type(t.strip(), imports) for t in type_str.split("|"))
    if "Optional[" in type_str:
        inner = type_str.replace("Optional[", "").rstrip(")")
        return is_incident_promotion_result_type(inner, imports)

    # P1 FIX: _TypedPromotionResult alias MUST be verified by import identity
    if type_str in INCIDENT_PROMOTION_RESULT_ALIASES:
        if imports is not None:
            imp = resolve_annotation_to_import(type_str, imports)
            # Reject if not imported or imported from non-canonical module
            if imp is None:
                return False
            return is_from_canonical_module(imp, CANONICAL_ALIAS_MODULES)
        # Without import list, we cannot verify - reject for security
        return False

    # Canonical class names - verify import identity
    if type_str in CANONICAL_ACTIONABLE_OWNERS:
        if imports is not None:
            imp = resolve_annotation_to_import(type_str, imports)
            if imp is None:
                # Annotation used but not imported - could be local shadow, reject
                return False
            return is_from_canonical_module(imp, CANONICAL_INCIDENT_PROMOTION_RESULT_MODULES)
        # No import list provided - reject for security (could be local shadow)
        return False

    return False


def is_run_promotion_accumulator_type(
    type_str: str | None,
    imports: list[ImportInfo] | None = None,
) -> bool:
    """Check if a type string represents RunPromotionAccumulator or compatible.

    P1 FIX: Now verifies import identity. The type is only trusted if:
    1. It's imported from a canonical module, OR
    2. The import list is None (backward compatibility for simple checks)
    """
    if not type_str:
        return False
    if "|" in type_str:
        return any(is_run_promotion_accumulator_type(t.strip(), imports) for t in type_str.split("|"))
    if "Optional[" in type_str:
        inner = type_str.replace("Optional[", "").rstrip(")")
        return is_run_promotion_accumulator_type(inner, imports)

    if type_str == CANONICAL_CANONICAL_OWNER:
        if imports is not None:
            imp = resolve_annotation_to_import(type_str, imports)
            if imp is None:
                # Annotation used but not imported - could be local shadow, reject
                return False
            return is_from_canonical_module(imp, CANONICAL_RUN_PROMOTION_ACCUMULATOR_MODULES)
        # No import list provided - reject for security
        return False

    return False


def is_canonical_actionable_owner(class_name: str) -> bool:
    """Check if a class name is a canonical owner of actionable_incident_ids."""
    return class_name in CANONICAL_ACTIONABLE_OWNERS


def is_canonical_canonical_owner(class_name: str) -> bool:
    """Check if a class name is the canonical owner of canonical_incident_ids."""
    return class_name == CANONICAL_CANONICAL_OWNER


def is_promotion_batch_type(
    type_str: str | None,
    imports: list[ImportInfo] | None = None,
) -> bool:
    """R21: Check if a type string represents PromotionBatch or compatible.

    This is the key R21 change: exact annotation-AST binding identity,
    not substring matching. The type is trusted only if:
    1. It's imported from a canonical module, OR
    2. The import list is None (backward compatibility for simple checks)
    """
    if not type_str:
        return False
    # Handle Optional[T] and T | None
    if "|" in type_str:
        return any(is_promotion_batch_type(t.strip(), imports) for t in type_str.split("|"))
    if "Optional[" in type_str:
        inner = type_str.replace("Optional[", "").rstrip(")")
        return is_promotion_batch_type(inner, imports)

    if type_str == CANONICAL_PROMOTION_BATCH:
        if imports is not None:
            imp = resolve_annotation_to_import(type_str, imports)
            if imp is None:
                # Annotation used but not imported - could be local shadow, reject
                return False
            return is_from_canonical_module(imp, CANONICAL_PROMOTION_BATCH_MODULES)
        # No import list provided - reject for security
        return False

    return False
